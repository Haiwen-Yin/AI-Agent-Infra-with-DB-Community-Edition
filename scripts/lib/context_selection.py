"""Metadata-first selection and deterministic model-input budget contracts.

Tokenizers are resolved from an installed, known implementation only. The
conservative fallback counts each UTF-8 byte as one token, never characters.
No tokenizer is downloaded, nor is caller-supplied code loaded.
"""
from __future__ import annotations

import re
import unicodedata
from . import identity_api, continuity_work as work
from .continuity_contracts import SourceRef
from .continuity_state import ContinuityConflict


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


def budget(request):
    count, method = counter(request.model_name)
    system, tools = count(request.system_text), count(request.tool_text)
    window = request.context_window or (request.token_budget + system + tools + request.output_reserve)
    remaining = window - system - tools - request.output_reserve
    if remaining < 0:
        raise ContinuityConflict('CONTEXT_RESERVES_EXCEED_WINDOW', 'System, tool and output reserves exceed the context window')
    return dict(count=count, count_method=method, context_window=window, system_tokens=system,
                tool_tokens=tools, output_reserve=request.output_reserve,
                source_budget=min(remaining, request.token_budget), byte_budget=request.byte_budget)


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


def metadata(tx, actor, domain, source):
    """Authorize exact source metadata before returning a relevance signal.

    Cross-domain publication bodies are intentionally left to their existing
    resolver; selection is not a new publication or ownership bypass.
    """
    from .continuity_sources import locate
    source = source if isinstance(source, SourceRef) else SourceRef.model_validate(source)
    located = locate(tx, source)
    work._authorize(tx, actor, domain, write=False)
    if located['security_domain_id'] != domain:
        raise PermissionError('An explicit context publication is required')
    family = source.family.value
    if family in {'MEMORY', 'KNOWLEDGE', 'EXPERIENCE', 'SKILL'}:
        action = {'MEMORY': 'memory.read', 'KNOWLEDGE': 'knowledge.read',
                  'EXPERIENCE': 'knowledge.read', 'SKILL': 'skills.read'}[family]
        access = identity_api.effective_access(actor, action, resource={'security_domain_id': domain})
        if access.get('decision') != 'ALLOW':
            raise PermissionError('Source access denied')
        # Memory ownership/scopes are governed by its existing reader, which
        # also supports explicitly assigned domain members. Asset eligibility
        # must neither replace that authority nor narrow it to owner/ALL.
        if family != 'MEMORY' and located['owner_principal_id'] != actor and 'ALL' not in access.get('scopes', []):
            raise PermissionError('Source access denied')
    if family == 'MEMORY':
        from . import memory_lifecycle as memory
        record = tx.query_one("SELECT v.TITLE,v.CONTENT_DIGEST,v.LIFECYCLE_STATE,v.VALID_UNTIL,v.OWNER_PRINCIPAL_ID,v.SECURITY_DOMAIN_ID,"
                              "v.MEMORY_SCOPE,v.CLASSIFICATION FROM CX_MEMORY_VERSIONS v JOIN CX_MEMORY_FAMILIES f ON f.FAMILY_ID=v.FAMILY_ID "
                              "JOIN CX_MEMORY_VERSIONS c ON c.VERSION_ID=f.CURRENT_VERSION_ID WHERE v.FAMILY_ID=:entity AND v.VERSION_ID=:revision "
                              "AND c.LIFECYCLE_STATE IN ('ACTIVE','STALE','CONFLICTED','MIGRATED') "
                              "AND (v.VALID_UNTIL IS NULL OR v.VALID_UNTIL>CURRENT_TIMESTAMP)",
                              {'entity': source.entity_id, 'revision': source.revision_id})
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
        record = tx.query_one("SELECT e.TITLE,r.CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACT_REVS r JOIN ENTITIES e ON "
                              "CAST(e.ENTITY_ID AS VARCHAR(128))=r.NATIVE_ENTITY_ID WHERE r.ARTIFACT_ID=:entity AND r.REVISION_ID=:revision",
                              {'entity': source.entity_id, 'revision': source.revision_id})
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
    return {'name': str(record.get('title') or family), 'description': '', 'source': source}


def select_sources(tx, actor, request):
    mandatory = {(s.family.value, s.entity_id, s.revision_id) for s in request.mandatory_sources}
    seen, candidates = set(), []
    for source in (*request.mandatory_sources, *request.sources):
        key = (source.family.value, source.entity_id, source.revision_id)
        if key in seen:
            continue
        seen.add(key)
        item = metadata(tx, actor, request.security_domain_id, source)
        item.update(mandatory=key in mandatory, rank_score=score(request.query_text, item['name'], item['description']))
        candidates.append(item)
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
