"""Bounded read-only source imports on canonical tasks and candidate review.

Sources never execute repository code. Source facts, candidate references and
the checkpoint commit in one transaction after the current lease and authority
are checked again. Published content remains behind ordinary review/publication.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import PurePosixPath
import re
import socket
import ssl
from urllib.parse import urlsplit, quote, unquote
from typing import Annotated, Literal
from pydantic import Field, StrictInt, model_validator
from . import connection, identity_api, continuity_work as work, task_continuity
from .agent_extension_contracts import identifier, canonical, digest, safe_key
from .connection_crypto import encrypt_section, decrypt_section
from .continuity_contracts import Contract, Identifier, Reason, SourceRef, NewCandidate, request_digest
from .continuity_state import ContinuityConflict, ContinuityError, require_idempotent_request


class SourceConfiguration(Contract):
    security_domain_id: Identifier
    agent_id: Identifier
    kind: Literal['DOCUMENT', 'GITHUB']
    endpoint: Annotated[str, Field(min_length=1, max_length=2000)]
    pinned_commit: Annotated[str, Field(max_length=40)] = ''
    paths: Annotated[tuple[Annotated[str, Field(max_length=500)], ...], Field(min_length=1, max_length=50)] = ('/',)
    credential_ref: Annotated[str, Field(max_length=100)] = ''
    content_types: Annotated[tuple[str, ...], Field(min_length=1, max_length=5)] = ('text/plain', 'text/markdown', 'text/html')
    max_bytes: Annotated[StrictInt, Field(ge=128, le=262144)] = 16384
    max_attempts: Annotated[StrictInt, Field(ge=1, le=5)] = 3
    reason: Reason
    idempotency_key: Identifier

    @model_validator(mode='after')
    def contract(self):
        endpoint = validate_endpoint(self.endpoint)
        parsed = urlsplit(endpoint)
        if self.kind == 'GITHUB':
            if parsed.hostname != 'github.com' or not re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', parsed.path.rstrip('/')):
                raise ValueError('Git sources require an exact https://github.com/owner/repository URL')
            if not re.fullmatch(r'[0-9a-f]{40}', self.pinned_commit):
                raise ValueError('Git sources require a pinned full commit SHA')
        elif self.pinned_commit:
            raise ValueError('Document sources use response versions, not Git commits')
        for path in self.paths:
            validate_path(path)
        if self.kind == 'DOCUMENT' and self.paths != ('/',):
            raise ValueError('A document source references its exact configured URL')
        if self.credential_ref:
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,99}',self.credential_ref):
                raise ValueError('Credential references use uppercase host-managed keys, e.g. DOCS_READ')
        if any(value not in {'text/plain', 'text/markdown', 'text/html', 'application/json'} for value in self.content_types):
            raise ValueError('Unsupported source content type')
        return self


class SyncRequest(Contract):
    task_id: Identifier | None = None
    reason: Reason
    idempotency_key: Identifier


class SourceState(Contract):
    expected_version: Annotated[StrictInt, Field(ge=1)]
    status: Literal['ACTIVE', 'PAUSED', 'REVOKED', 'RETIRED']
    reason: Reason
    idempotency_key: Identifier


def schema_statements(dialect):
    if dialect not in {'pg', 'postgresql', 'oracle', 'yashandb'}:
        raise ValueError('unsupported database adapter')
    body = 'TEXT' if dialect in {'pg', 'postgresql'} else 'CLOB'
    return [
        "CREATE TABLE CX_AGENT_SOURCES (SOURCE_ID VARCHAR(128) PRIMARY KEY, AGENT_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "OWNER_PRINCIPAL_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), SECURITY_DOMAIN_ID VARCHAR(128) NOT NULL REFERENCES CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID), "
        "SOURCE_KIND VARCHAR(16) NOT NULL CHECK(SOURCE_KIND IN ('DOCUMENT','GITHUB')), ENDPOINT VARCHAR(2000) NOT NULL, PINNED_COMMIT VARCHAR(40), "
        "CREDENTIAL_REF VARCHAR(100), CONTENT_POLICY_DIGEST VARCHAR(64) NOT NULL, CONFIG_DIGEST VARCHAR(64) NOT NULL, "
        "ROW_VERSION INTEGER NOT NULL CHECK(ROW_VERSION>0), MAX_BYTES INTEGER NOT NULL CHECK(MAX_BYTES>=128 AND MAX_BYTES<=262144), "
        "MAX_ATTEMPTS INTEGER NOT NULL CHECK(MAX_ATTEMPTS>=1 AND MAX_ATTEMPTS<=5), "
        "STATUS VARCHAR(16) NOT NULL CHECK(STATUS IN ('ACTIVE','PAUSED','REVOKED','RETIRED')), CURRENT_REVISION_ID VARCHAR(128), "
        "CHECKPOINT_DIGEST VARCHAR(64), CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_AGENT_SOURCE_PATHS (SOURCE_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_SOURCES(SOURCE_ID), "
        "PATH_NO INTEGER NOT NULL CHECK(PATH_NO>0), SOURCE_PATH VARCHAR(500) NOT NULL, PRIMARY KEY(SOURCE_ID,PATH_NO), UNIQUE(SOURCE_ID,SOURCE_PATH))",
        "CREATE TABLE CX_AGENT_SOURCE_TYPES (SOURCE_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_SOURCES(SOURCE_ID), "
        "CONTENT_TYPE VARCHAR(100) NOT NULL, PRIMARY KEY(SOURCE_ID,CONTENT_TYPE))",
        "CREATE TABLE CX_AGENT_SOURCE_REVISIONS (REVISION_ID VARCHAR(128) PRIMARY KEY, SOURCE_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_SOURCES(SOURCE_ID), "
        "SOURCE_VERSION VARCHAR(256) NOT NULL, SOURCE_PATH VARCHAR(500) NOT NULL, TITLE VARCHAR(500) NOT NULL, CONTENT_DIGEST VARCHAR(64) NOT NULL, "
        f"CONTENT_CIPHER {body} NOT NULL, OBSERVED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, EFFECTIVE_AT TIMESTAMP, "
        "LIFECYCLE_STATE VARCHAR(16) NOT NULL CHECK(LIFECYCLE_STATE IN ('AVAILABLE','UNAVAILABLE','RETIRED')), "
        "UNIQUE(SOURCE_ID,SOURCE_VERSION,SOURCE_PATH,CONTENT_DIGEST))",
        "CREATE TABLE CX_AGENT_SYNC_JOBS (JOB_ID VARCHAR(128) PRIMARY KEY, SOURCE_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_SOURCES(SOURCE_ID), "
        "CONTINUITY_ID VARCHAR(128) NOT NULL UNIQUE REFERENCES CX_TASK_CONTINUITY_LINKS(CONTINUITY_ID), "
        "REQUESTED_BY VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), CONFIG_DIGEST VARCHAR(64) NOT NULL, REQUEST_DIGEST VARCHAR(64) NOT NULL, "
        "STATUS VARCHAR(16) NOT NULL CHECK(STATUS IN ('PENDING','RUNNING','SUCCEEDED','FAILED','BLOCKED')), "
        "ATTEMPT_COUNT INTEGER NOT NULL CHECK(ATTEMPT_COUNT>=0), ERROR_CODE VARCHAR(64), CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_AGENT_SYNC_IMPORTS (JOB_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_SYNC_JOBS(JOB_ID), "
        "REVISION_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_SOURCE_REVISIONS(REVISION_ID), CANDIDATE_ID VARCHAR(128) NOT NULL REFERENCES CX_ARTIFACT_CANDIDATES(CANDIDATE_ID), "
        "CANDIDATE_REVISION INTEGER NOT NULL CHECK(CANDIDATE_REVISION>0), PRIMARY KEY(JOB_ID,REVISION_ID))",
        "CREATE TABLE CX_AGENT_SOURCE_REQUESTS (ACTOR_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "IDEMPOTENCY_KEY VARCHAR(128) NOT NULL, REQUEST_DIGEST VARCHAR(64) NOT NULL, SOURCE_ID VARCHAR(128) NOT NULL REFERENCES CX_AGENT_SOURCES(SOURCE_ID), "
        "JOB_ID VARCHAR(128) REFERENCES CX_AGENT_SYNC_JOBS(JOB_ID), RESOURCE_VERSION INTEGER NOT NULL CHECK(RESOURCE_VERSION>0), "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY(ACTOR_ID,IDEMPOTENCY_KEY))",
    ]


def validate_endpoint(value):
    if not isinstance(value, str) or any(ord(char) <= 32 for char in value) or '\\' in value:
        raise ValueError('A credential-free configured HTTPS URL is required')
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Invalid HTTPS port') from exc
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or port not in {None, 443}:
        raise ValueError('Only credential-free HTTPS on port 443 is supported')
    if parsed.hostname.endswith('.') or '%' in parsed.netloc or parsed.hostname.lower() in {'metadata.google.internal', 'localhost'}:
        raise ValueError('Unsupported source host')
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError('Non-public source addresses are prohibited')
    return value


def validate_path(path):
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path or len(path) > 500:
        raise ValueError('Invalid source path')
    decoded = unquote(path)
    if decoded != path or any(part in {'.', '..', '.git'} for part in path.strip('/').split('/')) or path.startswith('//'):
        raise ValueError('Encoded or escaping paths are prohibited')
    if str(PurePosixPath('/' + path.lstrip('/'))).rstrip('/') != ('/' + path.lstrip('/')).rstrip('/'):
        raise ValueError('Source paths must be canonical')
    return path


def _credential(source):
    reference = source.get('credential_ref')
    if not reference:
        return {}
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,99}',reference):
        raise PermissionError('Source credential reference is invalid')
    # Values live only in host-managed environment state, never in a DB
    # request, source configuration, candidate, cursor or error report.
    token = os.environ.get('CX_SOURCE_CREDENTIAL_' + reference)
    if not token or any(ord(char) < 32 for char in token):
        raise PermissionError('Source credential is unavailable')
    return {'Authorization': 'Bearer ' + token}


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=15, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        raw = socket.create_connection((self._address, 443), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def https_get(url, *, allowed_hosts, headers=None, max_bytes=262144):
    """Resolve once, pin a public address and preserve TLS hostname validation.

    Redirects are rejected rather than forwarding a credential to another URL.
    No ambient proxy, cookies, netrc, helpers or filesystem access are used.
    """
    validate_endpoint(url)
    parsed = urlsplit(url)
    if parsed.hostname not in allowed_hosts:
        raise PermissionError('Source host is outside its configured contract')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise PermissionError('Non-public source resolution is prohibited')
    request_headers = {'Accept': 'application/json,text/plain,text/markdown,text/html', 'User-Agent': 'Chuanxu-Source-Sync', 'Accept-Encoding': 'identity'}
    for key, value in (headers or {}).items():
        if key not in {'Authorization', 'If-None-Match'} or not isinstance(value, str) or any(ord(char) < 32 for char in value):
            raise ValueError('Unsupported source request header')
        request_headers[key] = value
    client = _PinnedHTTPS(parsed.hostname, addresses[0][4][0])
    try:
        client.request('GET', (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''), headers=request_headers)
        response = client.getresponse()
        if 300 <= response.status < 400 and response.status != 304:
            raise ValueError('Source redirects are not permitted')
        length = response.getheader('Content-Length')
        if length and (not length.isdecimal() or int(length) > max_bytes):
            raise ValueError('Source response exceeds its byte limit')
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes or response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise ValueError('Source response exceeds its byte or encoding contract')
        return {'status': response.status, 'content_type': response.getheader('Content-Type', '').split(';')[0].strip().lower(),
                'etag': response.getheader('ETag', '')[:256], 'body': body}
    finally:
        client.close()


def _authority(tx, actor, source, *, write=False, active=True):
    from .agent_assets import _agent
    _agent(tx, actor, source['security_domain_id'], source['agent_id'], write=write)
    action = 'knowledge.write' if write else 'knowledge.read'
    access = identity_api.effective_access(actor, action, resource={'security_domain_id': source['security_domain_id']})
    if access.get('decision') != 'ALLOW' or (actor not in {source['owner_principal_id'], source['agent_id']} and 'ALL' not in access.get('scopes', [])):
        raise PermissionError('Source access denied')
    if active and source['status'] != 'ACTIVE':
        raise PermissionError('Source is unavailable')
    if active:
        _credential(source)


def _source(tx, actor, source_id, *, write=False, active=True):
    source = tx.query_one("SELECT * FROM CX_AGENT_SOURCES WHERE SOURCE_ID=:source" + (' FOR UPDATE' if write else ''), {'source': source_id})
    if not source:
        raise PermissionError('Source access denied')
    _authority(tx, actor, source, write=write, active=active)
    return source


def _receipt(tx, actor, operation, request, source_id=''):
    prior = tx.query_one("SELECT * FROM CX_AGENT_SOURCE_REQUESTS WHERE ACTOR_ID=:actor AND IDEMPOTENCY_KEY=:idem", {'actor': actor, 'idem': request.idempotency_key})
    if prior:
        require_idempotent_request(prior['request_digest'], request_digest(actor, operation + ':' + source_id, request))
        _source(tx, actor, prior['source_id'], write=True, active=operation != 'SOURCE_STATE')
        return {'source_id': prior['source_id'], 'job_id': prior['job_id'], 'version': int(prior['resource_version']), 'replayed': True}


def _record(tx, actor, operation, request, source_id, version, *, target='', job_id=None):
    tx.execute("INSERT INTO CX_AGENT_SOURCE_REQUESTS(ACTOR_ID,IDEMPOTENCY_KEY,REQUEST_DIGEST,SOURCE_ID,JOB_ID,RESOURCE_VERSION) "
               "VALUES(:actor,:idem,:digest,:source,:job,:version)",
               {'actor': actor, 'idem': request.idempotency_key, 'digest': request_digest(actor, operation + ':' + target, request),
                'source': source_id, 'job': job_id, 'version': version})
    identity_api._audit_tx(tx, actor, operation, 'AGENT_SOURCE', source_id, 'ALLOW', request.reason)
    return {'source_id': source_id, 'job_id': job_id, 'version': version, 'replayed': False}


def configure(actor, value):
    request = SourceConfiguration.model_validate(value)
    def perform(tx):
        proposed = {'security_domain_id': request.security_domain_id, 'agent_id': request.agent_id,
                    'owner_principal_id': actor, 'status': 'ACTIVE', 'credential_ref': request.credential_ref}
        _authority(tx, actor, proposed, write=True)
        prior = _receipt(tx, actor, 'SOURCE_CREATE', request)
        if prior:
            return prior
        source_id = identifier('AS')
        tx.execute("INSERT INTO CX_AGENT_SOURCES(SOURCE_ID,AGENT_ID,OWNER_PRINCIPAL_ID,SECURITY_DOMAIN_ID,SOURCE_KIND,ENDPOINT,PINNED_COMMIT,CREDENTIAL_REF,CONTENT_POLICY_DIGEST,CONFIG_DIGEST,ROW_VERSION,MAX_BYTES,MAX_ATTEMPTS,STATUS) "
                   "VALUES(:source,:agent,:owner,:domain,:kind,:endpoint,:commit_id,:credential,:policy_digest,:config_digest,1,:max_bytes,:max_attempts,'ACTIVE')",
                   {'source': source_id, 'agent': request.agent_id, 'owner': actor, 'domain': request.security_domain_id, 'kind': request.kind,
                    'endpoint': request.endpoint.rstrip('/') if request.kind == 'GITHUB' else request.endpoint,
                    'commit_id': request.pinned_commit or None, 'credential': request.credential_ref or None,
                    'policy_digest': digest({'paths': tuple(dict.fromkeys(request.paths)), 'types': tuple(sorted(set(request.content_types))), 'max_bytes': request.max_bytes}),
                    'config_digest': request_digest(actor, 'SOURCE_CONFIGURATION', request), 'max_bytes': request.max_bytes, 'max_attempts': request.max_attempts})
        for number, path in enumerate(dict.fromkeys(request.paths), 1):
            tx.execute("INSERT INTO CX_AGENT_SOURCE_PATHS(SOURCE_ID,PATH_NO,SOURCE_PATH) VALUES(:source,:v_path_no,:path)", {'source': source_id, 'v_path_no': number, 'path': path})
        for content_type in dict.fromkeys(request.content_types):
            tx.execute("INSERT INTO CX_AGENT_SOURCE_TYPES(SOURCE_ID,CONTENT_TYPE) VALUES(:source,:content_type)", {'source': source_id, 'content_type': content_type})
        return _record(tx, actor, 'SOURCE_CREATE', request, source_id, 1)
    return connection.execute_transaction_callback(perform)


def change_state(actor, source_id, value):
    request = SourceState.model_validate(value)
    def perform(tx):
        source = _source(tx, actor, source_id, write=True, active=False)
        prior = _receipt(tx, actor, 'SOURCE_STATE', request, source_id)
        if prior:
            return prior
        if source['status'] in {'REVOKED', 'RETIRED'} or int(source['row_version']) != request.expected_version:
            raise ContinuityConflict('SOURCE_STATE_CONFLICT', 'Source version changed or is permanently unavailable')
        tx.execute("UPDATE CX_AGENT_SOURCES SET STATUS=:status,ROW_VERSION=ROW_VERSION+1 WHERE SOURCE_ID=:source", {'status': request.status, 'source': source_id})
        return _record(tx, actor, 'SOURCE_STATE', request, source_id, request.expected_version + 1, target=source_id)
    return connection.execute_transaction_callback(perform)


def enqueue(actor, source_id, value):
    request = SyncRequest.model_validate(value)
    def perform(tx):
        source = _source(tx, actor, source_id, write=True)
        prior = _receipt(tx, actor, 'SOURCE_SYNC', request, source_id)
        if prior:
            return prior
        task_id = task_continuity.ensure_task_root(tx, actor, request.task_id, goal='Configured source synchronization', preferred_agent_id=source['agent_id'])
        job_id = identifier('SJ')
        request_hash = request_digest(actor, 'SOURCE_SYNC:' + source_id, request)
        link = task_continuity.link_protocol_task(tx, actor=actor, security_domain_id=source['security_domain_id'], link_kind='RUNTIME', link_id=job_id,
                                                 canonical_task_id=task_id, idempotency_key='source-sync:' + job_id, request_digest=request_hash,
                                                 input_digest=source['config_digest'], effect_class='REVERSIBLE', reason=request.reason)
        tx.execute("INSERT INTO CX_AGENT_SYNC_JOBS(JOB_ID,SOURCE_ID,CONTINUITY_ID,REQUESTED_BY,CONFIG_DIGEST,REQUEST_DIGEST,STATUS,ATTEMPT_COUNT) "
                   "VALUES(:job,:source,:continuity,:actor,:config_digest,:request_digest,'PENDING',0)",
                   {'job': job_id, 'source': source_id, 'continuity': link['continuity_id'], 'actor': actor, 'config_digest': source['config_digest'],'request_digest':request_hash})
        return _record(tx, actor, 'SOURCE_SYNC', request, source_id, int(source['row_version']), target=source_id, job_id=job_id)
    return connection.execute_transaction_callback(perform)


def _job(tx, actor, job_id, *, write=False):
    job = tx.query_one("SELECT * FROM CX_AGENT_SYNC_JOBS WHERE JOB_ID=:job" + (' FOR UPDATE' if write else ''), {'job': job_id})
    if not job:
        raise PermissionError('Source sync job access denied')
    source = _source(tx, actor, job['source_id'], write=write)
    if actor != job['requested_by'] or source['config_digest'] != job['config_digest']:
        raise PermissionError('Original source sync authority changed')
    return job, source


def read_job(actor, job_id):
    def perform(tx):
        job, source = _job(tx, actor, job_id)
        imports = tx.query("SELECT REVISION_ID,CANDIDATE_ID,CANDIDATE_REVISION FROM CX_AGENT_SYNC_IMPORTS WHERE JOB_ID=:job ORDER BY REVISION_ID", {'job': job_id})
        return {**job, 'imports': imports, 'source_status': source['status'], 'publishes_automatically': False}
    return connection.execute_transaction_callback(perform)


def read_source(actor, source_id):
    def perform(tx):
        source = _source(tx, actor, source_id, active=False)
        source = _configuration(tx, source)
        return {**source, 'credential_value_disclosed': False, 'automatic_publication': False}
    return connection.execute_transaction_callback(perform)


def list_sources(actor, domain, agent, *, limit=20, after=''):
    if isinstance(limit, bool) or not 1<=int(limit)<=100:
        raise ValueError('Invalid source inventory limit')
    def perform(tx):
        from .agent_assets import _agent
        _agent(tx, actor, domain, agent)
        params={'domain':domain,'agent':agent,'page_limit':int(limit)+1}
        sql="SELECT SOURCE_ID FROM CX_AGENT_SOURCES WHERE SECURITY_DOMAIN_ID=:domain AND AGENT_ID=:agent"
        if after:
            sql+=" AND SOURCE_ID>:after"
            params['after']=after
        rows=tx.query(sql+" ORDER BY SOURCE_ID"+identity_api._limit_clause('page_limit'),params)
        items=[]
        for row in rows[:int(limit)]:
            try:
                source=_source(tx,actor,row['source_id'],active=False)
                items.append({key:source[key] for key in ('source_id','source_kind','agent_id','status','row_version','current_revision_id','checkpoint_digest')})
            except PermissionError:
                continue
        return {'items':items,'next_cursor':rows[int(limit)-1]['source_id'] if len(rows)>int(limit) else None}
    return connection.execute_transaction_callback(perform)


def _configuration(tx, source):
    source = dict(source)
    source['paths'] = [row['source_path'] for row in tx.query("SELECT SOURCE_PATH FROM CX_AGENT_SOURCE_PATHS WHERE SOURCE_ID=:source ORDER BY PATH_NO", {'source': source['source_id']})]
    source['types'] = [row['content_type'] for row in tx.query("SELECT CONTENT_TYPE FROM CX_AGENT_SOURCE_TYPES WHERE SOURCE_ID=:source ORDER BY CONTENT_TYPE", {'source': source['source_id']})]
    if source['content_policy_digest'] != digest({'paths': tuple(source['paths']), 'types': tuple(source['types']), 'max_bytes': int(source['max_bytes'])}):
        raise ContinuityError('INTEGRITY_ERROR', 'Source content policy differs from its configured digest')
    return source


def _fetch(source, get):
    headers = _credential(source)
    if source['source_kind'] == 'DOCUMENT':
        result = get(source['endpoint'], allowed_hosts={urlsplit(source['endpoint']).hostname}, headers=headers, max_bytes=int(source['max_bytes']))
        if result['status'] in {401, 403}:
            raise PermissionError('Source access was revoked')
        if result['status'] == 404:
            raise ContinuityError('SOURCE_MISSING', 'Source is temporarily or permanently unavailable; deletion is not inferred')
        if result['status'] != 200 or result['content_type'] not in source['types']:
            raise ValueError('Source response violates its status or content contract')
        text = result['body'].decode('utf-8')
        if '\x00' in text:
            raise ValueError('Binary source text is not supported')
        return [{'path': '/', 'version': result.get('etag') or hashlib.sha256(result['body']).hexdigest(),
                 'title': urlsplit(source['endpoint']).path.rsplit('/', 1)[-1] or urlsplit(source['endpoint']).hostname, 'text': text}]
    repository = urlsplit(source['endpoint']).path.strip('/')
    commit = source['pinned_commit']
    endpoint = 'https://api.github.com/repos/' + repository + '/git/'
    tree = get(endpoint + 'trees/' + commit + '?recursive=1', allowed_hosts={'api.github.com'}, headers=headers, max_bytes=1048576)
    if tree['status'] in {401, 403}:
        raise PermissionError('Source access was revoked')
    if tree['status'] != 200:
        raise ContinuityError('SOURCE_MISSING', 'Pinned source tree is unavailable')
    value = json.loads(tree['body'])
    if value.get('truncated') or not isinstance(value.get('tree'), list):
        raise ValueError('Source tree exceeds its supported bounded window')
    selected = []
    total = 0
    for entry in value['tree']:
        path = entry.get('path')
        validate_path(path)
        if not any(prefix == '/' or path == prefix.strip('/') or path.startswith(prefix.strip('/') + '/') for prefix in source['paths']):
            continue
        if entry.get('mode') in {'120000', '160000'}:
            raise ValueError('Symlink and submodule sources are prohibited')
        if entry.get('type') != 'blob':
            continue
        if PurePosixPath(path).suffix.lower() not in {'.md', '.txt', '.rst', '.html', '.json', '.py', '.sql', '.js', '.ts', '.yaml', '.yml'}:
            continue
        blob = str(entry.get('sha') or '')
        if not re.fullmatch(r'[0-9a-f]{40}', blob) or len(selected) >= 50:
            raise ValueError('Source blob or file-count contract is invalid')
        result = get(endpoint + 'blobs/' + blob, allowed_hosts={'api.github.com'}, headers=headers, max_bytes=int(source['max_bytes']) * 2 + 1024)
        if result['status'] != 200:
            raise ContinuityError('SOURCE_BLOB_UNAVAILABLE', 'A pinned source blob is unavailable')
        data = json.loads(result['body'])
        if data.get('encoding') != 'base64':
            raise ValueError('Source blob encoding is unsupported')
        raw = base64.b64decode(''.join(str(data.get('content', '')).split()), validate=True)
        total += len(raw)
        if total > int(source['max_bytes']) or hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\x00' + raw).hexdigest() != blob:
            raise ValueError('Source blob digest or size is invalid')
        text = raw.decode('utf-8')
        if '\x00' in text:
            raise ValueError('Binary source content is not supported')
        selected.append({'path': path, 'version': commit, 'title': path, 'text': text})
    if not selected:
        raise ContinuityError('SOURCE_EMPTY', 'No eligible pinned text files were found')
    return selected


def _assert_lease(tx, job, attempt, worker):
    lease = tx.query_one("SELECT LEASE_OWNER,FENCING_TOKEN,LEASE_EXPIRES_AT,STATUS FROM CX_TASK_CONTINUITY_LEASES WHERE CONTINUITY_ID=:continuity FOR UPDATE", {'continuity': job['continuity_id']})
    if not lease or lease['status'] != 'ACTIVE' or lease['lease_owner'] != worker or int(lease['fencing_token']) != int(attempt['fencing_token']):
        raise ContinuityConflict('FENCING_MISMATCH', 'Source sync lease is stale')
    expiry = task_continuity._utc_naive(lease['lease_expires_at'])
    if expiry is None or expiry <= task_continuity._now():
        raise ContinuityConflict('LEASE_EXPIRED', 'Source sync lease expired before import')


def run(actor, job_id, *, get=None):
    """Execute one explicit durable sync attempt; no periodic job is enabled."""
    worker='source-sync:'+job_id
    def claim(tx):
        job, source = _job(tx, actor, job_id, write=True)
        if job['status'] == 'SUCCEEDED':
            return {'replayed': True, 'job': job}
        if job['status'] in {'BLOCKED', 'FAILED'} or int(job['attempt_count']) >= int(source['max_attempts']):
            raise ContinuityConflict('SYNC_CLOSED', 'Source sync is blocked or its retry budget is exhausted')
        attempt = task_continuity.claim_attempt(tx, continuity_id=job['continuity_id'], worker_id=worker, business_key=job_id,
                                               request_digest=job['request_digest'], lease_seconds=300)
        if attempt.get('replayed') or attempt.get('reconciliation_required'):
            raise ContinuityConflict('SYNC_ALREADY_CLAIMED', 'The existing attempt must complete or be reconciled')
        tx.execute("UPDATE CX_AGENT_SYNC_JOBS SET STATUS='RUNNING',ATTEMPT_COUNT=ATTEMPT_COUNT+1 WHERE JOB_ID=:job", {'job': job_id})
        return {'job': job, 'source': _configuration(tx, source), 'attempt': attempt}
    claimed = connection.execute_transaction_callback(claim)
    if claimed.get('replayed'):
        return read_job(actor, job_id)
    job, source, attempt = claimed['job'], claimed['source'], claimed['attempt']
    try:
        # Each HTTP request rechecks authority and fencing, including requests
        # made later in a multi-file source import.
        def checked_get(*args, **kwargs):
            def check(tx):
                current_job, current = _job(tx, actor, job_id, write=True)
                _assert_lease(tx, current_job, attempt, worker)
                if current['config_digest'] != source['config_digest']:
                    raise PermissionError('Source configuration changed')
            connection.execute_transaction_callback(check)
            return (get or https_get)(*args, **kwargs)
        documents = _fetch(source, checked_get)
        def commit(tx):
            from . import continuity_candidates
            current_job, current = _job(tx, actor, job_id, write=True)
            _assert_lease(tx, current_job, attempt, worker)
            checkpoint_items, last_revision = [], None
            for document in documents:
                # The bounded candidate DTO stores a full fact. Split source
                # text into exact independently evidenced chunks, never trim.
                chunks = [document['text'][start:start + 3500] for start in range(0, len(document['text']), 3500)] or ['']
                for number, chunk in enumerate(chunks, 1):
                    if not chunk.strip():
                        continue
                    path = document['path'] + ('#chunk-' + str(number) if len(chunks) > 1 else '')
                    if len(path)>500:
                        raise ValueError('Chunked source path exceeds its exact locator limit')
                    content_hash = hashlib.sha256(chunk.encode()).hexdigest()
                    prior = tx.query_one("SELECT REVISION_ID FROM CX_AGENT_SOURCE_REVISIONS WHERE SOURCE_ID=:source AND SOURCE_VERSION=:source_version AND SOURCE_PATH=:path AND CONTENT_DIGEST=:digest",
                                         {'source': source['source_id'], 'source_version': document['version'], 'path': path, 'digest': content_hash})
                    revision = prior['revision_id'] if prior else identifier('SR')
                    if not prior:
                        tx.execute("INSERT INTO CX_AGENT_SOURCE_REVISIONS(REVISION_ID,SOURCE_ID,SOURCE_VERSION,SOURCE_PATH,TITLE,CONTENT_DIGEST,CONTENT_CIPHER,LIFECYCLE_STATE) "
                                   "VALUES(:revision,:source,:source_version,:path,:title,:digest,:cipher,'AVAILABLE')",
                                   {'revision': revision, 'source': source['source_id'], 'source_version': document['version'], 'path': path,
                                    'title': document['title'][:500], 'digest': content_hash, 'cipher': encrypt_section({'text': chunk})})
                    evidence = {'family': 'SOURCE', 'entity_id': source['source_id'], 'revision_id': revision, 'content_digest': content_hash}
                    candidate = continuity_candidates._create_candidate(tx, actor, NewCandidate.model_validate({
                        'security_domain_id': source['security_domain_id'], 'content': {'family': 'KNOWLEDGE', 'title': document['title'][:500], 'body': chunk},
                        'sources': [evidence], 'reason': 'Versioned configured source import; independent review required',
                        'idempotency_key': 'source-import:' + digest([source['source_id'], revision])[:64]}))
                    existing = tx.query_one("SELECT CANDIDATE_ID FROM CX_AGENT_SYNC_IMPORTS WHERE JOB_ID=:job AND REVISION_ID=:revision", {'job': job_id, 'revision': revision})
                    if not existing:
                        tx.execute("INSERT INTO CX_AGENT_SYNC_IMPORTS(JOB_ID,REVISION_ID,CANDIDATE_ID,CANDIDATE_REVISION) VALUES(:job,:revision,:candidate,1)",
                                   {'job': job_id, 'revision': revision, 'candidate': candidate['candidate_id']})
                    checkpoint_items.append([path, document['version'], content_hash])
                    last_revision = revision
            if not last_revision:
                raise ContinuityError('SOURCE_EMPTY', 'Source has no nonempty eligible content')
            checkpoint = digest(checkpoint_items)
            tx.execute("UPDATE CX_AGENT_SOURCES SET CURRENT_REVISION_ID=:revision,CHECKPOINT_DIGEST=:checkpoint WHERE SOURCE_ID=:source",
                       {'revision': last_revision, 'checkpoint': checkpoint, 'source': source['source_id']})
            finished = task_continuity.finish_attempt(tx, attempt_id=attempt['attempt_id'], worker_id=worker, fencing_token=attempt['fencing_token'],
                                                      status='SUCCEEDED', request_digest=job['request_digest'])
            if finished.get('accepted') is False:
                raise ContinuityConflict('LEASE_EXPIRED', 'Source sync completion was not accepted')
            tx.execute("UPDATE CX_AGENT_SYNC_JOBS SET STATUS='SUCCEEDED',ERROR_CODE=NULL WHERE JOB_ID=:job", {'job': job_id})
            identity_api._audit_tx(tx, actor, 'SOURCE_SYNC_COMMITTED', 'AGENT_SOURCE', source['source_id'], 'ALLOW', 'Exact imports, candidates and checkpoint committed atomically')
        connection.execute_transaction_callback(commit)
    except Exception as exc:
        def fail(tx):
            current = tx.query_one("SELECT STATUS,ATTEMPT_COUNT FROM CX_AGENT_SYNC_JOBS WHERE JOB_ID=:job FOR UPDATE", {'job': job_id})
            if not current or current['status'] != 'RUNNING':
                return
            # A read-only fetch never produces an unobserved write to the
            # remote system. An unresolved original lease is still kept by
            # the shared continuity contract; no automatic retry is emitted.
            blocked = isinstance(exc, PermissionError)
            final = blocked or int(current['attempt_count']) >= int(source['max_attempts']) or not isinstance(exc, (OSError, TimeoutError))
            status = 'BLOCKED' if blocked else 'FAILED' if final else 'PENDING'
            # Only a current exact lease can record a known read failure. A
            # stale worker cannot release a successor or advance a checkpoint.
            try:
                _assert_lease(tx, job, attempt, worker)
            except ContinuityConflict:
                # Delegate unknown lease completion to the common ledger.
                task_continuity.finish_attempt(tx, attempt_id=attempt['attempt_id'], worker_id=worker, fencing_token=attempt['fencing_token'],
                                               status='UNOBSERVED', request_digest=job['request_digest'], error_code='LEASE_EXPIRED', error_message='Source sync lease expired')
                tx.execute("UPDATE CX_AGENT_SYNC_JOBS SET STATUS='BLOCKED',ERROR_CODE='LEASE_EXPIRED' WHERE JOB_ID=:job", {'job': job_id})
                return
            tx.execute("UPDATE CX_AGENT_SYNC_JOBS SET STATUS=:status,ERROR_CODE=:code WHERE JOB_ID=:job",
                       {'status': status, 'code': 'SOURCE_AUTHORITY_CHANGED' if blocked else 'SOURCE_SYNC_FAILED', 'job': job_id})
            if status=='PENDING':
                changed=tx.execute("UPDATE CX_TASK_CONTINUITY_ATTEMPTS SET STATUS='FAILED',COMPLETED_AT=CURRENT_TIMESTAMP,ERROR_CODE='SOURCE_READ_FAILED',ERROR_MESSAGE='Read-only source fetch failed before import' "
                                   "WHERE ATTEMPT_ID=:attempt AND STATUS='SENDING' AND FENCING_TOKEN=:token", {'attempt':attempt['attempt_id'],'token':attempt['fencing_token']})
                if changed!=1:
                    raise ContinuityConflict('ATTEMPT_TERMINAL','Source sync attempt already completed')
                tx.execute("UPDATE CX_TASK_CONTINUITY_LEASES SET STATUS='RELEASED',UPDATED_AT=CURRENT_TIMESTAMP WHERE CONTINUITY_ID=:continuity AND FENCING_TOKEN=:token",
                           {'continuity':job['continuity_id'],'token':attempt['fencing_token']})
                task_continuity._transition(tx,job['continuity_id'],actor,'WAITING','Known read-only source failure; bounded retry permitted',job['request_digest'])
            else:
                task_continuity.finish_attempt(tx, attempt_id=attempt['attempt_id'], worker_id=worker, fencing_token=attempt['fencing_token'],
                                               status='FAILED', request_digest=job['request_digest'], error_code='SOURCE_SYNC_FAILED', error_message='Bounded source import failed')
        connection.execute_transaction_callback(fail)
        raise
    return read_job(actor, job_id)


def source_metadata(tx, actor, domain, reference):
    reference = reference if isinstance(reference, SourceRef) else SourceRef.model_validate(reference)
    source = _source(tx, actor, reference.entity_id)
    if source['security_domain_id'] != domain:
        raise PermissionError('Source evidence must retain its original domain')
    revision = tx.query_one("SELECT REVISION_ID,TITLE,CONTENT_DIGEST,LIFECYCLE_STATE FROM CX_AGENT_SOURCE_REVISIONS "
                            "WHERE SOURCE_ID=:source AND REVISION_ID=:revision", {'source': reference.entity_id, 'revision': reference.revision_id})
    if not revision or revision['lifecycle_state'] != 'AVAILABLE' or revision['content_digest'] != reference.content_digest:
        raise PermissionError('Source evidence is unavailable')
    return revision


def resolve_source(tx, actor, domain, reference):
    source_metadata(tx, actor, domain, reference)
    revision = tx.query_one("SELECT CONTENT_CIPHER FROM CX_AGENT_SOURCE_REVISIONS WHERE SOURCE_ID=:source AND REVISION_ID=:revision",
                            {'source': reference.entity_id, 'revision': reference.revision_id})
    cipher = revision['content_cipher']
    text = decrypt_section(cipher.read() if hasattr(cipher, 'read') else cipher)['text']
    if hashlib.sha256(text.encode()).hexdigest() != reference.content_digest:
        raise ContinuityError('INTEGRITY_ERROR', 'Stored source evidence failed digest verification')
    return {'source': reference.model_dump(mode='json'), 'text': text, 'content_digest': reference.content_digest, 'authorized_scope': domain}
