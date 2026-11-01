"""Revisioned Agent asset eligibility; every use rechecks source authority."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from pydantic import Field, StrictInt, model_validator
from . import connection, identity_api, continuity_work as work
from .agent_extension_contracts import identifier
from .continuity_contracts import Contract, Identifier, Reason, SourceRef, AssemblyRequest, request_digest
from .continuity_state import ContinuityConflict, require_idempotent_request


class AssetBinding(Contract):
    security_domain_id: Identifier
    agent_id: Identifier
    source: SourceRef
    purpose: Reason
    priority: Annotated[StrictInt, Field(ge=0, le=100)] = 50
    resolution_policy: Literal['PINNED', 'CURRENT'] = 'PINNED'
    valid_until: datetime | None = None
    reason: Reason
    idempotency_key: Identifier

    @model_validator(mode='after')
    def source_policy(self):
        if self.source.family.value not in {'MEMORY', 'KNOWLEDGE', 'SKILL', 'GRAPH', 'SOURCE'}:
            raise ValueError('Asset bindings support Knowledge, Memory, Skill, code graphs and sources')
        if self.resolution_policy == 'CURRENT' and self.source.family.value in {'GRAPH','SOURCE'}:
            raise ValueError('Captured code graphs and source evidence require an exact pinned revision')
        if self.valid_until is not None and (self.valid_until.tzinfo is None or self.valid_until <= datetime.now(timezone.utc)):
            raise ValueError('Validity must be a future timestamp with an explicit timezone')
        return self


class AssetRevision(AssetBinding):
    expected_version: Annotated[StrictInt, Field(ge=1)]


class AssetState(Contract):
    expected_version: Annotated[StrictInt, Field(ge=1)]
    status: Literal['ACTIVE', 'PAUSED', 'REVOKED']
    reason: Reason
    idempotency_key: Identifier


def schema_statements(dialect):
    if dialect not in {'pg', 'postgresql', 'oracle', 'yashandb'}:
        raise ValueError('unsupported database adapter')
    return [
        "CREATE TABLE CX_AGENT_ASSET_BINDINGS (BINDING_ID VARCHAR(128) PRIMARY KEY, AGENT_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "SECURITY_DOMAIN_ID VARCHAR(128) NOT NULL REFERENCES CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID), OWNER_PRINCIPAL_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "CURRENT_REVISION INTEGER NOT NULL CHECK(CURRENT_REVISION>0), ROW_VERSION INTEGER NOT NULL CHECK(ROW_VERSION>0), "
        "STATUS VARCHAR(16) NOT NULL CHECK(STATUS IN ('ACTIVE','PAUSED','REVOKED')), CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_AGENT_ASSET_REVISIONS (BINDING_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_ASSET_BINDINGS(BINDING_ID), "
        "REVISION_NO INTEGER NOT NULL CHECK(REVISION_NO>0), FAMILY VARCHAR(24) NOT NULL CHECK(FAMILY IN ('MEMORY','KNOWLEDGE','SKILL','GRAPH','SOURCE')), "
        "ENTITY_ID VARCHAR(128) NOT NULL, REVISION_ID VARCHAR(128) NOT NULL, CONTENT_DIGEST VARCHAR(64) NOT NULL, "
        "PURPOSE VARCHAR(1000) NOT NULL, PRIORITY INTEGER NOT NULL CHECK(PRIORITY>=0 AND PRIORITY<=100), "
        "RESOLUTION_POLICY VARCHAR(16) NOT NULL CHECK(RESOLUTION_POLICY IN ('PINNED','CURRENT')), VALID_UNTIL TIMESTAMP, "
        "CREATED_BY VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), REASON VARCHAR(1000) NOT NULL, "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY(BINDING_ID,REVISION_NO))",
        "CREATE TABLE CX_AGENT_ASSET_REQUESTS (ACTOR_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "IDEMPOTENCY_KEY VARCHAR(128) NOT NULL, REQUEST_DIGEST VARCHAR(64) NOT NULL, BINDING_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_ASSET_BINDINGS(BINDING_ID), "
        "RESOURCE_VERSION INTEGER NOT NULL CHECK(RESOURCE_VERSION>0), CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY(ACTOR_ID,IDEMPOTENCY_KEY))",
        "CREATE TABLE CX_CONTEXT_ASSET_USES (ASSEMBLY_ID VARCHAR(128) NOT NULL REFERENCES CX_CONTEXT_ASSEMBLIES(ASSEMBLY_ID), "
        "BINDING_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_ASSET_BINDINGS(BINDING_ID), BINDING_VERSION INTEGER NOT NULL CHECK(BINDING_VERSION>0), "
        "FAMILY VARCHAR(24) NOT NULL, ENTITY_ID VARCHAR(128) NOT NULL, REVISION_ID VARCHAR(128) NOT NULL, CONTENT_DIGEST VARCHAR(64) NOT NULL, "
        "PRIMARY KEY(ASSEMBLY_ID,BINDING_ID))",
    ]


def _agent(tx, actor, domain, agent, *, write=False):
    work._authorize(tx, actor, domain, write=write)
    work._authorize(tx, agent, domain, write=False)
    principal = tx.query_one("SELECT PRINCIPAL_TYPE,STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:agent", {'agent': agent})
    if not principal or principal['principal_type'] != 'AGENT' or principal['status'] != 'ACTIVE':
        raise PermissionError('Agent assets access denied')
    action = 'agents.operate' if write else 'agents.read'
    access = identity_api.effective_access(actor, action, resource={'security_domain_id': domain})
    if access.get('decision') != 'ALLOW' or (actor != agent and not identity_api._agent_visible_to(actor, agent)):
        raise PermissionError('Agent assets access denied')


def _source(tx, actor, agent, domain, source, policy='PINNED', *, metadata_only=False):
    from .continuity_sources import resolve
    from .context_selection import metadata
    source = source if isinstance(source, SourceRef) else SourceRef.model_validate(source)
    if policy == 'CURRENT':
        family = source.family.value
        if family == 'MEMORY':
            current = tx.query_one("SELECT v.VERSION_ID AS REVISION_ID,v.CONTENT_DIGEST FROM CX_MEMORY_FAMILIES f "
                                   "JOIN CX_MEMORY_VERSIONS v ON v.VERSION_ID=f.CURRENT_VERSION_ID WHERE f.FAMILY_ID=:entity", {'entity': source.entity_id})
        elif family == 'SOURCE':
            current = tx.query_one("SELECT r.REVISION_ID,r.CONTENT_DIGEST FROM CX_AGENT_SOURCE_REVISIONS r JOIN CX_AGENT_SOURCES s "
                                   "ON s.CURRENT_REVISION_ID=r.REVISION_ID WHERE s.SOURCE_ID=:entity", {'entity': source.entity_id})
        else:
            current = tx.query_one("SELECT r.REVISION_ID,r.CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACTS a "
                                   "JOIN CX_CONTINUITY_ARTIFACT_REVS r ON r.ARTIFACT_ID=a.ARTIFACT_ID AND r.REVISION_ID=a.CURRENT_REVISION_ID "
                                   "WHERE a.ARTIFACT_ID=:entity AND a.FAMILY=:family", {'entity': source.entity_id, 'family': family})
        if not current:
            raise PermissionError('Configured asset is unavailable')
        source = SourceRef(family=family, entity_id=source.entity_id, revision_id=current['revision_id'], content_digest=current['content_digest'])
    if metadata_only:
        value = metadata(tx, actor, domain, source)
        metadata(tx, agent, domain, source)
        return {'source': source.model_dump(mode='json'), 'name': value['name']}
    value = resolve(tx, actor, domain, source)
    resolve(tx, agent, domain, source)
    return {**value, 'source': source.model_dump(mode='json')}


def _lock(tx, actor, binding_id, *, write=False, _root=None):
    root = (_root if _root is not None else tx.query_one("SELECT * FROM CX_AGENT_ASSET_BINDINGS WHERE BINDING_ID=:binding" + (' FOR UPDATE' if write else ''), {'binding': binding_id}))
    if not root or root.get('binding_id')!=binding_id:
        raise PermissionError('Agent assets access denied')
    _agent(tx, actor, root['security_domain_id'], root['agent_id'], write=write)
    if actor != root['owner_principal_id']:
        access = identity_api.effective_access(actor, 'agents.operate', resource={'security_domain_id': root['security_domain_id']})
        if 'ALL' not in access.get('scopes', []):
            raise PermissionError('Agent assets access denied')
    return root


def _replay(tx, actor, operation, request, binding_id=None):
    prior = tx.query_one("SELECT * FROM CX_AGENT_ASSET_REQUESTS WHERE ACTOR_ID=:actor AND IDEMPOTENCY_KEY=:idem", {'actor': actor, 'idem': request.idempotency_key})
    if prior:
        require_idempotent_request(prior['request_digest'], request_digest(actor, operation + ':' + str(binding_id or ''), request))
        _lock(tx, actor, prior['binding_id'], write=True)
        return {'binding_id': prior['binding_id'], 'version': int(prior['resource_version']), 'replayed': True}


def _record(tx, actor, operation, request, binding_id, version, target=None):
    tx.execute("INSERT INTO CX_AGENT_ASSET_REQUESTS(ACTOR_ID,IDEMPOTENCY_KEY,REQUEST_DIGEST,BINDING_ID,RESOURCE_VERSION) "
               "VALUES(:actor,:idem,:digest,:binding,:version)",
               {'actor': actor, 'idem': request.idempotency_key, 'digest': request_digest(actor, operation + ':' + str(target or ''), request),
                'binding': binding_id, 'version': version})
    identity_api._audit_tx(tx, actor, operation, 'AGENT_ASSET', binding_id, 'ALLOW', request.reason)
    return {'binding_id': binding_id, 'version': version, 'replayed': False}


def _revision(tx, actor, binding_id, number, request):
    source = request.source
    tx.execute("INSERT INTO CX_AGENT_ASSET_REVISIONS(BINDING_ID,REVISION_NO,FAMILY,ENTITY_ID,REVISION_ID,CONTENT_DIGEST,PURPOSE,PRIORITY,RESOLUTION_POLICY,VALID_UNTIL,CREATED_BY,REASON) "
               "VALUES(:binding,:v_revision_no,:family,:entity,:revision,:digest,:purpose,:priority,:resolution,:valid_until,:actor,:reason)",
               {'binding': binding_id, 'v_revision_no': number, 'family': source.family.value, 'entity': source.entity_id, 'revision': source.revision_id,
                'digest': source.content_digest, 'purpose': request.purpose, 'priority': request.priority, 'resolution': request.resolution_policy,
                'valid_until': request.valid_until.astimezone(timezone.utc).replace(tzinfo=None) if request.valid_until else None, 'actor': actor, 'reason': request.reason})


def bind(actor, value):
    request = AssetBinding.model_validate(value)
    def perform(tx):
        _agent(tx, actor, request.security_domain_id, request.agent_id, write=True)
        _source(tx, actor, request.agent_id, request.security_domain_id, request.source)
        prior = _replay(tx, actor, 'ASSET_BIND', request)
        if prior:
            return prior
        binding_id = identifier('AB')
        tx.execute("INSERT INTO CX_AGENT_ASSET_BINDINGS(BINDING_ID,AGENT_ID,SECURITY_DOMAIN_ID,OWNER_PRINCIPAL_ID,CURRENT_REVISION,ROW_VERSION,STATUS) "
                   "VALUES(:binding,:agent,:domain,:actor,1,1,'ACTIVE')",
                   {'binding': binding_id, 'agent': request.agent_id, 'domain': request.security_domain_id, 'actor': actor})
        _revision(tx, actor, binding_id, 1, request)
        return _record(tx, actor, 'ASSET_BIND', request, binding_id, 1)
    return connection.execute_transaction_callback(perform)


def revise(actor, binding_id, value):
    request = AssetRevision.model_validate(value)
    def perform(tx):
        root = _lock(tx, actor, binding_id, write=True)
        if root['agent_id'] != request.agent_id or root['security_domain_id'] != request.security_domain_id:
            raise PermissionError('Binding cannot change Agent or security domain')
        _source(tx, actor, root['agent_id'], root['security_domain_id'], request.source)
        prior = _replay(tx, actor, 'ASSET_REVISE', request, binding_id)
        if prior:
            return prior
        if int(root['row_version']) != request.expected_version or root['status'] == 'REVOKED':
            raise ContinuityConflict('STALE_BINDING', 'Binding version changed or was revoked')
        _revision(tx, actor, binding_id, int(root['current_revision']) + 1, request)
        tx.execute("UPDATE CX_AGENT_ASSET_BINDINGS SET CURRENT_REVISION=CURRENT_REVISION+1,ROW_VERSION=ROW_VERSION+1 WHERE BINDING_ID=:binding", {'binding': binding_id})
        return _record(tx, actor, 'ASSET_REVISE', request, binding_id, request.expected_version + 1, binding_id)
    return connection.execute_transaction_callback(perform)


def change_state(actor, binding_id, value):
    request = AssetState.model_validate(value)
    def perform(tx):
        root = _lock(tx, actor, binding_id, write=True)
        prior = _replay(tx, actor, 'ASSET_STATE', request, binding_id)
        if prior:
            return prior
        if int(root['row_version']) != request.expected_version or root['status'] == 'REVOKED':
            raise ContinuityConflict('STALE_BINDING', 'Binding version changed or was revoked')
        tx.execute("UPDATE CX_AGENT_ASSET_BINDINGS SET STATUS=:status,ROW_VERSION=ROW_VERSION+1 WHERE BINDING_ID=:binding", {'status': request.status, 'binding': binding_id})
        return _record(tx, actor, 'ASSET_STATE', request, binding_id, request.expected_version + 1, binding_id)
    return connection.execute_transaction_callback(perform)


def load(actor, binding_id, *, metadata_only=False, transaction=None):
    def perform(tx):
        root = _lock(tx, actor, binding_id)
        if root['status'] != 'ACTIVE':
            raise PermissionError('Configured asset is inactive')
        # Revisions store UTC-naive instants, independent of the DB session zone.
        revision = tx.query_one("SELECT * FROM CX_AGENT_ASSET_REVISIONS WHERE BINDING_ID=:binding AND REVISION_NO=:revision "
                                "AND (VALID_UNTIL IS NULL OR VALID_UNTIL>:utc_now)",
                                {'binding': binding_id, 'revision': root['current_revision'],
                                 'utc_now': datetime.now(timezone.utc).replace(tzinfo=None)})
        if not revision:
            raise PermissionError('Configured asset expired')
        value = _source(tx, actor, root['agent_id'], root['security_domain_id'],
                        {key: revision[key] for key in ('family', 'entity_id', 'revision_id', 'content_digest')},
                        revision['resolution_policy'], metadata_only=metadata_only)
        return {'binding_id': binding_id, 'version': int(root['row_version']), 'purpose': revision['purpose'],
                'priority': int(revision['priority']), 'resolution_policy': revision['resolution_policy'],
                **value, 'binding_grants_authority': False}
    return perform(transaction) if transaction else connection.execute_transaction_callback(perform)


def _batch_records(tx,identifiers,*,lock=True):
    from .continuity_sources import read_ids
    roots={row['binding_id']:row for row in read_ids(tx,
        "SELECT * FROM CX_AGENT_ASSET_BINDINGS WHERE BINDING_ID IN ({ids}) ORDER BY BINDING_ID"+(' FOR UPDATE' if lock else ''),identifiers)}
    revisions={row['binding_id']:row for row in read_ids(tx,
        "SELECT r.* FROM CX_AGENT_ASSET_REVISIONS r JOIN CX_AGENT_ASSET_BINDINGS b ON b.BINDING_ID=r.BINDING_ID "
        "AND b.CURRENT_REVISION=r.REVISION_NO WHERE r.BINDING_ID IN ({ids})",identifiers)}
    return roots,revisions


def load_many(actor,binding_ids,*,metadata_only=False,transaction=None,omit_denied=False):
    """Batch original binding/revision inputs; every source keeps its reader.

    This is eligibility, never a grant. Every full load retains the canonical
    per-source authority; CURRENT bindings retain their ordinary resolver.
    """
    from .context_selection import metadata_many
    from .continuity_sources import resolve_many
    identifiers=list(dict.fromkeys(binding_ids))
    if len(identifiers)>100:raise ValueError('A bounded binding list is required')
    if not identifiers:return {}
    def perform(tx):
        work._lock_actor(tx,actor)
        preliminary,_unused=_batch_records(tx,identifiers,lock=False)
        authorized_groups=set()
        for domain,agent in sorted({(row['security_domain_id'],row['agent_id']) for row in preliminary.values()}):
            try:
                _agent(tx,actor,domain,agent)
                authorized_groups.add((domain,agent))
            except PermissionError:
                if not omit_denied:raise
        readable=[identifier for identifier in identifiers if identifier in preliminary
            and (preliminary[identifier]['security_domain_id'],preliminary[identifier]['agent_id']) in authorized_groups]
        roots,revisions=_batch_records(tx,readable)
        if roots!={identifier:preliminary[identifier] for identifier in readable}:
            raise PermissionError('Configured assets changed before batch locking')
        allowed={};groups={};result={}
        for identifier in identifiers:
            try:
                if identifier not in roots:raise PermissionError('Agent assets access denied')
                root=_lock(tx,actor,identifier,_root=roots[identifier])
                if root['status']!='ACTIVE':raise PermissionError('Configured asset is inactive')
                revision=revisions.get(identifier)
                if not revision:raise PermissionError('Configured asset expired')
                until=revision.get('valid_until')
                if isinstance(until,str):until=datetime.fromisoformat(until.replace('Z','+00:00'))
                if until is not None:
                    until=until.replace(tzinfo=timezone.utc) if until.tzinfo is None else until.astimezone(timezone.utc)
                    if until<=datetime.now(timezone.utc):raise PermissionError('Configured asset expired')
                allowed[identifier]=(root,revision)
                if revision['resolution_policy']=='PINNED':
                    groups.setdefault((root['security_domain_id'],root['agent_id']),[]).append(identifier)
                else:
                    value=_source(tx,actor,root['agent_id'],root['security_domain_id'],
                        {key:revision[key] for key in ('family','entity_id','revision_id','content_digest')},
                        revision['resolution_policy'],metadata_only=metadata_only)
                    result[identifier]=value
            except PermissionError:
                if not omit_denied:raise
        for (domain,agent),members in groups.items():
            sources=[{key:allowed[identifier][1][key] for key in ('family','entity_id','revision_id','content_digest')} for identifier in members]
            loader=metadata_many if metadata_only else resolve_many
            human=loader(tx,actor,domain,sources,omit_denied=omit_denied)
            recipient=loader(tx,agent,domain,sources,omit_denied=omit_denied)
            for identifier,source,visible,received in zip(members,sources,human,recipient):
                if visible is not None and received is not None:
                    result[identifier]=(dict(source=source,name=visible['name']) if metadata_only else dict(visible,source=source))
        if _batch_records(tx,readable)!=(roots,revisions):
            raise PermissionError('Configured assets changed during batch loading')
        for domain,agent in sorted({(allowed[identifier][0]['security_domain_id'],allowed[identifier][0]['agent_id']) for identifier in result}):
            _agent(tx,actor,domain,agent)
            if any(actor!=allowed[identifier][0]['owner_principal_id'] for identifier in result
                    if allowed[identifier][0]['security_domain_id']==domain and allowed[identifier][0]['agent_id']==agent):
                access=identity_api.effective_access(actor,'agents.operate',resource={'security_domain_id':domain})
                if 'ALL' not in access.get('scopes',[]):raise PermissionError('Agent assets access denied')
        for identifier,value in list(result.items()):
            root,revision=allowed[identifier]
            until=revision.get('valid_until')
            if isinstance(until,str):until=datetime.fromisoformat(until.replace('Z','+00:00'))
            if until is not None:
                until=until.replace(tzinfo=timezone.utc) if until.tzinfo is None else until.astimezone(timezone.utc)
                if until<=datetime.now(timezone.utc):raise PermissionError('Configured asset expired')
            result[identifier]=dict(binding_id=identifier,version=int(root['row_version']),purpose=revision['purpose'],
                priority=int(revision['priority']),resolution_policy=revision['resolution_policy'],**value,binding_grants_authority=False)
        return result
    return perform(transaction) if transaction is not None else connection.execute_transaction_callback(perform)


def list_bindings(actor, domain, agent, *, limit=20, after=''):
    if isinstance(limit, bool) or not 1 <= int(limit) <= 100:
        raise ValueError('Invalid binding inventory limit')
    def perform(tx):
        _agent(tx, actor, domain, agent)
        params = {'agent': agent, 'domain': domain, 'page_limit': int(limit) + 1}
        sql = "SELECT BINDING_ID FROM CX_AGENT_ASSET_BINDINGS WHERE AGENT_ID=:agent AND SECURITY_DOMAIN_ID=:domain AND STATUS='ACTIVE'"
        if after:
            sql += " AND BINDING_ID>:after"
            params['after'] = after
        rows = tx.query(sql + " ORDER BY BINDING_ID" + identity_api._limit_clause('page_limit'), params)
        identifiers=[row['binding_id'] for row in rows[:int(limit)]]
        loaded=load_many(actor,identifiers,metadata_only=True,transaction=tx,omit_denied=True)
        items=[loaded[identifier] for identifier in identifiers if identifier in loaded]
        return {'items': items, 'next_cursor': rows[int(limit)-1]['binding_id'] if len(rows) > int(limit) else None}
    return connection.execute_transaction_callback(perform)


def assemble(actor, binding_ids, value):
    """Build a normal immutable assembly from exact freshly checked bindings."""
    from . import continuity_assembly
    value = AssemblyRequest.model_validate(value).model_dump(mode='json')
    if not isinstance(binding_ids, (list, tuple)) or len(binding_ids) > 100:
        raise ValueError('A bounded binding list is required')
    def perform(tx):
        sources,bindings = [],[]
        loaded=load_many(actor,binding_ids,transaction=tx)
        for binding_id in dict.fromkeys(binding_ids):
            item = loaded[binding_id]
            root = _lock(tx, actor, binding_id)
            if root['security_domain_id'] != value['security_domain_id']:
                raise PermissionError('Asset assembly must retain its configured domain')
            sources.append(item['source'])
            bindings.append(item)
        result=continuity_assembly.assemble(actor, {**value, 'sources': [*value.get('sources', []), *sources]}, transaction=tx,_asset_scope=True)
        prior=tx.query("SELECT BINDING_ID FROM CX_CONTEXT_ASSET_USES WHERE ASSEMBLY_ID=:assembly",{'assembly':result['assembly_id']})
        if prior:
            if {row['binding_id'] for row in prior}!={item['binding_id'] for item in bindings}:
                raise ContinuityConflict('IDEMPOTENCY_CONFLICT','Asset bindings differ from the prepared assembly')
            return result
        for item in bindings:
            tx.execute("INSERT INTO CX_CONTEXT_ASSET_USES(ASSEMBLY_ID,BINDING_ID,BINDING_VERSION,FAMILY,ENTITY_ID,REVISION_ID,CONTENT_DIGEST) "
                       "VALUES(:assembly,:binding,:version,:family,:entity,:revision,:digest)",
                       {'assembly':result['assembly_id'],'binding':item['binding_id'],'version':item['version'],
                        'family':item['source']['family'],'entity':item['source']['entity_id'],'revision':item['source']['revision_id'],'digest':item['source']['content_digest']})
        return result
    return connection.execute_transaction_callback(perform)


def revalidate_assembly(tx,actor,assembly_id):
    uses=tx.query("SELECT * FROM CX_CONTEXT_ASSET_USES WHERE ASSEMBLY_ID=:assembly",{'assembly':assembly_id})
    loaded=load_many(actor,[use['binding_id'] for use in uses],transaction=tx)
    for use in uses:
        item=loaded[use['binding_id']]
        source=item['source']
        if item['version']!=int(use['binding_version']) or any(source[key]!=use[key] for key in ('family','entity_id','revision_id','content_digest')):
            raise ContinuityConflict('STALE_BINDING','An assembly asset binding changed; prepare a new assembly')
