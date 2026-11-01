"""Shared enrollment/proof primitives for the existing authenticated Gateway.

The registered Origin server is authoritative for its own source and lease.
The coordinator authenticates its Gateway credential, never a foreign actor ID.
"""
import base64
import hashlib
import hmac
import json

from . import connection,identity_api,model_endpoint_capacity as capacity,continuity_work as work
from .agent_extension_contracts import canonical,digest,identifier,row
from .continuity_state import ContinuityConflict
from .model_coordinator_contracts import CoordinatorBinding,CoordinatorRoute,OriginEnvelope,ProofEnvelope

PROOF_MS=30000


def enabled():
    from .edition_features import MODEL_RUNTIME_CONTEXT_ENABLED
    if not MODEL_RUNTIME_CONTEXT_ENABLED:raise ValueError('Shared coordinator requires the current model runtime')


def profile(tx,profile_id,version=None):
    result=row(tx.query_one('SELECT PROFILE_ID,VERSION,PROFILE_KEY,PROVIDER_URL,MODEL_ID,API_KEY_CIPHER,STATUS '
        'FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile FOR UPDATE',{'profile':profile_id}))
    if not result or result['status']!='ACTIVE' or version is not None and int(result['version'])!=int(version):
        raise PermissionError('The exact enrolled Provider Profile is unavailable')
    return result


def secret(profile_value):
    from .connection_crypto import decrypt_section
    value=str(decrypt_section(str(profile_value.get('api_key_cipher') or '')).get('api_key') or '')
    if not value.startswith('cxgw_'):raise PermissionError('An enrolled Gateway machine credential is required')
    return value


def token_digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _credential_scopes(result,profile_id):
    try:scopes=json.loads(result.get('scopes_json') or '[]')
    except (ValueError,TypeError):scopes=[]
    if not isinstance(scopes,list):scopes=[]
    profiles={item.split(':',1)[1] for item in scopes if isinstance(item,str) and item.startswith('profile:')}
    if ('model.forward' not in scopes or profiles and profile_id not in profiles
            or any(str(item).startswith('agent:') for item in scopes)):
        raise PermissionError('Coordinator Gateway credential scope is unavailable')


def _credential(tx,raw,profile_id,*,lock_credential=False):
    if not raw.startswith('cxgw_'):raise PermissionError('Coordinator transport requires an original Gateway credential')
    statement="SELECT CREDENTIAL_ID,CREATED_BY,SCOPES_JSON FROM CX_MODEL_GATEWAY_CREDENTIALS WHERE "\
        "TOKEN_DIGEST=:fingerprint AND STATUS='ACTIVE' AND (EXPIRES_AT IS NULL OR EXPIRES_AT>CURRENT_TIMESTAMP)"
    params={'fingerprint':token_digest(raw)}
    result=row(tx.query_one(statement,params))
    if not result:raise PermissionError('The original coordinator Gateway credential is unavailable')
    work._lock_actor(tx,result['created_by'])
    if lock_credential:
        fresh=row(tx.query_one(statement+' FOR UPDATE',params))
        if not fresh or fresh['credential_id']!=result['credential_id'] or fresh['created_by']!=result['created_by']:
            raise PermissionError('The original coordinator Gateway credential changed during authorization')
        result=fresh
    _credential_scopes(result,profile_id)
    return result


def authenticated_binding(tx,raw,binding_id,envelope=None,*,dispatch=True):
    enabled()
    binding=row(tx.query_one('SELECT * FROM CX_MODEL_COORD_BINDINGS WHERE BINDING_ID=:binding',{'binding':binding_id}))
    if not binding or binding['status']!='ACTIVE':raise PermissionError('Coordinator enrollment is unavailable')
    credential=_credential(tx,raw,binding['profile_id'])
    if credential['credential_id']!=binding['credential_id']:
        raise PermissionError('A different Gateway credential cannot replace the enrolled original')
    group,policy=capacity._group(tx,binding['group_id'])
    latest=row(tx.query_one('SELECT * FROM CX_MODEL_COORD_BINDINGS WHERE BINDING_ID=:binding FOR UPDATE',{'binding':binding_id}))
    if not latest or latest!=binding:raise PermissionError('Coordinator enrollment changed during authorization')
    credential=_credential(tx,raw,binding['profile_id'],lock_credential=True)
    if credential['credential_id']!=binding['credential_id']:
        raise PermissionError('A different Gateway credential cannot replace the enrolled original')
    tx.query_one('SELECT ORIGIN_ID FROM CX_MODEL_CAP_ORIGINS WHERE GROUP_ID=:group_id AND ORIGIN_ID=:origin_id FOR UPDATE',
        dict(group_id=binding['group_id'],origin_id=binding['origin_id']))
    origin=capacity._origin(tx,credential['created_by'],binding['group_id'],binding['origin_id'])
    if origin['installation_key']!=binding['installation_key']:
        raise PermissionError('Coordinator installation enrollment changed')
    if not dispatch:return binding,credential,None,group,policy
    current=profile(tx,binding['profile_id'],binding['profile_version'])
    if ('/api/model-gateway/coordinator/' in str(current['provider_url'])
            or origin['installation_key']!=binding['installation_key']
            or int(group['current_revision'])!=int(binding['policy_revision'])
            or capacity.selected_group(tx,current['profile_id'],current['provider_url'])!=binding['group_id']):
        raise PermissionError('Coordinator resource, origin or policy enrollment changed')
    if envelope is not None:
        selected=envelope if isinstance(envelope,OriginEnvelope) else OriginEnvelope.model_validate(envelope)
        pairs={'installation_key':'installation_key','origin_profile_id':'origin_profile_id',
               'origin_profile_version':'origin_profile_version','group_id':'group_id','policy_revision':'policy_revision',
               'profile_id':'profile_id','profile_version':'profile_version'}
        if any(str(getattr(selected,key))!=str(binding[column]) for key,column in pairs.items()) or selected.model_id!=current['model_id']:
            raise PermissionError('Foreign source metadata does not match the authenticated enrollment')
    return binding,credential,current,group,policy


def register_binding(actor,value):
    enabled();request=CoordinatorBinding.model_validate(value)
    fingerprint=digest(request.model_dump(mode='json'))
    def perform(tx):
        work._lock_actor(tx,actor);capacity.authorize(actor,'model_gateway.manage')
        group,policy=capacity._group(tx,request.group_id)
        if int(group['version'])!=request.expected_group_version or int(group['current_revision'])!=request.policy_revision:
            raise ContinuityConflict('COORDINATOR_POLICY_CHANGED','Select the exact current capacity revision')
        origin=row(tx.query_one('SELECT * FROM CX_MODEL_CAP_ORIGINS WHERE GROUP_ID=:group_id AND ORIGIN_ID=:origin_id',
            dict(group_id=request.group_id,origin_id=request.origin_id)))
        credential=row(tx.query_one("SELECT CREDENTIAL_ID,CREATED_BY,SCOPES_JSON FROM CX_MODEL_GATEWAY_CREDENTIALS "
            "WHERE CREDENTIAL_ID=:credential AND STATUS='ACTIVE' AND (EXPIRES_AT IS NULL OR EXPIRES_AT>CURRENT_TIMESTAMP)",
            {'credential':request.credential_id}))
        current=profile(tx,request.profile_id,request.profile_version)
        if (not origin or origin['status']!='ACTIVE' or origin['installation_key']!=request.installation_key
                or not credential or credential['created_by']!=origin['principal_id']
                or capacity.selected_group(tx,current['profile_id'],current['provider_url'])!=request.group_id
                or '/api/model-gateway/coordinator/' in str(current['provider_url'])):
            raise PermissionError('Gateway credential must belong to the selected registered coordinator Origin')
        _credential_scopes(credential,request.profile_id)
        prior=row(tx.query_one('SELECT BINDING_ID,REQUEST_DIGEST FROM CX_MODEL_COORD_BINDINGS WHERE REGISTERED_BY=:actor '
            'AND IDEMPOTENCY_KEY=:key',dict(actor=actor,key=request.idempotency_key)))
        if prior:
            if prior['request_digest']!=fingerprint:raise ContinuityConflict('IDEMPOTENCY_CONFLICT','Coordinator enrollment changed')
            return dict(binding_id=prior['binding_id'],replayed=True)
        key=identifier('MCB')
        tx.execute('INSERT INTO CX_MODEL_COORD_BINDINGS(BINDING_ID,GROUP_ID,ORIGIN_ID,INSTALLATION_KEY,CREDENTIAL_ID,PROFILE_ID,'
            'PROFILE_VERSION,ORIGIN_PROFILE_ID,ORIGIN_PROFILE_VERSION,POLICY_REVISION,STATUS,VERSION,REGISTERED_BY,IDEMPOTENCY_KEY,'
            'REQUEST_DIGEST,CREATED_AT_MS) VALUES(:binding,:group_id,:origin_id,:installation,:credential,:profile,:profile_version,'
            ":origin_profile,:origin_version,:policy,'ACTIVE',1,:actor,:key,:fingerprint,:now_ms)",
            dict(binding=key,group_id=request.group_id,origin_id=request.origin_id,installation=request.installation_key,
                credential=request.credential_id,profile=request.profile_id,profile_version=request.profile_version,
                origin_profile=request.origin_profile_id,origin_version=request.origin_profile_version,policy=request.policy_revision,
                actor=actor,key=request.idempotency_key,fingerprint=fingerprint,now_ms=capacity._now_ms(tx)))
        identity_api._audit_tx(tx,actor,'MODEL_COORDINATOR_ENROLL','MODEL_COORDINATOR',key,'ALLOW',request.reason)
        return dict(binding_id=key,replayed=False)
    return connection.execute_transaction_callback(perform)


def register_route(actor,value):
    enabled();request=CoordinatorRoute.model_validate(value)
    fingerprint=digest(request.model_dump(mode='json'))
    target=capacity.endpoint_url(request.coordinator_url)
    if not target.endswith('/api/model-gateway/coordinator/'+request.binding_id):
        raise ValueError('The fixed coordinator URL must identify the enrolled Gateway binding')
    def perform(tx):
        work._lock_actor(tx,actor);capacity.authorize(actor,'model_gateway.manage')
        current=profile(tx,request.profile_id,request.profile_version)
        if capacity.endpoint_url(current['provider_url'])!=target:raise PermissionError('Local Profile URL differs from its fixed coordinator route')
        credential=token_digest(secret(current))
        prior=row(tx.query_one('SELECT ROUTE_ID,REQUEST_DIGEST FROM CX_MODEL_COORD_ROUTES WHERE REGISTERED_BY=:actor '
            'AND IDEMPOTENCY_KEY=:key',dict(actor=actor,key=request.idempotency_key)))
        if prior:
            if prior['request_digest']!=fingerprint:raise ContinuityConflict('IDEMPOTENCY_CONFLICT','Coordinator route changed')
            return dict(route_id=prior['route_id'],replayed=True)
        key=identifier('MCR')
        tx.execute('INSERT INTO CX_MODEL_COORD_ROUTES(ROUTE_ID,PROFILE_ID,PROFILE_VERSION,COORDINATOR_URL,BINDING_ID,GROUP_ID,'
            'POLICY_REVISION,ORIGIN_ID,INSTALLATION_KEY,COORDINATOR_PROFILE_ID,COORDINATOR_PROFILE_VERSION,CREDENTIAL_DIGEST,'
            'STATUS,VERSION,REGISTERED_BY,IDEMPOTENCY_KEY,REQUEST_DIGEST,CREATED_AT_MS) VALUES(:route,:profile,:profile_version,'
            ":url,:binding,:group_id,:policy,:origin_id,:installation,:remote_profile,:remote_version,:credential,'ACTIVE',1,:actor,:key,:fingerprint,:now_ms)",
            dict(route=key,profile=request.profile_id,profile_version=request.profile_version,url=target,binding=request.binding_id,
                group_id=request.group_id,policy=request.policy_revision,origin_id=request.origin_id,installation=request.installation_key,
                remote_profile=request.coordinator_profile_id,remote_version=request.coordinator_profile_version,credential=credential,
                actor=actor,key=request.idempotency_key,fingerprint=fingerprint,now_ms=capacity._now_ms(tx)))
        identity_api._audit_tx(tx,actor,'MODEL_COORDINATOR_ROUTE','PROVIDER_PROFILE',request.profile_id,'ALLOW',request.reason)
        return dict(route_id=key,replayed=False)
    return connection.execute_transaction_callback(perform)


def encode_proof(proof,raw):
    value=proof.model_dump(mode='json') if hasattr(proof,'model_dump') else proof
    signed=dict(proof=value,signature=hmac.new(raw.encode(),canonical(value).encode(),hashlib.sha256).hexdigest())
    return base64.urlsafe_b64encode(canonical(signed).encode()).decode()


def decode_proof(value,raw):
    if not isinstance(value,str) or not 1<=len(value)<=16384:raise PermissionError('A bounded original dispatch proof is required')
    try:parsed=ProofEnvelope.model_validate_json(base64.b64decode(value,altchars=b'-_',validate=True))
    except Exception:raise PermissionError('Invalid Origin dispatch proof') from None
    expected=hmac.new(raw.encode(),canonical(parsed.proof.model_dump(mode='json')).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,parsed.signature):raise PermissionError('Origin dispatch proof integrity failed')
    return parsed.proof
