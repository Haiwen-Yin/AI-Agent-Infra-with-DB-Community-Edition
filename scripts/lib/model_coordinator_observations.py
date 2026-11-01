"""Safe central measurements attached to the original Origin's durable receipt.

No prompts, answer bodies, secrets or second usage charges belong here. The
central request/admission IDs are opaque foreign metadata, not local authority.
"""
import base64

from . import connection,model_endpoint_capacity as capacity,model_observations
from .agent_extension_contracts import canonical,digest,row
from .continuity_state import ContinuityConflict
from .model_coordinator_contracts import CoordinatorObservation
from .model_results import ModelResultError

HEADER='X-Chuanxu-Coordinator-Observation'
COUNTS=('prompt_tokens','completion_tokens','total_tokens','cached_tokens','cache_write_tokens','reasoning_tokens')
TIMES=('queue_ms','first_content_ms','provider_ms','total_ms')


def central(record,*,transaction=None):
    def read(tx):
        observed=row(tx.query_one('SELECT * FROM CX_MODEL_RUNTIME_OBSERVATIONS WHERE ADMISSION_ID=:admission',
            {'admission':record['admission_id']}))
        if not observed:return None
        return CoordinatorObservation(coordinator_request_id=record['coordinator_request_id'],admission_id=record['admission_id'],
            request_complete=observed['request_complete'],result_state=observed['result_state'],finish_code=observed['finish_code'],
            usage={key:int(observed[key]) if observed[key] is not None else None for key in COUNTS},
            usage_provenance=observed['usage_provenance'],**{key:int(observed[key]) if observed[key] is not None else None for key in TIMES}).model_dump(mode='json')
    return read(transaction) if transaction is not None else connection.execute_transaction_callback(read)


def encode(value):
    validated=CoordinatorObservation.model_validate(value)
    return base64.urlsafe_b64encode(canonical(validated.model_dump(mode='json')).encode()).decode()


def decode(value,receipt):
    if not isinstance(value,str) or not 1<=len(value)<=8192:raise ValueError('A bounded coordinator observation is required')
    observed=CoordinatorObservation.model_validate_json(base64.b64decode(value,altchars=b'-_',validate=True)).model_dump(mode='json')
    if (observed['coordinator_request_id']!=receipt['coordinator_request_id'] or observed['admission_id']!=receipt['admission_id']
            or (observed['request_complete']=='N')!=(observed['result_state']=='UNKNOWN')):
        raise PermissionError('Coordinator observation differs from the original remote reservation')
    return observed


def persist(tx,ticket,error):
    receipt=ticket.receipt
    if not receipt.get('coordinator_request_id') or not receipt.get('admission_id'):
        raise PermissionError('A possible Origin send requires its exact coordinator reservation')
    safe=ticket.result_observation
    if safe is None:
        observed=error.observation if isinstance(error,ModelResultError) else getattr(error,'model_observation',{})
        safe=model_observations.safe_result(observed or {})
    remote=ticket.remote_observation
    if remote:
        if ticket.result_observation is not None and ticket.result_observation['usage']!=remote['usage']:
            raise ContinuityConflict('ORIGIN_USAGE_CONFLICT','Origin and coordinator usage observations differ')
        # These are measurements from the central immutable dispatch record.
        # A local failure can reject a complete answer without erasing counts.
        safe={'usage':remote['usage'],'usage_provenance':remote['usage_provenance']}
    complete=ticket.complete
    value=dict(origin_receipt_id=receipt['origin_receipt_id'],coordinator_request_id=receipt['coordinator_request_id'],
        admission_id=receipt['admission_id'],request_complete='Y' if complete else 'N',
        result_state='UNKNOWN' if not complete else 'REJECTED' if error is not None else 'COMPLETED',
        finish_code=error.code if isinstance(error,ModelResultError) else 'OUTPUT_REJECTED' if complete and error is not None
            else ticket.code if complete else 'COORDINATOR_SEND_UNCONFIRMED',usage_provenance=safe['usage_provenance'],
        **safe['usage'],**{key:remote[key] if remote else None for key in TIMES})
    fingerprint=digest(value)
    prior=row(tx.query_one('SELECT OBSERVATION_DIGEST FROM CX_MODEL_ORIGIN_OBSERVATIONS WHERE ORIGIN_RECEIPT_ID=:receipt',
        {'receipt':receipt['origin_receipt_id']}))
    if prior:
        if prior['observation_digest']!=fingerprint:raise ContinuityConflict('ORIGIN_OBSERVATION_CONFLICT','The original Origin already has a different immutable observation')
        return
    value.update(observation_digest=fingerprint,observed_at_ms=capacity._now_ms(tx))
    columns=list(value)
    tx.execute('INSERT INTO CX_MODEL_ORIGIN_OBSERVATIONS('+','.join(key.upper() for key in columns)+') VALUES ('+
        ','.join(':'+key for key in columns)+')',value)


def read_for_source(actor,source_kind,source_id,*,authorize_source,transaction=None):
    if not callable(authorize_source):raise PermissionError('Original business resource authorization is required')
    def read(tx):
        if authorize_source(tx,actor,source_id) is not None:raise TypeError('Source authorization must check and return None')
        values=tx.query('SELECT r.PROFILE_ID,r.PROFILE_VERSION,r.MODEL_ID,r.SOURCE_ATTEMPT_ID,r.STATUS AS ORIGIN_STATUS,o.* '
            'FROM CX_MODEL_ORIGIN_RECEIPTS r JOIN CX_MODEL_ORIGIN_OBSERVATIONS o ON o.ORIGIN_RECEIPT_ID=r.ORIGIN_RECEIPT_ID '
            'WHERE r.SOURCE_KIND=:kind AND r.SOURCE_ID=:source ORDER BY r.CREATED_AT_MS',
            dict(kind=source_kind,source=source_id))
        if len(values)>100:raise ContinuityConflict('OBSERVATION_BOUND','Origin observation count exceeds its business bound')
        for value in values:
            for key in ('profile_version',*COUNTS,*TIMES,'observed_at_ms'):
                if value.get(key) is not None:value[key]=int(value[key])
        return values
    return read(transaction) if transaction is not None else connection.execute_transaction_callback(read)
