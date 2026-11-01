"""Origin-side durable authorization for an explicitly enrolled shared Gateway."""
from contextlib import contextmanager
from datetime import timezone
import json
import time
import urllib.error
import urllib.request

from . import connection,identity_api,continuity_work as work,model_endpoint_capacity as capacity
from . import model_coordinator_common as common,model_dispatch,model_coordinator_observations as observations
from .agent_extension_contracts import digest,identifier,row
from .continuity_state import ContinuityConflict
from .model_coordinator_contracts import OriginEnvelope,DispatchProof,ReceiptReconciliation,CoordinatorResolution
from .model_results import decode_json,ModelResultError
from .model_native_numeric import native_revision


def selected_route(profile):
    def locate(tx):
        route=row(tx.query_one('SELECT * FROM CX_MODEL_COORD_ROUTES WHERE PROFILE_ID=:profile ORDER BY PROFILE_VERSION DESC',
            {'profile':str(profile.get('profile_id') or '')}))
        if not route:
            if '/api/model-gateway/coordinator/' in str(profile.get('provider_url') or ''):
                raise model_dispatch.ModelNotDispatched('COORDINATOR_NOT_ENROLLED','The shared coordinator Profile has no original enrolled route')
            return None
        _route(tx,profile,route)
        return route
    return connection.execute_transaction_callback(locate)


def _route(tx,profile,route):
    current=common.profile(tx,route['profile_id'],route['profile_version'])
    if (route['status']!='ACTIVE' or int(profile.get('version') or 0)!=int(route['profile_version'])
            or common.token_digest(common.secret(current))!=route['credential_digest']
            or capacity.endpoint_url(current['provider_url'])!=route['coordinator_url']
            or capacity.endpoint_url(profile.get('provider_url'))!=route['coordinator_url']
            or profile.get('model_id')!=current['model_id']):
        raise model_dispatch.ModelNotDispatched('COORDINATOR_ROUTE_CHANGED','The frozen coordinator route or original Gateway credential changed')
    return current


def _millis(value):
    from .task_continuity import _utc_naive
    selected=_utc_naive(value)
    return int(selected.replace(tzinfo=timezone.utc).timestamp()*1000) if selected else None


def _source_fence(tx,context):
    now=capacity._now_ms(tx)
    if context.source_kind in {'NATIVE','CHANNEL'}:
        runtime=row(tx.query_one('SELECT WORKER_ID,FENCING_TOKEN,LEASE_EXPIRES_AT,STATUS FROM CX_RUNTIME_EXECUTIONS '
            'WHERE EXECUTION_ID=:execution',{'execution':context.source_id}))
        if runtime:
            expiry=_millis(runtime.get('lease_expires_at'))
            if runtime['status']!='CLAIMED' or runtime['worker_id']!=context.worker_key or not expiry or expiry<=now:
                raise PermissionError('The original Origin Runtime Worker lease is not current')
            return int(runtime['fencing_token']),expiry
    if context.source_kind in {'NATIVE','RETROSPECTIVE','EVALUATION'}:
        attempt=row(tx.query_one('SELECT a.FENCING_TOKEN,a.LEASE_EXPIRES_AT,a.STATUS,l.LEASE_OWNER,l.STATUS AS LEASE_STATUS,'
            'l.FENCING_TOKEN AS LEASE_FENCING_TOKEN,l.LEASE_EXPIRES_AT AS CURRENT_LEASE_EXPIRES_AT '
            'FROM CX_TASK_CONTINUITY_ATTEMPTS a JOIN CX_TASK_CONTINUITY_LEASES l ON l.CONTINUITY_ID=a.CONTINUITY_ID '
            'WHERE a.ATTEMPT_ID=:attempt',{'attempt':context.source_attempt_id}))
        if attempt:
            expiries=[_millis(attempt.get(key)) for key in ('lease_expires_at','current_lease_expires_at')]
            expiry=min(expiries) if all(expiries) else None
            if (attempt['status']!='SENDING' or attempt['lease_status']!='ACTIVE' or attempt['lease_owner']!=context.worker_key
                    or int(attempt['fencing_token'])!=int(attempt['lease_fencing_token'])
                    or not expiry or expiry<=now):raise PermissionError('The original Origin Task attempt was expired or fenced')
            return int(attempt['fencing_token']),expiry
    if context.source_kind in {'NATIVE','CHANNEL','RETROSPECTIVE','EVALUATION'}:
        raise PermissionError('The original Origin Worker or Task attempt lease is unavailable')
    # Synchronous Portal/Gateway/probe/managed-input requests have no Worker
    # lease to borrow. Their original credential/source callback remains the
    # authority; this request gets its own immutable one-use receipt fence.
    return 1,now+7200000


def _managed_source(tx,context,profile,payload):
    if not any(isinstance(item.get('content'),list) for item in payload.get('messages',[])):return
    if (context.source_kind!='EXTERNAL' or context.source_id!=context.source_attempt_id
            or not context.source_id.startswith('MU_') or payload.get('stream') is not False):
        raise PermissionError('Remote images require the original managed-input source adapter')
    use=row(tx.query_one('SELECT * FROM CX_MANAGED_ASSET_USES WHERE USE_ID=:source FOR UPDATE',{'source':context.source_id}))
    asset=row(tx.query_one('SELECT OWNER_ID,MEDIA_TYPE,VERSION,STATUS FROM CX_MANAGED_INPUT_ASSETS WHERE ASSET_ID=:asset FOR UPDATE',
        {'asset':use.get('asset_id')})) if use else {}
    if (not use or not asset or use['status']!='SENDING' or use['actor_id']!=context.actor or asset['owner_id']!=context.actor
            or use['profile_id']!=profile['profile_id'] or int(use['profile_version'])!=int(profile['version'])
            or int(use['asset_version'])!=int(asset['version']) or asset['status']!='ACTIVE'
            or asset['media_type']!='image/png' or use['input_digest']!=digest(payload['messages'])):
        raise PermissionError('The exact original owned PNG managed-input use is unavailable')


def _local(tx,context,profile,route,payload_digest,payload):
    if not context or not context.credential_digest or not callable(context.reauthorize):
        raise PermissionError('The original authenticated Origin dispatch context is required')
    for principal in sorted({context.actor,*context.lock_principals}):work._lock_actor(tx,principal)
    current_route=row(tx.query_one('SELECT * FROM CX_MODEL_COORD_ROUTES WHERE ROUTE_ID=:route FOR UPDATE',{'route':route['route_id']}))
    if not current_route or int(current_route['version'])!=int(route['version']):raise PermissionError('Origin route revision changed')
    current=_route(tx,profile,current_route)
    context.reauthorize(tx,dict(input_digest=payload_digest,credential_digest=context.credential_digest,
        actor_id=context.actor,source_kind=context.source_kind,source_id=context.source_id,source_attempt_id=context.source_attempt_id,
        profile_id=profile['profile_id'],profile_version=profile['version'],group_id=route['group_id']))
    _managed_source(tx,context,profile,payload)
    return current,_source_fence(tx,context)


def _envelope(receipt,route):
    return OriginEnvelope(origin_receipt_id=receipt['origin_receipt_id'],installation_key=route['installation_key'],
        origin_actor_id=receipt['actor_id'],source_kind=receipt['source_kind'],source_id=receipt['source_id'],source_attempt_id=receipt['source_attempt_id'],
        worker_key=receipt['worker_key'],origin_fencing_token=int(receipt['origin_fencing_token']),origin_lease_until_ms=int(receipt['origin_lease_until_ms']),
        authority_digest=receipt['authority_digest'],origin_profile_id=receipt['profile_id'],origin_profile_version=int(receipt['profile_version']),
        group_id=route['group_id'],policy_revision=int(route['policy_revision']),profile_id=route['coordinator_profile_id'],
        profile_version=int(route['coordinator_profile_version']),model_id=receipt['model_id'],payload_digest=receipt['payload_digest'],
        idempotency_key=receipt['idempotency_key'])


def _receipt(tx,key):
    value=row(tx.query_one('SELECT * FROM CX_MODEL_ORIGIN_RECEIPTS WHERE ORIGIN_RECEIPT_ID=:receipt FOR UPDATE',{'receipt':key}))
    if not value:raise PermissionError('The original Origin request receipt is unavailable')
    return value


def _state(tx,record,status,code,**fields):
    permitted={'coordinator_request_id','admission_id','remote_fencing_token','remote_reservation_version',
        'authorized_at_ms','proof_expires_at_ms','proof_digest'}
    if set(fields)-permitted:raise ValueError('Unsupported Origin progress field')
    params=dict(receipt=record['origin_receipt_id'],status=status,code=code,revision=int(record['version'])+1,**fields)
    assignments=''.join(','+key.upper()+'=:'+key for key in fields)
    tx.execute('UPDATE CX_MODEL_ORIGIN_RECEIPTS SET STATUS=:status,FINISH_CODE=:code,VERSION=:revision'+assignments+
        ' WHERE ORIGIN_RECEIPT_ID=:receipt',params)
    record.update(status=status,finish_code=code,version=params['revision'],**fields)


def prepare(profile,payload,context,route):
    profile={**profile,'version':native_revision(profile['version'])}
    payload_digest=digest(payload)
    def perform(tx):
        current,(fence,expiry)=_local(tx,context,profile,route,payload_digest,payload)
        prior=row(tx.query_one('SELECT * FROM CX_MODEL_ORIGIN_RECEIPTS WHERE ACTOR_ID=:actor AND SOURCE_KIND=:kind '
            'AND SOURCE_ID=:source AND SOURCE_ATTEMPT_ID=:attempt FOR UPDATE',
            dict(actor=context.actor,kind=context.source_kind,source=context.source_id,attempt=context.source_attempt_id)))
        if prior:
            if (prior['payload_digest']!=payload_digest or prior['original_credential_digest']!=context.credential_digest
                    or prior['route_id']!=route['route_id'] or int(prior['route_version'])!=int(route['version'])
                    or int(prior['origin_fencing_token'])!=fence or prior['worker_key']!=context.worker_key):
                raise ContinuityConflict('IDEMPOTENCY_CONFLICT','The original Origin source attempt cannot change its dispatch')
            if prior['status']!='PREPARED':
                if prior['status'] in {'DISPATCHING','UNKNOWN'}:
                    raise ContinuityConflict('UNKNOWN_SEND','The original Origin attempt has an unresolved prior send; it cannot send again')
                raise model_dispatch.ModelNotDispatched('ORIGIN_ATTEMPT_ALREADY_RECORDED','Read and reconcile the original Origin attempt; it cannot send again')
            return prior
        key=identifier('MOR')
        idem='remote:'+digest(dict(actor=context.actor,kind=context.source_kind,source=context.source_id,attempt=context.source_attempt_id,route=route['route_id']))
        authority=digest(dict(actor=context.actor,credential=context.credential_digest,source=context.source_id,attempt=context.source_attempt_id,
            worker=context.worker_key,fence=fence,profile=profile['profile_id'],version=profile['version'],route=route['route_id'],route_version=native_revision(route['version'])))
        selected=dict(origin_receipt_id=key,actor_id=context.actor,source_kind=context.source_kind,source_id=context.source_id,
            source_attempt_id=context.source_attempt_id,worker_key=context.worker_key,origin_fencing_token=fence,origin_lease_until_ms=expiry,
            authority_digest=authority,profile_id=profile['profile_id'],profile_version=profile['version'],model_id=profile['model_id'],
            payload_digest=payload_digest,idempotency_key=idem)
        fingerprint=digest(_envelope(selected,route).model_dump(mode='json'))
        tx.execute('INSERT INTO CX_MODEL_ORIGIN_RECEIPTS(ORIGIN_RECEIPT_ID,ROUTE_ID,ROUTE_VERSION,ACTOR_ID,ORIGINAL_CREDENTIAL_DIGEST,'
            'SOURCE_KIND,SOURCE_ID,SOURCE_ATTEMPT_ID,WORKER_KEY,ORIGIN_FENCING_TOKEN,ORIGIN_LEASE_UNTIL_MS,AUTHORITY_DIGEST,'
            'PROFILE_ID,PROFILE_VERSION,MODEL_ID,PAYLOAD_DIGEST,IDEMPOTENCY_KEY,ENVELOPE_DIGEST,STATUS,VERSION,CREATED_AT_MS) '
            'VALUES(:origin_receipt_id,:route,:route_version,:actor_id,:credential,:source_kind,:source_id,:source_attempt_id,:worker_key,'
            ':origin_fencing_token,:origin_lease_until_ms,:authority_digest,:profile_id,:profile_version,:model_id,:payload_digest,'
            ":idempotency_key,:fingerprint,'PREPARED',1,:now_ms)",
            dict(**selected,route=route['route_id'],route_version=route['version'],credential=context.credential_digest,
                fingerprint=fingerprint,now_ms=capacity._now_ms(tx)))
        identity_api._audit_tx(tx,context.actor,'MODEL_ORIGIN_REQUEST','MODEL_REQUEST',key,'ALLOW',
            'Original local source, credential, Worker and exact payload frozen for the registered coordinator')
        return _receipt(tx,key)
    return connection.execute_transaction_callback(perform)


def _peer(route,suffix,raw,context,body=None,*,method='POST'):
    request=urllib.request.Request(route['coordinator_url']+suffix,
        data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+raw,'Content-Type':'application/json'},method=method)
    ticket=model_dispatch.DispatchTicket(context,dict(admission_id='meta:'+digest(request.full_url)[:32],
        socket_ms=10000,idle_ms=10000,remaining_ms=10000))
    with ticket.open(request,timeout=10) as response:return decode_json(ticket.read_response(response,65536),max_bytes=65536)


class RemoteTicket(model_dispatch.DispatchTicket):
    def __init__(self,profile,payload,context,route,receipt):
        super().__init__(context)
        self.profile,self.payload,self.route,self.receipt=profile,payload,route,receipt
        self.sent=False;self.no_send=False;self.remote_unknown=False;self.remote_observation=None

    @property
    def request_id(self):return self.receipt.get('coordinator_request_id') or self.receipt['origin_receipt_id']

    def open(self,request,*,timeout,default_open=None):
        raw=common.secret(self.profile)
        try:
            if (request.full_url!=self.route['coordinator_url']+'/chat/completions'
                    or request.get_method()!='POST' or digest(decode_json(request.data))!=self.receipt['payload_digest']
                    or request.get_header('Authorization')!='Bearer '+raw):raise PermissionError('Origin transport changed after source admission')
            remote=_peer(self.route,'/reservations',raw,self.context,_envelope(self.receipt,self.route).model_dump(mode='json'))
            if remote.get('origin_receipt_id')!=self.receipt['origin_receipt_id'] or remote.get('envelope_digest')!=self.receipt['envelope_digest']:
                raise PermissionError('Coordinator reservation receipt does not match the frozen Origin request')
            self.receipt.update(coordinator_request_id=remote['coordinator_request_id'],admission_id=remote.get('admission_id'))
            if remote['status']!='RESERVED' or remote['admission_status']!='RESERVED':
                if remote['status'] in {'DISPATCHING','UNKNOWN'} or remote.get('admission_status') in {'DISPATCHING','UNKNOWN'}:
                    self.remote_unknown=True
                    raise ContinuityConflict('UNKNOWN_SEND','The exact coordinator attempt retains an unresolved prior send')
                raise model_dispatch.ModelNotDispatched('COORDINATOR_BUSY_NO_SEND','The shared coordinator did not provide an unused no-wait reservation')
            def authorize(tx):
                latest=_receipt(tx,self.receipt['origin_receipt_id'])
                if latest['status']!='PREPARED':raise PermissionError('The original Origin receipt already crossed its final authorization boundary')
                current,(fence,expiry)=_local(tx,self.context,self.profile,self.route,self.receipt['payload_digest'],self.payload)
                now=capacity._now_ms(tx)
                if fence!=int(latest['origin_fencing_token']):raise PermissionError('The original Origin Worker was replaced')
                proof=DispatchProof(envelope=_envelope(latest,self.route),coordinator_request_id=remote['coordinator_request_id'],
                    admission_id=remote['admission_id'],reservation_version=int(remote['reservation_version']),fencing_token=int(remote['fencing_token']),
                    authorized_at_ms=now,expires_at_ms=min(now+common.PROOF_MS,expiry,int(latest['origin_lease_until_ms'])))
                if proof.expires_at_ms<=now:raise PermissionError('The original Origin source lease expired before dispatch')
                _state(tx,latest,'DISPATCHING','ORIGIN_FINAL_AUTHORIZATION',coordinator_request_id=remote['coordinator_request_id'],
                    admission_id=remote['admission_id'],remote_fencing_token=int(remote['fencing_token']),
                    remote_reservation_version=int(remote['reservation_version']),authorized_at_ms=now,
                    proof_expires_at_ms=proof.expires_at_ms,proof_digest=digest(proof.model_dump(mode='json')))
                from . import processing_recovery
                if processing_recovery.schema_enabled():processing_recovery.on_origin_dispatch(tx,latest)
                identity_api._audit_tx(tx,self.context.actor,'MODEL_ORIGIN_FINAL_AUTH','MODEL_REQUEST',latest['origin_receipt_id'],
                    'ALLOW','Original source, credential and Worker rechecked in its own database after shared reservation')
                self.receipt=latest
                return common.encode_proof(proof,raw)
            encoded=connection.execute_transaction_callback(authorize)
            request.add_header('X-Chuanxu-Coordinator-Proof',encoded)
            self.record={**remote,'remaining_ms':int(remote['remaining_ms'])}
            self.started=time.monotonic();self.sent=True
            response=super().open(request,timeout=min(timeout,self.timeout_seconds(timeout)))
            try:
                if response.headers.get(observations.HEADER):
                    self.remote_observation=observations.decode(response.headers[observations.HEADER],self.receipt)
                    if self.remote_observation['request_complete']!='Y':raise ValueError('A successful coordinator response needs a complete observation')
            except Exception:
                response.close()
                raise
            return response
        except urllib.error.HTTPError as exc:
            if self.sent and exc.headers.get(observations.HEADER):
                self.remote_observation=observations.decode(exc.headers[observations.HEADER],self.receipt)
            if self.sent and exc.headers.get('X-Chuanxu-Coordinator-No-Send')=='1':
                self.no_send=True
                try:_peer(self.route,'/requests/'+self.receipt['coordinator_request_id']+'/cancel',raw,self.context,{})
                except Exception:pass
                raise model_dispatch.ModelNotDispatched('COORDINATOR_NO_SEND','The shared coordinator confirmed no provider dispatch') from None
            if self.sent and exc.headers.get('X-Chuanxu-Coordinator-Request-Complete')=='1':
                self.response_complete('COORDINATOR_COMPLETED_REJECTED')
                failure=ModelResultError('COORDINATOR_COMPLETED_REJECTED',request_complete=True)
                if self.remote_observation:
                    failure.observation=dict(model=self.profile['model_id'],request_complete=True,usage=self.remote_observation['usage'],
                        usage_observation='PROVIDER_REPORTED' if self.remote_observation['usage_provenance'] in {'PROVIDER_REPORTED','DERIVED_TOTAL'} else 'INCOMPLETE',
                        usage_field_provenance={'total_tokens':'SUM_OF_REPORTED_INPUT_OUTPUT'} if self.remote_observation['usage_provenance']=='DERIVED_TOTAL' else {})
                raise failure from None
            if not self.sent:
                self.no_send=True
                raise model_dispatch.ModelNotDispatched('COORDINATOR_RESERVATION_DENIED','The coordinator did not receive a provider dispatch request') from None
            raise
        except Exception as exc:
            if self.remote_unknown:raise
            if not self.sent:
                self.no_send=True
                if 'remote' in locals() and remote.get('coordinator_request_id'):
                    try:_peer(self.route,'/requests/'+remote['coordinator_request_id']+'/cancel',raw,self.context,{})
                    except Exception:pass
                if getattr(exc,'model_not_dispatched',False):raise
                raise model_dispatch.ModelNotDispatched('ORIGIN_AUTHORIZATION_DENIED','The Origin stopped before provider dispatch') from None
            raise

    def finish(self,error):
        if isinstance(error,ModelResultError) and error.request_complete:self.response_complete(error.code)
        status='UNKNOWN' if self.remote_unknown else 'KNOWN_NO_SEND' if self.no_send or not self.sent else 'COMPLETED' if self.complete else 'UNKNOWN'
        def persist(tx):
            latest=_receipt(tx,self.receipt['origin_receipt_id'])
            if latest['status'] in {'COMPLETED','KNOWN_NO_SEND','UNKNOWN'}:
                if latest['status']!=status:raise ContinuityConflict('ORIGIN_PROGRESS_CONFLICT','An existing terminal Origin observation cannot be overwritten')
                return
            if status!='KNOWN_NO_SEND':observations.persist(tx,self,error)
            links={key:self.receipt[key] for key in ('coordinator_request_id','admission_id') if self.receipt.get(key)}
            _state(tx,latest,status,'ORIGIN_KNOWN_NO_SEND' if status=='KNOWN_NO_SEND' else self.code if self.complete else 'COORDINATOR_SEND_UNCONFIRMED',**links)
        connection.execute_transaction_callback(persist)


@contextmanager
def dispatch(profile,payload,context,route):
    try:receipt=prepare(profile,payload,context,route)
    except Exception as exc:
        if not isinstance(exc,ContinuityConflict):exc.model_not_dispatched=True
        raise
    ticket=RemoteTicket(profile,payload,context,route,receipt)
    error=None
    try:yield ticket
    except BaseException as exc:error=exc;raise
    finally:
        try:ticket.finish(error)
        except Exception as exc:exc.model_ledger_failed=True;raise


def authorize_receipt_read(tx,actor,receipt):
    """Resolve current business read authority, independently of send/recovery.

    A completed Worker or expired dispatch credential is not a reason to claim
    that the source is still readable. Conversely, reading a terminal result
    does not require a SENDING attempt or permission to dispatch again. Sources
    without a durable typed read adapter remain unavailable through this view.
    """
    from . import processing_recovery as recovery
    kind,source=receipt['source_kind'],receipt['source_id']
    if kind in {'NATIVE','CHANNEL'} and source.startswith('EXE_'):
        from . import native_runtime
        mapped=row(tx.query_one('SELECT n.*,c.SOURCE_KIND FROM CX_PROCESSING_NATIVE_CALLS c '
            'JOIN CX_PROCESSING_NATIVE_ATTEMPTS n ON n.TASK_ATTEMPT_ID=c.TASK_ATTEMPT_ID '
            'WHERE c.SOURCE_ATTEMPT_ID=:attempt AND n.EXECUTION_ID=:execution',
            {'attempt':receipt['source_attempt_id'],'execution':source}))
        if (not mapped or mapped['source_kind']!=kind or mapped['worker_id']!=receipt['worker_key']
                or int(mapped['native_fencing_token'])!=int(receipt['origin_fencing_token'])
                or recovery._link(tx,mapped['continuity_id'])['actor_id']!=actor):
            raise PermissionError('The original Origin business source is unavailable')
        native_runtime.get_execution(actor,source,transaction=tx)
        return
    if not ((kind=='RETROSPECTIVE' and source.startswith('RJ_'))
            or (kind=='EVALUATION' and source.startswith('AQR_'))
            or (kind=='NATIVE' and source.startswith('MTU_'))):
        raise PermissionError('The original Origin business source is unavailable')
    from . import processing_runtime as adapter
    from .continuity_execution_links import authorize
    attempt=row(tx.query_one('SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt',
        {'attempt':receipt['source_attempt_id']}))
    if not attempt:raise PermissionError('The original Origin business source is unavailable')
    link=recovery._link(tx,attempt['continuity_id'])
    original=adapter._original(tx,link)
    original_source=original['link_id']
    expected_source=original_source.rsplit(':',1)[0] if source.startswith('MTU_') else original_source
    frozen=row(tx.query_one('SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain',
        {'chain':link['continuity_id']}))
    if (not frozen or original['actor_id']!=actor or expected_source!=source
            or int(attempt['fencing_token'])!=int(receipt['origin_fencing_token'])):
        raise PermissionError('The original Origin business source is unavailable')
    recovery._validate_target(tx,recovery._target(frozen).model_copy(update={'attempt_id':attempt['attempt_id']}))
    work._authorize(tx,actor,original['security_domain_id'],write=False)
    authorize(tx,actor,original['security_domain_id'],'TASK',original['canonical_task_id'])
    if kind=='RETROSPECTIVE':
        from . import continuity_retrospectives as retros
        job=row(tx.query_one('SELECT * FROM CX_RETROSPECTIVE_JOBS WHERE JOB_ID=:source',{'source':source}))
        if not job or job['created_by']!=actor or original['link_kind']!='RUNTIME':
            raise PermissionError('The original Origin business source is unavailable')
        adapter._same_job(tx,job['continuity_id'],original)
        retros._refs(tx,actor,job)
    elif kind=='EVALUATION':
        from . import answer_quality as quality
        job=row(tx.query_one('SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=:source',{'source':source}))
        if not job or job['actor_id']!=actor or original['link_kind']!='DIAGNOSTIC':
            raise PermissionError('The original Origin business source is unavailable')
        adapter._same_job(tx,job['continuity_id'],original)
        quality._authority(tx,actor,job)
        quality._sources(tx,actor,job)
    else:
        from . import governed_model_turns as turns
        if original['link_kind']!='RUNTIME' or original_source not in {source+':PROPOSAL',source+':FINAL'}:
            raise PermissionError('The original Origin business source is unavailable')
        turns._authorize_read(tx,actor,turns._root(tx,source,observer=actor))


def read_receipt(actor,receipt_id):
    def read(tx):
        work._lock_actor(tx,actor)
        record=_receipt(tx,receipt_id)
        if record['actor_id']!=actor:raise PermissionError('Origin request belongs to its original principal')
        authorize_receipt_read(tx,actor,record)
        result={key:record.get(key) for key in ('origin_receipt_id','source_kind','source_id','source_attempt_id','status','version',
            'profile_id','profile_version','coordinator_request_id','admission_id','remote_fencing_token','finish_code')}
        observed=row(tx.query_one('SELECT * FROM CX_MODEL_ORIGIN_OBSERVATIONS WHERE ORIGIN_RECEIPT_ID=:receipt',{'receipt':receipt_id}))
        result['observation']=observed or None
        result['resolution']=resolution_for_receipt(tx,record)
        return result
    return connection.execute_transaction_callback(read)


def authorize_original_receipt(tx,actor,receipt):
    """Dispatch to trusted business adapters; HTTP never supplies a callback."""
    from . import processing_recovery
    processing_recovery.authorize_origin_receipt(tx,actor,receipt)


def resolution_for_receipt(tx,receipt):
    value=row(tx.query_one('SELECT * FROM CX_MODEL_ORIGIN_RESOLUTIONS WHERE ORIGIN_RECEIPT_ID=:receipt',
        {'receipt':receipt['origin_receipt_id']}))
    if value and (value['route_id']!=receipt['route_id'] or int(value['route_version'])!=int(receipt['route_version'])
            or value['coordinator_request_id']!=receipt.get('coordinator_request_id') or value['admission_id']!=receipt.get('admission_id')
            or int(value['fencing_token'])!=int(receipt.get('remote_fencing_token') or 0)):
        raise PermissionError('The Origin transport resolution differs from its exact original reservation')
    return value or None


def reconcile_receipt(actor,receipt_id,value,*,authorize_source=authorize_original_receipt):
    """Explicit remote GET, then a final local authorization transaction.

    Never hold a local DB transaction across HTTP, reserve capacity, call a
    Provider, replace credentials or rewrite an original UNKNOWN observation.
    A terminal transport receipt never approves content or authorizes replay.
    """
    if not callable(authorize_source):raise PermissionError('Original business source authorization is required')
    request=ReceiptReconciliation.model_validate(value)
    fingerprint=digest(dict(receipt=receipt_id,request=request.model_dump(mode='json')))
    def original(tx):
        work._lock_actor(tx,actor)
        receipt=_receipt(tx,receipt_id)
        if receipt['actor_id']!=actor:raise PermissionError('Origin transport reconciliation requires its original principal')
        if authorize_source(tx,actor,receipt) is not None:raise TypeError('Original source authorization must check and return None')
        route=row(tx.query_one('SELECT * FROM CX_MODEL_COORD_ROUTES WHERE ROUTE_ID=:route FOR UPDATE',{'route':receipt['route_id']}))
        if not route or int(route['version'])!=int(receipt['route_version']):raise PermissionError('The original coordinator route changed')
        profile=common.profile(tx,receipt['profile_id'],receipt['profile_version'])
        _route(tx,profile,route)
        keyed=row(tx.query_one('SELECT REQUEST_DIGEST FROM CX_MODEL_ORIGIN_RESOLUTIONS WHERE REQUESTED_BY=:actor AND IDEMPOTENCY_KEY=:key',
            dict(actor=actor,key=request.idempotency_key)))
        if keyed and keyed['request_digest']!=fingerprint:raise ContinuityConflict('IDEMPOTENCY_CONFLICT','The explicit resolution key belongs to another request')
        prior=resolution_for_receipt(tx,receipt)
        if prior:
            if prior['requested_by']!=actor or prior['request_digest']!=fingerprint:
                raise ContinuityConflict('IDEMPOTENCY_CONFLICT','The original Origin transport already has a different explicit resolution')
            return receipt,route,profile,prior
        if int(receipt['version'])!=request.expected_version:raise ContinuityConflict('STALE_VERSION','The original Origin receipt changed')
        if receipt['status'] not in {'UNKNOWN','DISPATCHING'} or not receipt.get('coordinator_request_id') or not receipt.get('admission_id'):
            raise ContinuityConflict('ORIGIN_NOT_UNKNOWN','Only an exact unresolved remote Origin attempt can be reconciled')
        return receipt,route,profile,None
    receipt,route,profile,prior=connection.execute_transaction_callback(original)
    if prior:return dict(status='RESOLVED',resolution=prior,replayed=True,content_approved=False,replay_allowed=False)
    from .model_dispatch import DispatchContext
    context=DispatchContext(actor,receipt['source_kind'],receipt['source_id'],receipt['source_attempt_id'],
        receipt['original_credential_digest'],lambda *_:None,receipt['worker_key'])
    remote=_peer(route,'/requests/'+receipt['coordinator_request_id'],common.secret(profile),context,method='GET')
    if (remote.get('coordinator_request_id')!=receipt['coordinator_request_id'] or remote.get('origin_receipt_id')!=receipt_id
            or remote.get('admission_id')!=receipt['admission_id'] or remote.get('envelope_digest')!=receipt['envelope_digest']):
        raise PermissionError('The coordinator read did not identify the exact original Origin request')
    raw_resolution=remote.get('transport_resolution')
    resolved=CoordinatorResolution.model_validate(raw_resolution) if raw_resolution else None
    if resolved and (resolved.coordinator_request_id!=receipt['coordinator_request_id'] or resolved.origin_receipt_id!=receipt_id
            or resolved.admission_id!=receipt['admission_id'] or resolved.envelope_digest!=receipt['envelope_digest']
            or resolved.fencing_token!=int(receipt.get('remote_fencing_token') or 0)
            or resolved.admission_version<int(receipt.get('remote_reservation_version') or 1)
            or resolved.admission_status!=remote.get('admission_status') or resolved.central_status!=remote.get('status')):
        raise PermissionError('The coordinator terminal evidence differs from the frozen original reservation')
    peer_digest=digest(remote)
    def persist(tx):
        latest,current_route,current_profile,existing=original(tx)
        # Keep native timestamp and Decimal precision when comparing the full row.
        if latest!=receipt:raise ContinuityConflict('STALE_VERSION','The original Origin receipt changed during remote observation')
        if existing:return dict(status='RESOLVED',resolution=existing,replayed=True,content_approved=False,replay_allowed=False)
        if resolved is None:return dict(status='UNKNOWN',resolution=None,replayed=False,content_approved=False,replay_allowed=False)
        data=resolved.model_dump(mode='json')
        data.pop('origin_receipt_id');data.pop('envelope_digest')
        selected=dict(resolution_id=identifier('MRS'),origin_receipt_id=receipt_id,route_id=route['route_id'],route_version=route['version'],
            **data,observation_method='REGISTERED_COORDINATOR_GET',peer_receipt_digest=peer_digest,requested_by=actor,
            idempotency_key=request.idempotency_key,request_digest=fingerprint,reason=request.reason,observed_at_ms=capacity._now_ms(tx))
        columns=list(selected)
        tx.execute('INSERT INTO CX_MODEL_ORIGIN_RESOLUTIONS('+','.join(key.upper() for key in columns)+') VALUES ('+
            ','.join(':'+key for key in columns)+')',selected)
        identity_api._audit_tx(tx,actor,'MODEL_ORIGIN_RECONCILE','MODEL_REQUEST',receipt_id,'ALLOW',request.reason)
        return dict(status='RESOLVED',resolution=selected,replayed=False,content_approved=False,replay_allowed=False)
    return connection.execute_transaction_callback(persist)
