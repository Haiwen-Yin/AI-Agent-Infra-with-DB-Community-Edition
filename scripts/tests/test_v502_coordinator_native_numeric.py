"""Native-row normalization at the coordinator's strict admission boundary.

These tests use no database, HTTP transport or model generation.
"""
from copy import deepcopy
from decimal import Decimal

from pydantic import ValidationError
import pytest

from lib import model_coordinator as coordinator
from lib.agent_extension_contracts import digest
from lib.model_endpoint_contracts import ModelAdmission


def _inputs(version):
    return (
        dict(origin_id='origin-1'),
        dict(profile_id='profile-1',version=version,model_id='model-1',
             provider_url='http://provider.invalid/v1/chat/completions'),
        dict(credential_id='credential-1',created_by='actor-1'),
        dict(coordinator_request_id='coordinator-request-1',origin_receipt_id='origin-receipt-1',
             payload_digest='1'*64,credential_digest='2'*64),
    )


@pytest.mark.parametrize('native_version,expected',[
    (1,1),(18,18),(10**25,10**25),
    (Decimal('1'),1),(Decimal('1.000'),1),(Decimal('18'),18),
    (Decimal('1E+25'),10**25),
])
def test_native_profile_version_crosses_strict_admission_without_changing_provenance(native_version,expected):
    inputs=_inputs(native_version)
    original=deepcopy(inputs)

    admission=coordinator._admission(*inputs)
    validated=ModelAdmission.model_validate(admission)

    assert type(admission['profile_version']) is int
    assert type(validated.profile_version) is int
    assert validated.profile_version==expected
    source=dict(source_kind='GATEWAY',source_id='coordinator-request-1',source_attempt_id='origin-receipt-1')
    assert validated.model_dump()==dict(
        origin_id='origin-1',profile_id='profile-1',profile_version=expected,model_id='model-1',
        endpoint_url='http://provider.invalid/v1/chat/completions',input_digest='1'*64,
        credential_digest='2'*64,**source,idempotency_key='model:'+digest(source),
        reason='Authenticated model request admission')
    assert inputs==original
    assert type(inputs[1]['version']) is type(native_version)


@pytest.mark.parametrize('native_version',[
    0,-1,Decimal('0'),Decimal('-1'),Decimal('1.5'),Decimal('0.999999999999999999'),
    Decimal('NaN'),Decimal('sNaN'),Decimal('Infinity'),Decimal('-Infinity'),
    1.0,1.5,'1','1.0',True,False,None,
])
def test_invalid_native_profile_version_is_rejected_without_coercion(native_version):
    with pytest.raises(ValueError,match='native database revision must be a positive integer'):
        coordinator._admission(*_inputs(native_version))


@pytest.mark.parametrize('external_version',[
    Decimal('1'),Decimal('1.000'),Decimal('1.5'),Decimal('NaN'),
    1.0,1.5,'1','1.0',True,False,None,
])
def test_external_admission_still_requires_strict_integer_profile_version(external_version):
    admission=coordinator._admission(*_inputs(1))
    admission['profile_version']=external_version

    with pytest.raises(ValidationError) as failure:
        ModelAdmission.model_validate(admission)

    assert any(error['loc']==('profile_version',) and error['type']=='int_type'
               for error in failure.value.errors())
