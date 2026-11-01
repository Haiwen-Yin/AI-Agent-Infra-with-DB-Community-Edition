"""Closed contracts for explicitly enrolled cross-installation model transport."""
from typing import Annotated,Literal

from pydantic import Field,StrictInt,model_validator

from .continuity_contracts import Contract,Identifier,Reason,Revision
from .model_endpoint_contracts import Fingerprint

Millis=Annotated[StrictInt,Field(ge=1,le=9999999999999999999)]
SourceKind=Literal['NATIVE','GATEWAY','PORTAL','CHANNEL','PROBE','RETROSPECTIVE','EVALUATION','EXTERNAL']


class CoordinatorBinding(Contract):
    group_id:Identifier
    expected_group_version:Revision
    policy_revision:Revision
    origin_id:Identifier
    installation_key:Identifier
    credential_id:Identifier
    profile_id:Identifier
    profile_version:Revision
    origin_profile_id:Identifier
    origin_profile_version:Revision
    reason:Reason
    idempotency_key:Identifier


class CoordinatorRoute(Contract):
    profile_id:Identifier
    profile_version:Revision
    coordinator_url:Annotated[str,Field(min_length=1,max_length=1000)]
    binding_id:Identifier
    group_id:Identifier
    policy_revision:Revision
    origin_id:Identifier
    installation_key:Identifier
    coordinator_profile_id:Identifier
    coordinator_profile_version:Revision
    reason:Reason
    idempotency_key:Identifier


class OriginEnvelope(Contract):
    origin_receipt_id:Identifier
    installation_key:Identifier
    origin_actor_id:Identifier
    source_kind:SourceKind
    source_id:Identifier
    source_attempt_id:Identifier
    worker_key:Identifier
    origin_fencing_token:Revision
    origin_lease_until_ms:Millis
    authority_digest:Fingerprint
    origin_profile_id:Identifier
    origin_profile_version:Revision
    group_id:Identifier
    policy_revision:Revision
    profile_id:Identifier
    profile_version:Revision
    model_id:Annotated[str,Field(min_length=1,max_length=256)]
    payload_digest:Fingerprint
    idempotency_key:Identifier


class DispatchProof(Contract):
    envelope:OriginEnvelope
    coordinator_request_id:Identifier
    admission_id:Identifier
    reservation_version:Revision
    fencing_token:Revision
    authorized_at_ms:Millis
    expires_at_ms:Millis


class ProofEnvelope(Contract):
    proof:DispatchProof
    signature:Fingerprint


class ReceiptReconciliation(Contract):
    expected_version:Revision
    reason:Reason
    idempotency_key:Identifier


TokenCount=Annotated[StrictInt,Field(ge=0,le=2**63-1)]
Duration=Annotated[StrictInt,Field(ge=0,le=720000000)]


class CoordinatorUsage(Contract):
    prompt_tokens:TokenCount|None=None
    completion_tokens:TokenCount|None=None
    total_tokens:TokenCount|None=None
    cached_tokens:TokenCount|None=None
    cache_write_tokens:TokenCount|None=None
    reasoning_tokens:TokenCount|None=None


class CoordinatorObservation(Contract):
    coordinator_request_id:Identifier
    admission_id:Identifier
    request_complete:Literal['Y','N']
    result_state:Literal['COMPLETED','REJECTED','UNKNOWN']
    finish_code:Identifier
    usage:CoordinatorUsage
    usage_provenance:Literal['PROVIDER_REPORTED','DERIVED_TOTAL','PARTIAL','INCOMPLETE']
    queue_ms:Duration|None=None
    first_content_ms:Duration|None=None
    provider_ms:Duration|None=None
    total_ms:Duration|None=None


class CoordinatorResolution(Contract):
    coordinator_request_id:Identifier
    origin_receipt_id:Identifier
    envelope_digest:Fingerprint
    admission_id:Identifier
    admission_version:Revision
    central_status:Literal['PREPARED','RESERVED','DISPATCHING','COMPLETED','KNOWN_NO_SEND','UNKNOWN']
    admission_status:Literal['COMPLETED','CANCELLED','EXPIRED','REJECTED']
    attempt_id:Identifier|None=None
    fencing_token:Annotated[StrictInt,Field(ge=0)]
    resolution_kind:Literal['KNOWN_NO_SEND','TRANSPORT_TERMINATED']
    evidence_id:Identifier
    evidence_kind:Literal['NO_SEND_STATE','COMPLETE_RESPONSE','REMOTE_TERMINATED','LOCAL_LIFECYCLE','OPERATOR_CONFIRMATION']
    evidence_digest:Fingerprint
    evidence_at_ms:Millis
    request_complete:Literal['Y','N']

    @model_validator(mode='after')
    def exact_terminal(self):
        if self.resolution_kind=='KNOWN_NO_SEND':
            if (self.attempt_id is not None or self.evidence_kind!='NO_SEND_STATE' or self.request_complete!='N'
                    or self.admission_status not in {'CANCELLED','EXPIRED','REJECTED'}):
                raise ValueError('A known-no-send resolution requires an unused terminal reservation')
        elif (not self.attempt_id or self.fencing_token<1 or self.evidence_kind=='NO_SEND_STATE'
                or self.admission_status!='COMPLETED'):
            raise ValueError('A terminated transport resolution requires its exact completed dispatch attempt')
        return self
