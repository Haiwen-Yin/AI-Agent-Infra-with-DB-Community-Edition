"""Bounded capacity contracts. Identity claims never establish authorization."""
from typing import Annotated, Literal

from pydantic import Field, StrictInt, StringConstraints, model_validator

from .continuity_contracts import Contract, Identifier, Reason, Revision

Fingerprint = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


class CapacityPolicy(Contract):
    capacity: StrictInt = Field(default=1, ge=1, le=16)
    queue_ms: StrictInt = Field(default=60000, ge=0, le=3600000)
    socket_ms: StrictInt = Field(default=180000, ge=1000, le=600000)
    idle_ms: StrictInt = Field(default=60000, ge=1000, le=600000)
    overall_ms: StrictInt = Field(default=600000, ge=1000, le=7200000)
    reservation_ms: StrictInt = Field(default=30000, ge=1000, le=120000)

    @model_validator(mode="after")
    def deadline_order(self):
        if self.queue_ms >= self.overall_ms or self.reservation_ms > self.overall_ms:
            raise ValueError("The overall deadline must allow time after queue admission")
        return self


class NewCapacityGroup(Contract):
    resource_key: Identifier
    coordinator_id: Identifier
    policy: CapacityPolicy = Field(default_factory=CapacityPolicy)
    reason: Reason
    idempotency_key: Identifier


class CapacityRevision(Contract):
    expected_version: Revision
    policy: CapacityPolicy
    status: Literal["ACTIVE", "DRAINING"] = "ACTIVE"
    reason: Reason
    idempotency_key: Identifier


class CapacityOrigin(Contract):
    origin_id: Identifier
    principal_id: Identifier
    installation_key: Identifier
    reason: Reason
    idempotency_key: Identifier


class CapacityOriginState(Contract):
    expected_version: Revision
    status: Literal["ACTIVE", "REVOKED"]
    reason: Reason
    idempotency_key: Identifier


class CapacityAlias(Contract):
    endpoint_url: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
    profile_id: Identifier | None = None
    expected_version: Revision
    reason: Reason
    idempotency_key: Identifier


class ModelAdmission(Contract):
    origin_id: Identifier
    profile_id: Identifier
    profile_version: Revision
    model_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]
    endpoint_url: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
    input_digest: Fingerprint
    credential_digest: Fingerprint
    source_kind: Literal["NATIVE", "GATEWAY", "PORTAL", "CHANNEL", "PROBE", "RETROSPECTIVE", "EVALUATION", "EXTERNAL"]
    source_id: Identifier
    source_attempt_id: Identifier
    idempotency_key: Identifier
    reason: Reason


class ReservationClaim(Contract):
    expected_version: Revision
    fencing_token: Revision
    worker_key: Identifier
    credential_digest: Fingerprint
    reason: Reason
    idempotency_key: Identifier


class CapacityCancellation(Contract):
    expected_version: Revision
    reason: Reason
    idempotency_key: Identifier


class CapacityObservation(Contract):
    expected_version: Revision
    attempt_id: Identifier
    fencing_token: Revision
    evidence_digest: Fingerprint
    evidence_kind: Literal["COMPLETE_RESPONSE", "REMOTE_TERMINATED", "LOCAL_LIFECYCLE", "OPERATOR_CONFIRMATION", "TRANSPORT_UNKNOWN"]
    finish_code: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
    reason: Reason
    idempotency_key: Identifier


class OperatorCapacityResolution(CapacityObservation):
    evidence_kind: Literal["OPERATOR_CONFIRMATION"] = "OPERATOR_CONFIRMATION"
