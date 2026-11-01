"""A shared coordinator on the existing Gateway credential/capacity boundary.

Origins attest current local authorization after reservation. The coordinator
does not claim to query foreign databases or authenticate foreign actor IDs.
"""
import time

from . import connection,identity_api,model_dispatch,model_endpoint_capacity as capacity
from . import model_coordinator_common as common,model_coordinator_observations as observations
from .agent_extension_contracts import bounded_json,digest,row
from .continuity_state import ContinuityConflict
from .model_coordinator_contracts import OriginEnvelope,CoordinatorResolution
from .model_results import ModelResultError
from .model_native_numeric import native_revision


def _request(tx,binding_id,request_id):
    record=row(tx.query_one('SELECT * FROM CX_MODEL_COORD_REQUESTS WHERE BINDING_ID=:binding '
        'AND COORDINATOR_REQUEST_ID=:request_id FOR UPDATE',dict(binding=binding_id,request_id=request_id)))
    if not record:raise PermissionError('Coordinator request is unavailable')
    return record


def _state(tx,record,status,code,**fields):
    permitted={'admission_id','proof_digest','proof_expires_at_ms'}
    if set(fields)-permitted:raise ValueError('Unsupported coordinator progress field')
    params=dict(request_id=record['coordinator_request_id'],status=status,code=code,revision=int(record['version'])+1,**fields)
    assignments=''.join(','+key.upper()+'=:'+key for key in fields)
    tx.execute('UPDATE CX_MODEL_COORD_REQUESTS SET STATUS=:status,FINISH_CODE=:code,VERSION=:revision'+assignments+
        ' WHERE COORDINATOR_REQUEST_ID=:request_id',params)
    record.update(status=status,finish_code=code,version=params['revision'],**fields)


def _admission(binding,current,credential,record):
    source=dict(source_kind='GATEWAY',source_id=record['coordinator_request_id'],source_attempt_id=record['origin_receipt_id'])
    return dict(origin_id=binding['origin_id'],profile_id=current['profile_id'],profile_version=native_revision(current['version']),
        model_id=current['model_id'],endpoint_url=current['provider_url'],input_digest=record['payload_digest'],
        credential_digest=record['credential_digest'],**source,idempotency_key='model:'+digest(source),
        reason='Authenticated model request admission')


def reserve(raw,binding_id,value):
    envelope=OriginEnvelope.model_validate(value)
    fingerprint=digest(envelope.model_dump(mode='json'))
    def prepare(tx):
        binding,credential,current,group,policy=common.authenticated_binding(tx,raw,binding_id,envelope)
        if envelope.origin_lease_until_ms<=capacity._now_ms(tx):raise PermissionError('The original Origin authorization lease expired')
        prior=row(tx.query_one('SELECT * FROM CX_MODEL_COORD_REQUESTS WHERE BINDING_ID=:binding AND '
            '(ORIGIN_RECEIPT_ID=:receipt OR IDEMPOTENCY_KEY=:key) FOR UPDATE',
            dict(binding=binding_id,receipt=envelope.origin_receipt_id,key=envelope.idempotency_key)))
        if prior:
            if (prior['envelope_digest']!=fingerprint or prior['credential_digest']!=common.token_digest(raw)
                    or int(prior['binding_version'])!=int(binding['version'])):
                raise ContinuityConflict('IDEMPOTENCY_CONFLICT','Coordinator source request or original enrollment changed')
            return binding,credential,current,prior
        from .agent_extension_contracts import identifier
        request_id=identifier('LMR')
        data=envelope.model_dump(mode='json')
        params={**data,'request_id':request_id,'binding':binding_id,'binding_version':binding['version'],
            'actor':credential['created_by'],'credential':credential['credential_id'],'credential_digest':common.token_digest(raw),
            'fingerprint':fingerprint,'now_ms':capacity._now_ms(tx)}
        tx.execute('INSERT INTO CX_MODEL_COORD_REQUESTS(COORDINATOR_REQUEST_ID,BINDING_ID,BINDING_VERSION,ORIGIN_RECEIPT_ID,'
            'INSTALLATION_KEY,ACTOR_ID,CREDENTIAL_ID,CREDENTIAL_DIGEST,ORIGIN_ACTOR_ID,SOURCE_KIND,SOURCE_ID,SOURCE_ATTEMPT_ID,'
            'WORKER_KEY,ORIGIN_FENCING_TOKEN,ORIGIN_LEASE_UNTIL_MS,AUTHORITY_DIGEST,ORIGIN_PROFILE_ID,ORIGIN_PROFILE_VERSION,'
            'PROFILE_ID,PROFILE_VERSION,GROUP_ID,POLICY_REVISION,MODEL_ID,PAYLOAD_DIGEST,IDEMPOTENCY_KEY,ENVELOPE_DIGEST,STATUS,VERSION,CREATED_AT_MS) '
            'VALUES(:request_id,:binding,:binding_version,:origin_receipt_id,:installation_key,:actor,:credential,:credential_digest,'
            ':origin_actor_id,:source_kind,:source_id,:source_attempt_id,:worker_key,:origin_fencing_token,:origin_lease_until_ms,'
            ':authority_digest,:origin_profile_id,:origin_profile_version,:profile_id,:profile_version,:group_id,:policy_revision,'
            ":model_id,:payload_digest,:idempotency_key,:fingerprint,'PREPARED',1,:now_ms)",params)
        identity_api._audit_tx(tx,credential['created_by'],'MODEL_COORDINATOR_SOURCE','MODEL_REQUEST',request_id,'ALLOW',
            'Authenticated enrolled installation froze its original source request')
        return binding,credential,current,_request(tx,binding_id,request_id)
    binding,credential,current,record=connection.execute_transaction_callback(prepare)
    if record['status']!='PREPARED':return read_request(raw,binding_id,record['coordinator_request_id'])
    admitted=capacity.admit(credential['created_by'],binding['group_id'],_admission(binding,current,credential,record))
    if admitted['status']=='QUEUED':
        admitted=capacity.cancel_admission(credential['created_by'],admitted['admission_id'],dict(expected_version=admitted['version'],
            reason='Cross-installation Origin never queues while holding its original Worker lease',
            idempotency_key='coord-no-wait:'+record['coordinator_request_id']))
    def attach(tx):
        common.authenticated_binding(tx,raw,binding_id,envelope)
        latest=_request(tx,binding_id,record['coordinator_request_id'])
        if latest['status']=='PREPARED':
            _state(tx,latest,'RESERVED' if admitted['status']=='RESERVED' else 'KNOWN_NO_SEND',
                'RESERVED' if admitted['status']=='RESERVED' else 'COORDINATOR_BUSY_NO_SEND',admission_id=admitted['admission_id'])
        return latest
    connection.execute_transaction_callback(attach)
    return read_request(raw,binding_id,record['coordinator_request_id'])


def read_request(raw,binding_id,request_id):
    def read(tx):
        binding,credential,current,group,policy=common.authenticated_binding(tx,raw,binding_id,dispatch=False)
        record=_request(tx,binding_id,request_id)
        if record['credential_digest']!=common.token_digest(raw) or record['credential_id']!=credential['credential_id']:
            raise PermissionError('Coordinator request retains its original enrolled Gateway credential')
        admission=capacity._state(tx,record['admission_id']) if record.get('admission_id') else None
        if admission and (admission['source_id']!=request_id or admission['source_attempt_id']!=record['origin_receipt_id']
                or admission['source_kind']!='GATEWAY' or admission['actor_id']!=record['actor_id']
                or admission['credential_digest']!=record['credential_digest']):
            raise PermissionError('The central capacity admission differs from its original enrolled request')
        policy=row(tx.query_one('SELECT * FROM CX_MODEL_CAP_REVISIONS WHERE GROUP_ID=:group_id AND REVISION_NO=:revision',
            dict(group_id=record['group_id'],revision=record['policy_revision'])))
        now=capacity._now_ms(tx)
        observed=observations.central(record,transaction=tx) if admission else None
        complete=bool(observed and observed['request_complete']=='Y')
        resolution=None
        if admission:
            attempt=row(tx.query_one('SELECT * FROM CX_MODEL_CAP_ATTEMPTS WHERE ADMISSION_ID=:admission',{'admission':admission['admission_id']}))
            if not attempt and admission['status'] in {'CANCELLED','EXPIRED','REJECTED'}:
                state=dict(request_id=request_id,admission_id=admission['admission_id'],version=int(admission['version']),status=admission['status'])
                resolution=dict(resolution_kind='KNOWN_NO_SEND',evidence_id=request_id,evidence_kind='NO_SEND_STATE',
                    evidence_digest=digest(state),evidence_at_ms=now,attempt_id=None)
            elif attempt and admission['status']=='COMPLETED' and int(attempt['fencing_token'])==int(admission['fencing_token']):
                evidence=row(tx.query_one('SELECT * FROM CX_MODEL_CAP_EVIDENCE WHERE ADMISSION_ID=:admission AND ATTEMPT_ID=:attempt '
                    'AND RESOURCE_VERSION=:revision ORDER BY CREATED_AT_MS DESC,EVIDENCE_ID DESC FETCH FIRST 1 ROWS ONLY',
                    dict(admission=admission['admission_id'],attempt=attempt['attempt_id'],revision=admission['version'])))
                valid=bool(evidence and (attempt['status']=='RECONCILED' and evidence['evidence_kind'] in {'LOCAL_LIFECYCLE','REMOTE_TERMINATED','OPERATOR_CONFIRMATION'}
                    or attempt['status']=='COMPLETED' and evidence['evidence_kind'] in {'COMPLETE_RESPONSE','REMOTE_TERMINATED'}))
                if valid:resolution=dict(resolution_kind='TRANSPORT_TERMINATED',evidence_id=evidence['evidence_id'],evidence_kind=evidence['evidence_kind'],
                    evidence_digest=evidence['evidence_digest'],evidence_at_ms=int(evidence['created_at_ms']),attempt_id=attempt['attempt_id'])
            if resolution:
                resolution=CoordinatorResolution(coordinator_request_id=request_id,origin_receipt_id=record['origin_receipt_id'],
                    envelope_digest=record['envelope_digest'],admission_id=admission['admission_id'],admission_version=int(admission['version']),
                    central_status=record['status'],admission_status=admission['status'],
                    fencing_token=int(admission['fencing_token']),request_complete='Y' if complete else 'N',**resolution).model_dump(mode='json')
        # Read only: no reserve, sweep, local/remote reconciliation or retry.
        return dict(coordinator_request_id=request_id,origin_receipt_id=record['origin_receipt_id'],status=record['status'],
            version=record['version'],finish_code=record.get('finish_code'),envelope_digest=record['envelope_digest'],
            admission_id=record.get('admission_id'),admission_status=admission['status'] if admission else None,
            reservation_version=int(admission['version']) if admission else None,fencing_token=int(admission['fencing_token']) if admission else None,
            proof_expires_at_ms=record.get('proof_expires_at_ms'),request_complete=complete,transport_resolution=resolution,
            socket_ms=int(policy['socket_ms']),idle_ms=int(policy['idle_ms']),remaining_ms=max(0,int(admission['overall_until_ms'])-now) if admission else 0)
    return connection.execute_transaction_callback(read)


def _payload(profile,payload):
    from . import native_runtime,provider_capability_probes as probes
    bounded_json(payload,maximum=6000000)
    allowed={'model','messages','stream','stream_options','response_format','tools','tool_choice','max_tokens','temperature',
             'reasoning_effort','preserve_thinking'}
    if (not isinstance(payload,dict) or set(payload)-allowed or payload.get('model')!=profile['model_id']
            or type(payload.get('stream')) is not bool or not isinstance(payload.get('messages'),list)
            or not 1<=len(payload['messages'])<=100):raise ValueError('Unsupported exact coordinator Chat Completions request')
    stream=payload['stream']
    fields={key:payload[key] for key in ('response_format','tools','tool_choice','max_tokens','temperature') if key in payload}
    if stream and (fields or payload.get('stream_options')!={'include_usage':True}):
        raise ValueError('The enrolled streaming subset is the native text stream contract')
    expected=probes.apply_parameters(profile,dict(model=profile['model_id'],messages=native_runtime._provider_messages(payload['messages']),
        stream=stream,**({'stream_options':{'include_usage':True}} if stream else fields)))
    if digest(expected)!=digest(payload):raise PermissionError('Origin and coordinator exact model parameter contracts differ')
    kind='tool' if 'tools' in fields else 'structured' if 'response_format' in fields else 'text'
    return stream,fields,kind


def _managed_image(tx,profile,payload,envelope):
    image=any(isinstance(item.get('content'),list) for item in payload.get('messages',[]))
    if not image:return False
    if (envelope.source_kind!='EXTERNAL' or envelope.source_id!=envelope.source_attempt_id
            or not envelope.source_id.startswith('MU_') or payload.get('stream') is not False
            or 'tools' in payload or 'response_format' in payload):
        raise PermissionError('Remote images require the original bounded managed-input source contract')
    evidence=tx.query_one("SELECT PROBE_ID FROM CX_PROVIDER_CAP_PROBES WHERE PROFILE_ID=:profile AND PROFILE_VERSION=:version "
        "AND MODEL_ID=:model AND API_DIALECT='CHAT_COMPLETIONS' AND CAPABILITY_KEY='IMAGE_INPUT' AND STATUS='VERIFIED' "
        "AND EXPIRES_AT>CURRENT_TIMESTAMP FOR UPDATE",dict(profile=profile['profile_id'],version=int(profile['version']),model=profile['model_id']))
    if not evidence:raise model_dispatch.ModelNotDispatched('COORDINATOR_IMAGE_CAPABILITY_DENIED','The coordinator Profile has no independent current verified PNG-input capability')
    return True


def complete(raw,binding_id,proof_value,payload):
    from . import native_runtime,model_usage_api as usage,model_governance_api as governance
    proof=common.decode_proof(proof_value,raw)
    envelope=proof.envelope
    proof_digest=digest(proof.model_dump(mode='json'))
    def claim(tx):
        binding,credential,current,group,policy=common.authenticated_binding(tx,raw,binding_id,envelope)
        record=_request(tx,binding_id,proof.coordinator_request_id)
        if (record['envelope_digest']!=digest(envelope.model_dump(mode='json'))
                or record['credential_digest']!=common.token_digest(raw)
                or record['payload_digest']!=digest(payload) or record['admission_id']!=proof.admission_id
                or int(record['binding_version'])!=int(binding['version'])):
            raise PermissionError('Coordinator dispatch differs from its exact original reservation')
        if record['status']=='COMPLETED':
            if record['proof_digest']!=proof_digest:raise PermissionError('Completed replay must retain its original proof')
            return record,current,credential,governance.replay_snapshot(record['coordinator_request_id'],transaction=tx)
        if record['status'] in {'DISPATCHING','UNKNOWN'}:
            raise ContinuityConflict('UNKNOWN_SEND','An earlier coordinator dispatch cannot be repeated')
        if record['status']!='RESERVED':raise model_dispatch.ModelNotDispatched('COORDINATOR_NOT_RESERVED','The coordinator request has no unused reservation')
        reservation=capacity._state(tx,proof.admission_id)
        if (reservation['status']!='RESERVED' or int(reservation['version'])!=proof.reservation_version
                or int(reservation['fencing_token'])!=proof.fencing_token):
            raise model_dispatch.ModelNotDispatched('COORDINATOR_RESERVATION_FENCED','The exact original reservation is no longer unused')
        now=capacity._now_ms(tx)
        if (proof.authorized_at_ms>now+5000 or proof.expires_at_ms<=now or proof.expires_at_ms<=proof.authorized_at_ms
                or proof.expires_at_ms-proof.authorized_at_ms>common.PROOF_MS
                or proof.expires_at_ms>envelope.origin_lease_until_ms):
            raise model_dispatch.ModelNotDispatched('ORIGIN_PROOF_EXPIRED','The final Origin authorization proof is no longer current')
        _payload(current,payload)
        _managed_image(tx,current,payload,envelope)
        _state(tx,record,'DISPATCHING','ORIGIN_FINAL_AUTHORIZATION_ACCEPTED',proof_digest=proof_digest,proof_expires_at_ms=proof.expires_at_ms)
        identity_api._audit_tx(tx,credential['created_by'],'MODEL_COORDINATOR_FINAL_AUTH','MODEL_REQUEST',record['coordinator_request_id'],
            'ALLOW','Original installation reauthorized its frozen source, credential and Worker immediately before dispatch')
        return record,current,credential,None
    record,current,credential,replayed=connection.execute_transaction_callback(claim)
    if replayed is not None:return replayed
    request_id=record['coordinator_request_id'];started=time.monotonic();parsed=None;settled=False
    key='coord:'+digest(dict(binding=binding_id,receipt=envelope.origin_receipt_id))
    try:
        stream,fields,kind=_payload(current,payload)
        connection.execute_transaction_callback(lambda tx:tx.execute('INSERT INTO CX_MODEL_REQUESTS(REQUEST_ID,ACTOR_PRINCIPAL_ID,AGENT_ID,PROFILE_ID,'
            'MODEL_ID,STATUS,IDEMPOTENCY_KEY,INPUT_DIGEST,CORRELATION_ID,CREDENTIAL_ID) '
            "VALUES(:id,:actor,NULL,:profile,:model,'AUTHORIZED',:key,:input_digest,:correlation,:credential)",
            dict(id=request_id,actor=record['actor_id'],profile=current['profile_id'],model=current['model_id'],key=key,
                input_digest=usage._digest(payload['messages']),correlation=request_id,credential=credential['credential_id'])))
        governance.reserve_quota(request_id,record['actor_id'],credential['credential_id'],'',current['profile_id'],current['model_id'])
        def reauthorize(tx,admission):
            binding,fresh,profile,group,policy=common.authenticated_binding(tx,raw,binding_id,envelope)
            frozen=_request(tx,binding_id,request_id)
            if (frozen['status']!='DISPATCHING' or frozen['proof_digest']!=proof_digest
                    or capacity._now_ms(tx)>=proof.expires_at_ms or admission['input_digest']!=record['payload_digest']
                    or int(admission['fencing_token'])!=proof.fencing_token
                    or admission['admission_id']!=proof.admission_id):
                raise PermissionError('The final Origin proof, payload or exact coordinator reservation was fenced')
            _managed_image(tx,profile,payload,envelope)
        origin_id=connection.execute_transaction_callback(lambda tx:common.authenticated_binding(tx,raw,binding_id,envelope)[0]['origin_id'])
        with model_dispatch.authenticated_context(record['actor_id'],'GATEWAY',request_id,envelope.origin_receipt_id,
                credential_digest=record['credential_digest'],reauthorize=reauthorize,worker_key='coord:'+request_id,
                origin_id=origin_id,allow_wait=False):
            parsed=native_runtime._stream_llm(current,payload['messages'],lambda _:None) if stream else native_runtime._call_llm(
                current,payload['messages'],output_kind=kind,request_fields=fields,
                managed_input=any(isinstance(item.get('content'),list) for item in payload['messages']))
        usage._write_usage(request_id,record['actor_id'],'',str(current.get('profile_key') or current['profile_id']),parsed['model'],
            parsed['usage'],'PROVIDER_REPORTED' if parsed['usage_observation']=='PROVIDER_REPORTED' else 'INCOMPLETE',started,
            'SUCCEEDED',key,field_provenance=parsed.get('usage_field_provenance'))
        settled=True
        message=dict(role='assistant',content=parsed['content'])
        if parsed.get('tool_calls'):message['tool_calls']=parsed['tool_calls']
        response=dict(id=request_id,model=parsed['model'],choices=[dict(index=0,message=message,finish_reason=parsed['finish_reason'])],
            usage=parsed['usage'],usage_observation=parsed['usage_observation'],usage_field_provenance=parsed.get('usage_field_provenance') or {})
        response['chuanxu_observation']=observations.central(record)
        governance.finalize_replayable_success(request_id,response)
        connection.execute_transaction_callback(lambda tx:_state(tx,_request(tx,binding_id,request_id),'COMPLETED','COORDINATOR_RESPONSE_COMPLETE'))
        return response
    except Exception as exc:
        admission=capacity.read_admission(record['actor_id'],record['admission_id'])
        no_send=admission['status'] in {'RESERVED','QUEUED','REJECTED','CANCELLED','EXPIRED'} and not admission.get('attempt_id')
        if no_send and admission['status'] in {'RESERVED','QUEUED'}:
            admission=capacity.cancel_admission(record['actor_id'],record['admission_id'],dict(expected_version=admission['version'],
                reason='Coordinator preflight did not dispatch the original request',idempotency_key='coord-preflight:'+request_id))
        observed_error=model_dispatch.ModelNotDispatched('COORDINATOR_NO_SEND','The coordinator stopped before provider dispatch') if no_send else exc
        failure=usage._forward_failure(request_id,record['actor_id'],'',current,started,key,observed_error,
            parsed=parsed,settled=settled,streaming=bool(payload.get('stream')))
        complete=admission['status']=='COMPLETED'
        state='KNOWN_NO_SEND' if no_send else 'COMPLETED' if complete else 'UNKNOWN'
        connection.execute_transaction_callback(lambda tx:_state(tx,_request(tx,binding_id,request_id),state,
            'COORDINATOR_NO_SEND' if no_send else 'COORDINATOR_COMPLETED_REJECTED' if complete else 'COORDINATOR_REMOTE_UNCONFIRMED'))
        if no_send:raise model_dispatch.ModelNotDispatched('COORDINATOR_NO_SEND','The coordinator rejected the request before provider dispatch') from None
        if complete:
            rejected=ModelResultError('COORDINATOR_COMPLETED_REJECTED',request_complete=True)
            rejected.observation=failure.model_observation
            rejected.model_ledger_failed=failure.model_ledger_failed
            rejected.coordinator_observation=observations.central(record)
            raise rejected from None
        unknown=ContinuityConflict('UNKNOWN_SEND','The original coordinator attempt must be reconciled before any further send')
        unknown.coordinator_observation=observations.central(record)
        raise unknown from None


def cancel_reservation(raw,binding_id,request_id):
    def read(tx):
        common.authenticated_binding(tx,raw,binding_id,dispatch=False)
        record=_request(tx,binding_id,request_id)
        if record['credential_digest']!=common.token_digest(raw):raise PermissionError('The original coordinator credential is required')
        return record
    record=connection.execute_transaction_callback(read)
    if record['status'] in {'PREPARED','RESERVED'} and record.get('admission_id'):
        admitted=capacity.read_admission(record['actor_id'],record['admission_id'])
        if admitted['status'] in {'QUEUED','RESERVED'}:
            admitted=capacity.cancel_admission(record['actor_id'],record['admission_id'],dict(expected_version=admitted['version'],
                reason='Origin stopped before dispatching its original frozen request',idempotency_key='coord-origin-cancel:'+request_id))
        if admitted['status'] in {'CANCELLED','EXPIRED','REJECTED'}:
            connection.execute_transaction_callback(lambda tx:_state(tx,_request(tx,binding_id,request_id),'KNOWN_NO_SEND','ORIGIN_CANCELLED_BEFORE_SEND'))
    return read_request(raw,binding_id,request_id)
