"""Immutable Human reviews of already observed answers; never a generation API.

Imported observations do not become native answer-quality runs. Release tools
independently prove their original capture and exact matrix coverage.
"""
from __future__ import annotations

from typing import Any, Annotated, Literal

from pydantic import Field, StrictBool, field_validator, model_validator

from . import connection, identity_api, continuity_work as work, continuity_sources
from . import knowledge_grounding, model_credentials
from .agent_extension_contracts import bounded_json, digest, identifier, row
from .connection_crypto import encrypt_section, decrypt_section
from .continuity_contracts import Contract, Identifier, Revision, SourceRef
from .continuity_state import ContinuityConflict

SHA = Annotated[str, Field(strict=True, pattern=r'^[a-f0-9]{64}$')]
PACKET_SCHEMA = 'chuanxu-observed-answer-review-packet/v1'
EXPORT_SCHEMA = 'chuanxu-observed-answer-review-export/v1'
TABLES = ('CX_OBS_ANSWER_SETS', 'CX_OBS_ANSWER_ROWS', 'CX_OBS_ANSWER_REVIEWS')
MUTABLE = {}


class FileRef(Contract):
    path: Annotated[str, Field(strict=True, min_length=1, max_length=2000)]
    sha256: SHA


class Observation(Contract):
    key: Identifier
    case_id: Identifier
    entry: Literal['PORTAL', 'CHANNEL']
    repetition: Annotated[int, Field(strict=True, ge=1, le=2)]
    binding_digest: SHA
    case_sha256: SHA
    original_output: FileRef
    original_actor_id: Identifier
    security_domain_id: Identifier
    agent_id: Identifier
    profile_id: Identifier
    profile_version: Revision
    query: Annotated[str, Field(strict=True, min_length=1, max_length=8000)]
    observed: dict[str, Any]

    @field_validator('observed')
    @classmethod
    def bounded_observation(cls, value):
        bounded_json(value, maximum=262144)
        if value.get('status') != 'COMPLETED' or not isinstance(value.get('answer'), str):
            raise ValueError('Review requires the original completed answer')
        if not isinstance(value.get('citations', []), list) or not isinstance(value.get('context_sources', []), list):
            raise ValueError('Original citation/source descriptors are required')
        return value


class Packet(Contract):
    packet_schema: Literal['chuanxu-observed-answer-review-packet/v1'] = Field(default=PACKET_SCHEMA, alias='schema')
    version: Literal['5.0.1', '5.0.2']
    phase: Literal['baseline', 'candidate']
    target: Identifier
    track: Literal['fresh', 'upgrade']
    generation: Identifier
    policy_sha256: SHA
    package_manifests: dict[str, SHA]
    report: FileRef
    rows: Annotated[tuple[Observation, ...], Field(min_length=1, max_length=256)]

    @model_validator(mode='after')
    def bounded_unique(self):
        if len({item.key for item in self.rows}) != len(self.rows):
            raise ValueError('Observation keys must be unique')
        bounded_json(self.model_dump(mode='json', by_alias=True), maximum=8*1024*1024)
        return self


class Registration(Contract):
    packet: Packet
    reason: Annotated[str, Field(strict=True, min_length=3, max_length=1000)]


class Decision(Contract):
    output_digest: SHA
    factual_correct: StrictBool
    citations_supported: StrictBool
    reason: Annotated[str, Field(strict=True, min_length=3, max_length=1000)]


def schema_enabled():
    from .edition_features import MODEL_RUNTIME_CONTEXT_ENABLED
    return MODEL_RUNTIME_CONTEXT_ENABLED is True


def schema_statements(database):
    if database not in {'pg', 'postgresql', 'oracle', 'yashandb'}:
        raise ValueError('Unsupported review database')
    body = 'TEXT' if database in {'pg', 'postgresql'} else 'CLOB'
    credential = ("SESSION_DIGEST VARCHAR(64) NOT NULL REFERENCES CX_WEB_SESSIONS(SESSION_DIGEST), "
        "AUTH_METHOD VARCHAR(64) NOT NULL, PERMISSION_VERSION INTEGER NOT NULL CHECK(PERMISSION_VERSION>0), "
        "MFA_LEVEL VARCHAR(16) NOT NULL, NODE_ID VARCHAR(128), SESSION_CREATED_AT VARCHAR(64) NOT NULL, ")
    return [
        "CREATE TABLE CX_OBS_ANSWER_SETS (SET_ID VARCHAR(128) PRIMARY KEY, PACKET_DIGEST VARCHAR(64) NOT NULL UNIQUE, "
        f"PACKET_CIPHER {body} NOT NULL, CREATED_BY VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        + credential + "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_OBS_ANSWER_ROWS (SET_ID VARCHAR(128) NOT NULL REFERENCES CX_OBS_ANSWER_SETS(SET_ID), "
        "OUTPUT_KEY VARCHAR(128) NOT NULL, OUTPUT_DIGEST VARCHAR(64) NOT NULL, "
        "ORIGINAL_ACTOR_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "SECURITY_DOMAIN_ID VARCHAR(128) NOT NULL REFERENCES CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID), "
        "AGENT_ID VARCHAR(128) NOT NULL REFERENCES CX_NATIVE_AGENTS(AGENT_ID), "
        "PROFILE_ID VARCHAR(128) NOT NULL REFERENCES CX_LLM_PROVIDER_PROFILES(PROFILE_ID), "
        "PROFILE_VERSION INTEGER NOT NULL CHECK(PROFILE_VERSION>0), "
        f"ROW_CIPHER {body} NOT NULL, CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "PRIMARY KEY(SET_ID,OUTPUT_KEY))",
        "CREATE TABLE CX_OBS_ANSWER_REVIEWS (REVIEW_ID VARCHAR(128) PRIMARY KEY, "
        "SET_ID VARCHAR(128) NOT NULL, OUTPUT_KEY VARCHAR(128) NOT NULL, "
        "REVIEWER_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "OUTPUT_DIGEST VARCHAR(64) NOT NULL, FACTUAL_CORRECT CHAR(1) NOT NULL CHECK(FACTUAL_CORRECT IN ('Y','N')), "
        "CITATIONS_SUPPORTED CHAR(1) NOT NULL CHECK(CITATIONS_SUPPORTED IN ('Y','N')), "
        "REASON VARCHAR(1000) NOT NULL, " + credential +
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "UNIQUE(SET_ID,OUTPUT_KEY,REVIEWER_ID), FOREIGN KEY(SET_ID,OUTPUT_KEY) REFERENCES CX_OBS_ANSWER_ROWS(SET_ID,OUTPUT_KEY))",
    ]


def _credential(tx, actor):
    credential = model_credentials.capture(actor, tx=tx)
    if credential is None or credential.kind != 'WEB':
        raise PermissionError('An original authenticated Human Web Session is required')
    principal = row(tx.query_one('SELECT PRINCIPAL_TYPE,STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor', {'actor': actor}))
    if principal.get('principal_type') != 'HUMAN' or principal.get('status') != 'ACTIVE':
        raise PermissionError('An active Human principal is required')
    if not credential.auth_method.upper().endswith(':DASHBOARD') and credential.auth_method.upper() != 'DASHBOARD':
        raise PermissionError('Review requires the original Dashboard Session')
    if identity_api.effective_access(actor, 'platform.manage').get('decision') != 'ALLOW':
        raise PermissionError('Observed-answer review access denied')
    return credential


def _credential_values(value):
    return dict(session_digest=value.credential_digest, auth_method=value.auth_method,
        permission_version=value.permission_version, mfa_level=value.mfa_level,
        node_id=value.node_id or None, session_created_at=value.created_at)


def _authorize(tx, actor, value):
    work._authorize(tx, actor, value.security_domain_id, write=False)
    if not identity_api._agent_visible_to(actor, value.agent_id):
        raise PermissionError('The original observed Agent is unavailable')
    agent = row(tx.query_one('SELECT STATUS,LLM_PROFILE_ID FROM CX_NATIVE_AGENTS WHERE AGENT_ID=:id', {'id': value.agent_id}))
    profile = row(tx.query_one('SELECT STATUS,HEALTH_STATE,VERSION FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:id', {'id': value.profile_id}))
    if (agent.get('status') != 'ACTIVE' or agent.get('llm_profile_id') != value.profile_id
            or profile.get('status') != 'ACTIVE' or profile.get('health_state') != 'HEALTHY'
            or int(profile.get('version') or 0) != value.profile_version):
        raise PermissionError('The original observed Agent/Profile revision is stale')
    knowledge_grounding.require_reader(actor, value.agent_id, transaction=tx)
    for citation in value.observed.get('citations', []):
        if not isinstance(citation, dict) or not citation.get('entity_id') or not citation.get('digest'):
            raise ValueError('An exact original knowledge citation is required')
        knowledge_grounding.citation(actor, value.agent_id, citation['entity_id'], citation['digest'], transaction=tx)
    for item in value.observed.get('context_sources', []):
        source = SourceRef.model_validate(item.get('source', item) if isinstance(item, dict) else item)
        continuity_sources.resolve(tx, actor, value.security_domain_id, source)


def _decrypt(record, field, expected):
    value = decrypt_section(record[field])
    if digest(value) != record[expected]:
        raise ValueError('Immutable observed-answer integrity check failed')
    return value


def register(actor, value):
    request = Registration.model_validate(value)
    packet = request.packet.model_dump(mode='json', by_alias=True)
    packet_digest = digest(packet)
    def save(tx):
        credential = _credential(tx, actor)
        for observation in request.packet.rows:
            _authorize(tx, actor, observation)
        existing = row(tx.query_one('SELECT SET_ID,CREATED_BY FROM CX_OBS_ANSWER_SETS WHERE PACKET_DIGEST=:digest', {'digest': packet_digest}))
        if existing:
            if existing['created_by'] != actor:
                raise PermissionError('The original packet belongs to another registering actor')
            model_credentials.recheck(tx, credential)
            return dict(set_id=existing['set_id'], packet_digest=packet_digest, replayed=True, generation_requests=0)
        set_id = identifier('OAS')
        tx.execute('INSERT INTO CX_OBS_ANSWER_SETS(SET_ID,PACKET_DIGEST,PACKET_CIPHER,CREATED_BY,SESSION_DIGEST,AUTH_METHOD,PERMISSION_VERSION,MFA_LEVEL,NODE_ID,SESSION_CREATED_AT) VALUES(:id,:digest,:cipher,:actor,:session_digest,:auth_method,:permission_version,:mfa_level,:node_id,:session_created_at)',
            dict(id=set_id, digest=packet_digest, cipher=encrypt_section(packet), actor=actor, **_credential_values(credential)))
        for observation in request.packet.rows:
            item = observation.model_dump(mode='json')
            tx.execute('INSERT INTO CX_OBS_ANSWER_ROWS(SET_ID,OUTPUT_KEY,OUTPUT_DIGEST,ORIGINAL_ACTOR_ID,SECURITY_DOMAIN_ID,AGENT_ID,PROFILE_ID,PROFILE_VERSION,ROW_CIPHER) VALUES(:set_id,:key,:digest,:original_actor_id,:security_domain_id,:agent_id,:profile_id,:profile_version,:cipher)',
                dict(set_id=set_id, key=observation.key, digest=digest(item), cipher=encrypt_section(item),
                    **{key: item[key] for key in ('original_actor_id', 'security_domain_id', 'agent_id', 'profile_id', 'profile_version')}))
        model_credentials.recheck(tx, credential)
        identity_api._audit_tx(tx, actor, 'OBSERVED_ANSWERS_REGISTERED', 'OBSERVED_ANSWER_SET', set_id, 'ALLOW', request.reason)
        return dict(set_id=set_id, packet_digest=packet_digest, replayed=False, generation_requests=0)
    return connection.execute_transaction_callback(save)


def _set(tx, set_id):
    record = row(tx.query_one('SELECT * FROM CX_OBS_ANSWER_SETS WHERE SET_ID=:id', {'id': set_id}))
    if not record:
        raise PermissionError('The observed answer set is unavailable')
    packet = Packet.model_validate(_decrypt(record, 'packet_cipher', 'packet_digest'))
    return record, packet


def _output(tx, set_id, key):
    record = row(tx.query_one('SELECT * FROM CX_OBS_ANSWER_ROWS WHERE SET_ID=:id AND OUTPUT_KEY=:key', {'id': set_id, 'key': key}))
    if not record:
        raise PermissionError('The original observed answer is unavailable')
    value = Observation.model_validate(_decrypt(record, 'row_cipher', 'output_digest'))
    fields = ('original_actor_id', 'security_domain_id', 'agent_id', 'profile_id', 'profile_version')
    if value.key != key or any(getattr(value, name) != record[name] for name in fields):
        raise ValueError('The immutable observed-answer identity changed')
    return record, value


def read_set(actor, set_id):
    def read(tx):
        credential = _credential(tx, actor)
        record, packet = _set(tx, set_id)
        for item in packet.rows:
            _authorize(tx, actor, item)
            output, value = _output(tx, set_id, item.key)
            if value != item:
                raise ValueError('The original packet and native output differ')
        result = dict(set_id=set_id, packet=packet.model_dump(mode='json', by_alias=True), packet_digest=record['packet_digest'],
            reviews=[row(item) for item in tx.query('SELECT REVIEW_ID,OUTPUT_KEY,REVIEWER_ID,OUTPUT_DIGEST,FACTUAL_CORRECT,CITATIONS_SUPPORTED,REASON,CREATED_AT FROM CX_OBS_ANSWER_REVIEWS WHERE SET_ID=:id ORDER BY OUTPUT_KEY,REVIEWER_ID', {'id': set_id})],
            provenance='IMPORTED_OBSERVATIONS_REQUIRE_INDEPENDENT_ORIGINAL_CAPTURE_VERIFICATION', generation_requests=0)
        model_credentials.recheck(tx, credential)
        return result
    return connection.execute_transaction_callback(read)


def review(actor, set_id, key, value):
    decision = Decision.model_validate(value)
    reason = decision.reason.strip()
    if len(reason) < 3:
        raise ValueError('A substantive Human review reason is required')
    def save(tx):
        credential = _credential(tx, actor)
        # Serialize simultaneous decisions for this immutable output.
        tx.query_one('SELECT OUTPUT_KEY FROM CX_OBS_ANSWER_ROWS WHERE SET_ID=:id AND OUTPUT_KEY=:key FOR UPDATE', {'id': set_id, 'key': key})
        parent, packet = _set(tx, set_id)
        output, observation = _output(tx, set_id, key)
        _authorize(tx, actor, observation)
        if actor in {parent['created_by'], observation.original_actor_id}:
            raise PermissionError('An independent Human reviewer is required')
        if decision.output_digest != output['output_digest']:
            raise ContinuityConflict('STALE_OUTPUT', 'The reviewed original output digest changed')
        if not any(item == observation for item in packet.rows):
            raise ValueError('The reviewed output is absent from its original packet')
        review_id = identifier('OAR')
        tx.execute('INSERT INTO CX_OBS_ANSWER_REVIEWS(REVIEW_ID,SET_ID,OUTPUT_KEY,REVIEWER_ID,OUTPUT_DIGEST,FACTUAL_CORRECT,CITATIONS_SUPPORTED,REASON,SESSION_DIGEST,AUTH_METHOD,PERMISSION_VERSION,MFA_LEVEL,NODE_ID,SESSION_CREATED_AT) VALUES(:review_id,:set_id,:key,:actor,:digest,:facts,:citations,:reason,:session_digest,:auth_method,:permission_version,:mfa_level,:node_id,:session_created_at)',
            dict(review_id=review_id, set_id=set_id, key=key, actor=actor, digest=decision.output_digest,
                facts='Y' if decision.factual_correct else 'N', citations='Y' if decision.citations_supported else 'N',
                reason=reason, **_credential_values(credential)))
        model_credentials.recheck(tx, credential)
        identity_api._audit_tx(tx, actor, 'OBSERVED_ANSWER_REVIEWED', 'OBSERVED_ANSWER_REVIEW', review_id, 'ALLOW', reason)
        return dict(review_id=review_id, set_id=set_id, key=key, reviewer_id=actor, recorded=True, generation_requests=0)
    return connection.execute_transaction_callback(save)


def export_native(tx, set_id):
    """Private native observer helper; not an HTTP authorization bypass.

    Reads original immutable records after their review window. The external
    observer must establish selected package/database/process authority.
    """
    parent, packet = _set(tx, set_id)
    outputs = []
    for item in packet.rows:
        record, observed = _output(tx, set_id, item.key)
        if observed != item:
            raise ValueError('Native output differs from the original imported observation')
        outputs.append({key: record[key] for key in record if key != 'row_cipher'})
    reviews = [row(item) for item in tx.query('SELECT * FROM CX_OBS_ANSWER_REVIEWS WHERE SET_ID=:id ORDER BY OUTPUT_KEY,REVIEWER_ID', {'id': set_id})]
    audits = []
    principals = {}
    for item in reviews:
        actual = tx.query('SELECT EVENT_ID,PRINCIPAL_ID,ACTION_NAME,RESOURCE_TYPE,RESOURCE_ID,OUTCOME,REASON,CREATED_AT FROM CX_SECURITY_EVENTS WHERE RESOURCE_ID=:id AND ACTION_NAME=:action',
            {'id': item['review_id'], 'action': 'OBSERVED_ANSWER_REVIEWED'})
        audits.extend(row(value) for value in actual)
        principal = row(tx.query_one('SELECT PRINCIPAL_TYPE FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor', {'actor': item['reviewer_id']}))
        principals[item['reviewer_id']] = principal
    return dict(schema=EXPORT_SCHEMA, set={key: parent[key] for key in parent if key != 'packet_cipher'},
        packet=packet.model_dump(mode='json', by_alias=True), outputs=outputs, reviews=reviews, audits=audits,
        reviewer_principals=principals, generation_requests=0, release_ready=False)


def export(actor, set_id):
    # An authenticated caller still needs current read authority; the private
    # native observer can preserve original review facts after fixture cleanup.
    def read(tx):
        credential = _credential(tx, actor)
        _, packet = _set(tx, set_id)
        for item in packet.rows:
            _authorize(tx, actor, item)
        result = export_native(tx, set_id)
        model_credentials.recheck(tx, credential)
        return result
    return connection.execute_transaction_callback(read)
