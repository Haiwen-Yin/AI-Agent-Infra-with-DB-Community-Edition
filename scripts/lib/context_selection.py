"""Metadata-first selection and deterministic model-input budget contracts.

Tokenizers are resolved from an installed, known implementation only. The
conservative fallback counts each UTF-8 byte as one token, never characters.
No tokenizer is downloaded, nor is caller-supplied code loaded.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager,nullcontext
import json
import logging
import re
import unicodedata
from . import identity_api, continuity_work as work
from .continuity_contracts import SourceRef
from .continuity_state import ContinuityConflict

_logger=logging.getLogger(__name__)
_UNREAD=object()


def schema_statements(dialect):
    if dialect not in {'pg', 'postgresql', 'oracle', 'yashandb'}:
        raise ValueError('unsupported database adapter')
    return [
        "CREATE TABLE CX_CONTEXT_BUDGETS (ASSEMBLY_ID VARCHAR(128) PRIMARY KEY REFERENCES CX_CONTEXT_ASSEMBLIES(ASSEMBLY_ID), "
        "COUNT_METHOD VARCHAR(128) NOT NULL, MODEL_NAME VARCHAR(200), CONTEXT_WINDOW INTEGER NOT NULL CHECK(CONTEXT_WINDOW>0), "
        "OUTPUT_RESERVE INTEGER NOT NULL CHECK(OUTPUT_RESERVE>=0), SYSTEM_TOKENS INTEGER NOT NULL CHECK(SYSTEM_TOKENS>=0), "
        "TOOL_TOKENS INTEGER NOT NULL CHECK(TOOL_TOKENS>=0), SOURCE_BUDGET INTEGER NOT NULL CHECK(SOURCE_BUDGET>=0), "
        "BYTE_BUDGET INTEGER NOT NULL CHECK(BYTE_BUDGET>0), QUERY_DIGEST VARCHAR(64) NOT NULL, "
        "CHECK(SOURCE_BUDGET+SYSTEM_TOKENS+TOOL_TOKENS+OUTPUT_RESERVE<=CONTEXT_WINDOW))",
        "CREATE TABLE CX_CONTEXT_REPRESENTATIONS (ASSEMBLY_ID VARCHAR(128) NOT NULL REFERENCES CX_CONTEXT_ASSEMBLIES(ASSEMBLY_ID), "
        "SOURCE_NO INTEGER NOT NULL CHECK(SOURCE_NO>0), ITEM_NO INTEGER, FAMILY VARCHAR(24) NOT NULL, ENTITY_ID VARCHAR(128) NOT NULL, "
        "REVISION_ID VARCHAR(128) NOT NULL, CONTENT_DIGEST VARCHAR(64) NOT NULL, RENDERED_DIGEST VARCHAR(64), "
        "REPRESENTATION VARCHAR(16) NOT NULL CHECK(REPRESENTATION IN ('COMPLETE','PARTIAL','OMITTED')), "
        "SELECTION_REASON VARCHAR(64) NOT NULL, RANK_SCORE INTEGER NOT NULL, TOKEN_COUNT INTEGER NOT NULL CHECK(TOKEN_COUNT>=0), "
        "BYTE_COUNT INTEGER NOT NULL CHECK(BYTE_COUNT>=0), "
        "DELIVERY_STATUS VARCHAR(16) NOT NULL CHECK(DELIVERY_STATUS IN ('PREPARED','CONFIRMED','UNOBSERVED','OMITTED')), "
        "PRIMARY KEY(ASSEMBLY_ID,SOURCE_NO), FOREIGN KEY(ASSEMBLY_ID,ITEM_NO) REFERENCES CX_CONTEXT_ASSEMBLY_ITEMS(ASSEMBLY_ID,ITEM_NO))",
    ]


def counter(model_name=''):
    # encoding_for_model rejects unknown model families. An absent library or
    # unknown model must remain an explicitly labeled estimate.
    if model_name:
        try:
            import tiktoken
            from tiktoken import registry, model
            # Avoid downloading missing vocabulary files from a read path.
            encoding_name = model.encoding_name_for_model(model_name)
            encoding = registry.ENCODINGS.get(encoding_name)
            if encoding is None:
                raise KeyError('Tokenizer vocabulary is not locally initialized')
            return lambda text: len(encoding.encode(text, disallowed_special=())), 'TIKTOKEN:' + encoding.name
        except (ImportError, KeyError, ValueError):
            pass
    return lambda text: len(text.encode('utf-8')), 'UTF8_UPPER_BOUND'


def _provider_json(value):
    # Match native_runtime's actual request serialization, including spaces,
    # escaping and every schema/control key. This is an input estimate, never
    # Provider-reported usage or a claim about the Provider's hidden framing.
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _positive_bound(value, name, *, allow_zero=False):
    if type(value) is not int or value < (0 if allow_zero else 1) or value > 16777216:
        raise ValueError(name + ' is outside its supported bound')
    return value


def provider_contract_budget(request_fields, *, token_budget, byte_budget=262144,
                             model_name='', base_payload=None, output_reserve=None):
    """Measure exact request JSON without shrinking any required contract.

    ``base_payload`` must contain the final model/messages/stream and Provider
    parameters. Limits deliberately retain the conservative UTF-8 byte plus
    output-reserve bound even when a local tokenizer reports fewer tokens.
    The caller revalidates current source and contract authority before send;
    a budget receipt confers no disclosure or execution authority.
    """
    if not isinstance(request_fields, dict) or set(request_fields) - {
            'tools', 'tool_choice', 'response_format', 'max_tokens', 'temperature'}:
        raise ValueError('Unsupported Provider contract fields')
    if base_payload is not None and not isinstance(base_payload, dict):
        raise ValueError('Provider base payload must be an object')
    if not isinstance(model_name, str) or len(model_name) > 200:
        raise ValueError('A bounded model name is required')
    _positive_bound(token_budget, 'token_budget')
    _positive_bound(byte_budget, 'byte_budget')
    configured_output = request_fields.get('max_tokens', (base_payload or {}).get('max_tokens'))
    reserve = (configured_output if configured_output is not None else 0) if output_reserve is None else output_reserve
    _positive_bound(reserve, 'output_reserve', allow_zero=True)
    if configured_output is not None and (type(configured_output) is not int or configured_output < 1 or configured_output != reserve):
        raise ValueError('Output reserve must equal the exact Provider max_tokens')
    base = dict(base_payload or {})
    full = {**base, **request_fields}
    serialized, schema, before = _provider_json(full), (_provider_json(request_fields) if request_fields else ''), _provider_json(base)
    input_bytes = len(serialized.encode('utf-8'))
    if input_bytes > byte_budget:
        raise ContinuityConflict('PROVIDER_INPUT_EXCEEDS_BYTE_BUDGET', 'The complete Provider input exceeds its byte budget')
    if input_bytes + reserve > token_budget:
        raise ContinuityConflict('PROVIDER_INPUT_EXCEEDS_TOKEN_BUDGET', 'The complete Provider input and output reserve exceed the conservative token budget')
    count, method = counter(model_name)
    return dict(input_bytes=input_bytes, input_tokens=count(serialized), output_reserve=reserve,
                conservative_total_units=input_bytes + reserve, token_budget=token_budget, byte_budget=byte_budget,
                schema_bytes=len(schema.encode('utf-8')), schema_tokens=count(schema),
                incremental_bytes=input_bytes-len(before.encode('utf-8')),
                incremental_tokens=count(serialized)-count(before), count_method=method,
                input_digest=hashlib.sha256(serialized.encode('utf-8')).hexdigest(),
                schema_digest=hashlib.sha256(schema.encode('utf-8')).hexdigest(),
                serialization='NATIVE_PROVIDER_JSON_V1', execution_authorized=False)


def budget(request, *, provider_fields=None):
    count, method = counter(request.model_name)
    system, tools = count(request.system_text), count(request.tool_text)
    schema_text = ''
    if provider_fields is not None:
        if not isinstance(provider_fields, dict) or set(provider_fields) - {'tools', 'tool_choice', 'response_format'}:
            raise ValueError('Unsupported input schema fields')
        if provider_fields:
            schema_text = _provider_json(provider_fields)
            tools += count(schema_text)
    window = request.context_window or (request.token_budget + system + tools + request.output_reserve)
    remaining = window - system - tools - request.output_reserve
    if remaining < 0:
        raise ContinuityConflict('CONTEXT_RESERVES_EXCEED_WINDOW', 'System, tool and output reserves exceed the context window')
    return dict(count=count, count_method=method, context_window=window, system_tokens=system,
                tool_tokens=tools, output_reserve=request.output_reserve,
                source_budget=min(remaining, request.token_budget), byte_budget=request.byte_budget,
                tool_schema_tokens=count(schema_text), tool_schema_bytes=len(schema_text.encode('utf-8')),
                tool_schema_digest=hashlib.sha256(schema_text.encode('utf-8')).hexdigest() if schema_text else None)


def plan_schema_contracts(candidates, query, *, load_exact, validate_current, render_payload,
                          token_budget, byte_budget=262144, limit=5, model_name=''):
    """Rank authorized metadata, then cost only exact selected contracts.

    All callbacks are trusted server code. ``load_exact`` performs the normal
    directory/source load and ``validate_current`` independently rechecks the
    selected contracts after loading. Neither metadata nor this plan is an
    execution grant; dispatch must revalidate again at its authority boundary.
    """
    if (not isinstance(candidates, (list, tuple)) or len(candidates) > 100
            or not isinstance(query, str) or not query.strip() or len(query) > 4000
            or type(limit) is not int or not 1 <= limit <= 10):
        raise ValueError('Invalid bounded contract selection input')
    _positive_bound(token_budget, 'token_budget')
    _positive_bound(byte_budget, 'byte_budget')
    seen = {}
    for item in candidates:
        if (not isinstance(item, dict) or item.get('family') not in {'SKILL', 'TOOL'}
                or any(not isinstance(item.get(key), str) for key in ('entity_id', 'name', 'version'))
                or item.get('content_digest') is not None and not re.fullmatch(r'[0-9a-f]{64}', str(item['content_digest']))):
            raise ValueError('An exact directory metadata contract is required')
        key = (item['family'], item['entity_id'], item['version'])
        if key in seen and seen[key] != item:
            raise ValueError('Conflicting directory metadata cannot be deduplicated')
        seen.setdefault(key, item)
    ranked = sorted(seen.values(), key=lambda item: (
        -score(query, item['name'], item.get('description', '')),
        item['family'], item['entity_id'], item['version'], item.get('content_digest') or ''))
    loaded, items, excluded = [], [], []
    for candidate in ranked:
        relevance = score(query, candidate['name'], candidate.get('description', ''))
        reason = 'NO_RELEVANCE' if relevance == 0 else 'SELECTION_LIMIT' if len(items) >= limit else None
        if reason:
            excluded.append(dict(family=candidate['family'], entity_id=candidate['entity_id'], selection_reason=reason))
            continue
        value = load_exact(candidate)
        if (not isinstance(value, dict)
                or any(value.get(key) != candidate[key] for key in ('family', 'entity_id', 'name', 'version'))
                or not re.fullmatch(r'[0-9a-f]{64}', str(value.get('content_digest') or ''))
                or candidate.get('content_digest') is not None and value['content_digest'] != candidate['content_digest']):
            raise ContinuityConflict('STALE_CONTRACT', 'The selected directory contract changed before loading')
        proposed = [*loaded, value]
        try:
            provider_contract_budget({}, token_budget=token_budget, byte_budget=byte_budget,
                model_name=model_name, base_payload=render_payload(proposed), output_reserve=0)
        except ContinuityConflict as exc:
            if exc.code not in {'PROVIDER_INPUT_EXCEEDS_BYTE_BUDGET', 'PROVIDER_INPUT_EXCEEDS_TOKEN_BUDGET'}:
                raise
            excluded.append(dict(family=candidate['family'], entity_id=candidate['entity_id'], selection_reason=exc.code))
            continue
        loaded = proposed
        items.append({**candidate, 'content_digest': value['content_digest'], 'rank_score': relevance,
                      'selection_reason': 'QUERY_METADATA_SCHEMA_BUDGET'})
    for selected in items:
        validate_current(selected)
    payload = render_payload(loaded) if loaded else {}
    if loaded:
        observation = provider_contract_budget({}, token_budget=token_budget, byte_budget=byte_budget,
            model_name=model_name, base_payload=payload, output_reserve=0)
    else:
        observation = dict(input_bytes=0, input_tokens=0, schema_bytes=0, schema_tokens=0,
                           output_reserve=0, conservative_total_units=0, token_budget=token_budget,
                           byte_budget=byte_budget, count_method=counter(model_name)[1],
                           serialization='NATIVE_PROVIDER_JSON_V1', execution_authorized=False)
    return dict(items=items, excluded=excluded, provider_payload=payload, budget=observation,
                policy='QUERY_METADATA_SCHEMA_BUDGET_V1', execution_authorized=False)


def terms(text):
    normalized = unicodedata.normalize('NFKC', str(text)).casefold()
    words = set(re.findall(r'[\w]+', normalized))
    # Bigrams permit bounded CJK matching without introducing a tokenizer
    # service or making metadata search depend on an external model.
    for run in re.findall(r'[\u3400-\u9fff]+', normalized):
        words.update(run[index:index + 2] for index in range(len(run) - 1))
    return words


def score(query, name, description=''):
    if not query.strip():
        return 1
    wanted, title, detail = terms(query), terms(name), terms(description)
    return sum(4 if item in title else 1 for item in wanted if item in title or item in detail)


def metadata(tx, actor, domain, source, *, _located=_UNREAD, _record=_UNREAD, _access=None):
    """Authorize exact source metadata before returning a relevance signal.

    Cross-domain publication bodies are intentionally left to their existing
    resolver; selection is not a new publication or ownership bypass.
    """
    from .continuity_sources import locate
    source = source if isinstance(source, SourceRef) else SourceRef.model_validate(source)
    located = locate(tx, source) if _located is _UNREAD else _located
    if not located or not located.get('security_domain_id') or not located.get('owner_principal_id'):
        raise PermissionError('Source access denied')
    work._authorize(tx, actor, domain, write=False)
    if located['security_domain_id'] != domain:
        raise PermissionError('An explicit context publication is required')
    family = source.family.value
    if family in {'MEMORY', 'KNOWLEDGE', 'EXPERIENCE', 'SKILL'}:
        action = {'MEMORY': 'memory.read', 'KNOWLEDGE': 'knowledge.read',
                  'EXPERIENCE': 'knowledge.read', 'SKILL': 'skills.read'}[family]
        access = (_access or {}).get(action) or identity_api.effective_access(actor, action, resource={'security_domain_id': domain})
        if access.get('decision') != 'ALLOW':
            raise PermissionError('Source access denied')
        # Memory has its own scoped reader; Knowledge uses its current native
        # sharing policy below. Neither is limited to the artifact's author.
        # Other artifact families retain their owner/ALL boundary.
        if family in {'EXPERIENCE','SKILL'} and located['owner_principal_id'] != actor and 'ALL' not in access.get('scopes', []):
            raise PermissionError('Source access denied')
    if family == 'MEMORY':
        from . import memory_lifecycle as memory
        record = tx.query_one("SELECT v.TITLE,v.CONTENT_DIGEST,v.LIFECYCLE_STATE,v.VALID_UNTIL,v.OWNER_PRINCIPAL_ID,v.SECURITY_DOMAIN_ID,"
                              "v.MEMORY_SCOPE,v.CLASSIFICATION FROM CX_MEMORY_VERSIONS v JOIN CX_MEMORY_FAMILIES f ON f.FAMILY_ID=v.FAMILY_ID "
                              "JOIN CX_MEMORY_VERSIONS c ON c.VERSION_ID=f.CURRENT_VERSION_ID WHERE v.FAMILY_ID=:entity AND v.VERSION_ID=:revision "
                              "AND c.LIFECYCLE_STATE IN ('ACTIVE','STALE','CONFLICTED','MIGRATED') "
                              "AND (v.VALID_UNTIL IS NULL OR v.VALID_UNTIL>CURRENT_TIMESTAMP)",
                              {'entity': source.entity_id, 'revision': source.revision_id}) if _record is _UNREAD else _record
        if not record or record.get('security_domain_id') != domain:
            raise PermissionError('Source access denied')
        try:
            memory._require_memory_access(actor, record, purpose='RUNTIME_CONTEXT')
        except memory.MemoryLifecycleError as exc:
            raise PermissionError('Source access denied') from exc
        from .memory_quality import require_applicable
        try:
            require_applicable(tx, source.revision_id)
        except ContinuityConflict as exc:
            if exc.code != 'NOT_APPLICABLE':
                raise
            # Unavailable metadata is not an asset-directory disclosure. The
            # body resolver retains its normal applicability conflict result.
            raise PermissionError('Source access denied') from exc
    elif family in {'KNOWLEDGE', 'EXPERIENCE', 'SKILL'}:
        record = tx.query_one("SELECT e.TITLE,r.CONTENT_DIGEST,r.NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS r JOIN ENTITIES e ON "
                              "CAST(e.ENTITY_ID AS VARCHAR(128))=r.NATIVE_ENTITY_ID WHERE r.ARTIFACT_ID=:entity AND r.REVISION_ID=:revision",
                              {'entity': source.entity_id, 'revision': source.revision_id}) if _record is _UNREAD else _record
        if family == 'KNOWLEDGE':
            from .knowledge_api import knowledge_access_predicate
            allowed = tx.query_one("SELECT e.ENTITY_ID FROM ENTITIES e JOIN CX_CONTINUITY_ARTIFACT_REVS r ON "
                                   "CAST(e.ENTITY_ID AS VARCHAR(128))=r.NATIVE_ENTITY_ID WHERE r.ARTIFACT_ID=:entity AND r.REVISION_ID=:revision AND " +
                                   knowledge_access_predicate('e', ':actor'),
                                   {'entity': source.entity_id, 'revision': source.revision_id, 'actor': actor})
            if not allowed:
                raise PermissionError('Source access denied')
    elif family == 'SOURCE':
        from . import agent_source_sync
        record = agent_source_sync.source_metadata(tx, actor, domain, source)
    else:
        # Work/Handoff/native snapshots have richer participant checks. Their
        # normal resolver is the authority boundary, not directory metadata.
        from .continuity_sources import resolve
        resolved = resolve(tx, actor, domain, source)
        record = {'title': family, 'content_digest': resolved['content_digest']}
    if not record or record['content_digest'] != source.content_digest:
        raise ContinuityConflict('STALE_CONTENT', 'Source metadata revision or digest changed')
    source_context=None
    if family=='MEMORY':
        from .continuity_promotions import require_memory_original_sources
        source_context=require_memory_original_sources(tx,actor,source.entity_id,source.revision_id,record)
    elif family in {'KNOWLEDGE','EXPERIENCE','SKILL'}:
        from .continuity_promotions import require_original_sources
        source_context=require_original_sources(tx,actor,record['native_entity_id'])
    return {'name': str(record.get('title') or family), 'description': '', 'source': source,
        **({'source_context':source_context} if source_context else {})}


@contextmanager
def permission_inputs(tx,actor,actions,*,cache=False):
    """One locked actor/version, one transaction; canonical policy only.

    Legacy readers and delegated authority keep their original immediate
    checks. Cached decisions are limited to metadata-only paths for this
    locked actor, never publication publishers or a later consumption.
    """
    if not actions or not callable(getattr(tx,'execute_many',None)):
        yield None;return
    principal=tx.query_one("SELECT STATUS,PERMISSION_VERSION FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor FOR UPDATE",{'actor':actor})
    if not principal or principal['status']!='ACTIVE':raise PermissionError('Source access denied')
    version=int(principal['permission_version'])
    decisions=identity_api.effective_access_many(actor,actions)
    if any(int(value.get('policy_version',-1))!=version for value in decisions.values()):
        raise PermissionError('Source permission version changed')
    delegated=any(str(origin).startswith('delegation:') for value in decisions.values() for origin in value.get('sources',[]))
    with identity_api.cached_authorization() if cache and not delegated else nullcontext():
        yield None if delegated else decisions
    current=tx.query_one("SELECT STATUS,PERMISSION_VERSION FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor",{'actor':actor})
    if not current or current['status']!='ACTIVE' or int(current['permission_version'])!=version:
        raise PermissionError('Source permission version changed')
    if identity_api.effective_access_many(actor,actions)!=decisions:
        raise PermissionError('Source permission inputs expired or changed')


def _metadata_inputs(tx,sources):
    from .continuity_sources import locate_many,read_ids
    from .memory_quality import applicable_sql
    located=locate_many(tx,sources,lock=True);records={}
    memories=[source for source in sources if source.family.value=='MEMORY']
    if memories:
        rows=read_ids(tx,"SELECT v.FAMILY_ID AS BATCH_ENTITY_ID,v.VERSION_ID AS BATCH_REVISION_ID,"
            "v.TITLE,v.CONTENT_DIGEST,v.LIFECYCLE_STATE,v.VALID_UNTIL,v.OWNER_PRINCIPAL_ID,v.SECURITY_DOMAIN_ID,v.MEMORY_SCOPE,v.CLASSIFICATION,"
            "CASE WHEN "+applicable_sql('v')+" THEN 1 ELSE 0 END AS BATCH_APPLICABLE "
            "FROM CX_MEMORY_VERSIONS v JOIN CX_MEMORY_FAMILIES f ON f.FAMILY_ID=v.FAMILY_ID "
            "JOIN CX_MEMORY_VERSIONS c ON c.VERSION_ID=f.CURRENT_VERSION_ID WHERE v.VERSION_ID IN ({ids}) "
            "AND c.LIFECYCLE_STATE IN ('ACTIVE','STALE','CONFLICTED','MIGRATED') "
            "AND (v.VALID_UNTIL IS NULL OR v.VALID_UNTIL>CURRENT_TIMESTAMP) ORDER BY v.VERSION_ID FOR UPDATE",[source.revision_id for source in memories])
        found={(row['batch_entity_id'],row['batch_revision_id']):row for row in rows}
        for source in memories:records[('MEMORY',source.entity_id,source.revision_id)]=found.get((source.entity_id,source.revision_id))
    artifacts=[source for source in sources if source.family.value in {'KNOWLEDGE','EXPERIENCE','SKILL'}]
    if artifacts:
        rows=read_ids(tx,"SELECT r.ARTIFACT_ID AS BATCH_ENTITY_ID,r.REVISION_ID AS BATCH_REVISION_ID,e.TITLE,r.CONTENT_DIGEST,r.NATIVE_ENTITY_ID "
            "FROM CX_CONTINUITY_ARTIFACT_REVS r JOIN ENTITIES e ON CAST(e.ENTITY_ID AS VARCHAR(128))=r.NATIVE_ENTITY_ID "
            "WHERE r.ARTIFACT_ID IN ({ids}) ORDER BY r.ARTIFACT_ID,r.REVISION_ID FOR UPDATE",[source.entity_id for source in artifacts])
        found={(row['batch_entity_id'],row['batch_revision_id']):row for row in rows}
        for source in artifacts:records[(source.family.value,source.entity_id,source.revision_id)]=found.get((source.entity_id,source.revision_id))
    return located,records


def metadata_many(tx,actor,domain,values,*,omit_denied=False):
    """Read bounded authorized metadata, then validate in original order."""
    sources=[value if isinstance(value,SourceRef) else SourceRef.model_validate(value) for value in values]
    if len(sources)>500:raise ValueError('Too many exact source references')
    if not sources:return []
    # Preserve the global actor-before-business-roots lock order even when
    # only metadata will be disclosed and no body resolver follows.
    work._authorize(tx,actor,domain,write=False)
    actions={'MEMORY':'memory.read','KNOWLEDGE':'knowledge.read','EXPERIENCE':'knowledge.read','SKILL':'skills.read'}
    requested={actions[source.family.value] for source in sources if source.family.value in actions}
    cache=bool(sources) and all(source.family.value in actions for source in sources)
    result=[]
    with permission_inputs(tx,actor,requested,cache=cache) as access:
        located,records=_metadata_inputs(tx,sources)
        for source in sources:
            key=(source.family.value,source.entity_id,source.revision_id)
            try:result.append(metadata(tx,actor,domain,source,_located=located.get(key,_UNREAD),_record=records.get(key,_UNREAD),_access=access))
            except PermissionError:
                if not omit_denied:raise
                result.append(None)
        # Locks serialize other transactions; the second read also detects a
        # mutation by a trusted callback in this same transaction and expiry
        # during selection. A directory cannot rely on a later body resolve.
        if _metadata_inputs(tx,sources)!=(located,records):
            raise ContinuityConflict('STALE_CONTENT','Source metadata authority changed during selection')
        work._authorize(tx,actor,domain,write=False)
    return result


def _knowledge_sources(tx,actor,request,reader):
    """Discover exact current domain artifacts through the shared hybrid path.

    Optional hits retain ordinary metadata/source authority. This does not
    promote legacy notes, infer grants, or turn graph relations into receipts.
    """
    from . import knowledge_grounding,embedding_api
    from .continuity_sources import read_ids
    if request.knowledge_retrieval is None or request.entry_limit==0:
        return []
    work._authorize(tx,reader,request.security_domain_id,write=False)
    with embedding_api.query_scope():
        found=knowledge_grounding.search(actor,reader,request.query_text,
            strategy='hybrid',limit=20,artifact_domain=request.security_domain_id,applicability=request.applicability,
            transaction=tx)
    keys=[item['entity_id'] for item in found['items']]
    rows=read_ids(tx,"SELECT r.NATIVE_ENTITY_ID,r.ARTIFACT_ID,r.REVISION_ID,r.CONTENT_DIGEST "
        "FROM CX_CONTINUITY_ARTIFACTS a JOIN CX_CONTINUITY_ARTIFACT_REVS r ON r.ARTIFACT_ID=a.ARTIFACT_ID "
        "AND r.REVISION_ID=a.CURRENT_REVISION_ID WHERE a.STATUS='ACTIVE' AND a.FAMILY='KNOWLEDGE' "
        "AND a.SECURITY_DOMAIN_ID=:domain AND r.NATIVE_ENTITY_ID IN ({ids})",keys,
        params={'domain':request.security_domain_id})
    by_native={str(row['native_entity_id']):row for row in rows}
    sources=[SourceRef(family='KNOWLEDGE',entity_id=by_native[key]['artifact_id'],
        revision_id=by_native[key]['revision_id'],content_digest=by_native[key]['content_digest']) for key in keys if key in by_native]
    result=[]
    metadata=metadata_many(tx,actor,request.security_domain_id,sources,omit_denied=True)
    other=metadata_many(tx,reader,request.security_domain_id,sources,omit_denied=True) if reader!=actor else metadata
    for rank,(item,readable) in enumerate(zip(metadata,other)):
        if item is not None and readable is not None:
            result.append(dict(item,mandatory=False,rank_score=1000-rank,selection_reason='DATABASE_HYBRID'))
    return result


def select_sources(tx, actor, request,*,reader=None):
    mandatory = {(s.family.value, s.entity_id, s.revision_id) for s in request.mandatory_sources}
    seen, candidates, unique = {}, [], []
    for source in (*request.mandatory_sources, *request.sources):
        key = (source.family.value, source.entity_id, source.revision_id)
        if key in seen:
            if seen[key] != source.content_digest:
                raise ContinuityConflict('STALE_CONTENT', 'Repeated source identity has conflicting exact digests')
            continue
        seen[key] = source.content_digest
        unique.append(source)
    for source,item in zip(unique,metadata_many(tx,actor,request.security_domain_id,unique)):
        key=(source.family.value,source.entity_id,source.revision_id)
        item.update(mandatory=key in mandatory, rank_score=score(request.query_text, item['name'], item['description']))
        candidates.append(item)
    for item in _knowledge_sources(tx,actor,request,reader or actor):
        source=item['source']
        key=(source.family.value,source.entity_id,source.revision_id)
        if key not in seen:
            candidates.append(item)
            seen[key]=source.content_digest
        elif seen[key]!=source.content_digest:
            raise ContinuityConflict('STALE_CONTENT','A discovered source conflicts with the explicit exact digest')
        else:
            current=next(candidate for candidate in candidates if
                (candidate['source'].family.value,candidate['source'].entity_id,candidate['source'].revision_id)==key)
            current['rank_score']=max(current['rank_score'],item['rank_score'])
            current.setdefault('selection_reason','DATABASE_HYBRID')
    return sorted(candidates, key=lambda item: (not item['mandatory'], -item['rank_score']))


def partial(text, count, token_limit, byte_limit):
    """Return a bounded prefix only for optional, non-structured material."""
    # Structured obligations need the existing extractive derivation, not a
    # prefix that could cut off a constraint or an unfinished requirement.
    if text.lstrip().startswith(('{', '[')):
        return None
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        part = text[:middle]
        if count(part) <= token_limit and len(part.encode('utf-8')) <= byte_limit:
            low = middle
        else:
            high = middle - 1
    return text[:low] or None
