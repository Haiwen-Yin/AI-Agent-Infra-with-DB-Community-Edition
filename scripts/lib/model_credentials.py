"""Original server-authenticated credentials for controlled model dispatch.

Only HTTP authentication dependencies install server_session. Credential hashes
are internal receipts, never public bearer inputs or substitutes for credentials.
Business/source/Worker authorization remains the dispatcher's responsibility.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
import re

from . import connection, identity_api
from .agent_extension_contracts import row

_session = ContextVar('model_original_web_session', default=None)


@dataclass(frozen=True)
class CredentialBinding:
    actor: str
    kind: str
    credential_digest: str
    required_scope: str = ''
    instance_id: str = ''
    fencing_token: int = 0
    auth_method: str = ''
    permission_version: int = 0
    mfa_level: str = ''
    node_id: str = ''
    created_at: str = ''


@contextmanager
def server_session(session):
    """Install an already authenticated dependency result, never request JSON."""
    token = _session.set(dict(session) if session is not None else None)
    try:
        yield
    finally:
        try:
            _session.reset(token)
        except ValueError:
            # Streaming HTTP cleanup may run in another worker Context.
            _session.set(None)


def _web(tx, actor, credential_digest):
    record = row(tx.query_one(
        'SELECT SESSION_DIGEST,PRINCIPAL_ID,AUTH_METHOD,MFA_LEVEL,NODE_ID,PERMISSION_VERSION,'
        'CREATED_AT,EXPIRES_AT,REVOKED_AT FROM CX_WEB_SESSIONS WHERE SESSION_DIGEST=:digest FOR UPDATE',
        {'digest': credential_digest}))
    if not record or record.get('principal_id') != actor or record.get('revoked_at') is not None:
        raise PermissionError('The original Web Session is no longer current')
    auth_method = str(record.get('auth_method') or '')
    scope = auth_method.upper().rsplit(':', 1)[-1]
    if scope not in {'DASHBOARD', 'PORTAL'}:
        raise PermissionError('The original Web Session scope is unavailable')
    now = identity_api._now()
    created, expiry = identity_api._timestamp(record.get('created_at')), identity_api._timestamp(record.get('expires_at'))
    policy = row(tx.query_one('SELECT ABSOLUTE_TIMEOUT_SECONDS FROM CX_WEB_SESSION_POLICIES WHERE POLICY_KEY=:session_scope',
                              {'session_scope': scope}))
    if not policy:
        raise PermissionError('The original Web Session policy is unavailable')
    absolute = max(60, min(identity_api.SESSION_MAX_SECONDS, int(policy.get('absolute_timeout_seconds') or 0)))
    if created is None or expiry is None or expiry <= now or created + timedelta(seconds=absolute) <= now:
        raise PermissionError('The original Web Session expired')
    principal = row(tx.query_one('SELECT STATUS,MFA_REQUIRED,PERMISSION_VERSION FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor',
                                 {'actor': actor}))
    mfa = str(record.get('mfa_level') or 'NONE').upper()
    required = principal.get('mfa_required') is True or str(principal.get('mfa_required') or '').upper() in {'Y', 'YES', 'TRUE', '1'}
    if (principal.get('status') != 'ACTIVE' or mfa == 'SETUP' or required and mfa == 'NONE'
            or int(principal.get('permission_version') or 1) != int(record.get('permission_version') or 1)):
        raise PermissionError('The original Web Session authority changed')
    if not identity_api.entry_allowed(actor, 'PORTAL' if scope == 'PORTAL' else 'APP'):
        raise PermissionError('The original Web Session entry is no longer allowed')
    return CredentialBinding(actor, 'WEB', credential_digest, auth_method=auth_method,
        permission_version=int(record.get('permission_version') or 1), mfa_level=mfa,
        node_id=str(record.get('node_id') or ''), created_at=created.isoformat())


def recheck(tx, binding):
    """Recheck the original identity; never mint a replacement token or Session."""
    if not isinstance(binding, CredentialBinding):
        raise PermissionError('An original authenticated credential is required')
    if binding.kind == 'WEB':
        current = _web(tx, binding.actor, binding.credential_digest)
        if current != binding:
            raise PermissionError('The original Web Session binding changed')
    elif binding.kind == 'AGENT':
        from .agent_gateway_api import _authenticate_access_token_digest
        def credential_query(statement, parameters):
            # Token revocation and instance fencing must serialize with the
            # final dispatch decision, including direct token-only revocation.
            return tx.query_one(statement + ' FOR UPDATE', parameters)
        current = _authenticate_access_token_digest(binding.credential_digest, binding.actor, binding.instance_id,
            binding.required_scope, operation=binding.required_scope or 'work', query_one=credential_query)
        if not current or int(current.get('fencing_token') or -1) != binding.fencing_token:
            raise PermissionError('The original Agent credential was revoked, expired or fenced')
    else:
        raise PermissionError('Unsupported original credential binding')
    return binding.credential_digest


def capture(actor, *, required_scope='', session=None, tx=None):
    """Capture only a trusted request Session or existing machine transport.

    No credential evidence returns None. This preserves unregistered model
    routes; a selected controlled resource then fails closed at model_dispatch.
    """
    from .continuity_bindings import _transport
    trusted = session if session is not None else _session.get()
    machine = _transport.get()
    session_digest = str((trusted or {}).get('session_digest') or '')
    if session_digest and machine is not None:
        raise PermissionError('Mixed original credential identities are not supported')
    if session_digest:
        if not re.fullmatch('[0-9a-f]{64}', session_digest) or str(trusted.get('principal_id') or '') != actor:
            raise PermissionError('The original Web Session identity does not match')
        def capture_web(reader):
            binding = _web(reader, actor, session_digest)
            if (trusted.get('permission_version') is not None
                    and int(trusted['permission_version']) != binding.permission_version):
                raise PermissionError('The authenticated Web Session version changed')
            if trusted.get('auth_method') is not None and trusted['auth_method'] != binding.auth_method:
                raise PermissionError('The authenticated Web Session scope changed')
            return binding
        return capture_web(tx) if tx is not None else connection.execute_transaction_callback(capture_web)
    if machine is None:
        return None
    credential_digest = str(machine.get('token_digest') or '')
    if not re.fullmatch('[0-9a-f]{64}', credential_digest):
        raise PermissionError('The original Agent credential is unavailable')
    binding = CredentialBinding(actor, 'AGENT', credential_digest, required_scope=required_scope,
        instance_id=str(machine.get('instance_id') or ''), fencing_token=int(machine.get('fencing_token') or 0))
    if tx is not None:
        recheck(tx, binding)
    else:
        connection.execute_transaction_callback(lambda reader: recheck(reader, binding))
    return binding


def binding_record(binding):
    """Serialize a captured binding for a private immutable business receipt."""
    if not isinstance(binding, CredentialBinding):
        raise TypeError('A captured original credential binding is required')
    return dict(actor_id=binding.actor, credential_kind=binding.kind, credential_digest=binding.credential_digest,
        required_scope=binding.required_scope or None, instance_id=binding.instance_id or None,
        fencing_token=binding.fencing_token, auth_method=binding.auth_method or None,
        permission_version=binding.permission_version, mfa_level=binding.mfa_level or None,
        node_id=binding.node_id or None, session_created_at=binding.created_at or None)


def binding_from_record(record):
    """Load only a trusted database receipt, never an HTTP binding dictionary."""
    record = row(record)
    binding = CredentialBinding(str(record.get('actor_id') or ''), str(record.get('credential_kind') or ''),
        str(record.get('credential_digest') or ''), required_scope=str(record.get('required_scope') or ''),
        instance_id=str(record.get('instance_id') or ''), fencing_token=int(record.get('fencing_token') or 0),
        auth_method=str(record.get('auth_method') or ''), permission_version=int(record.get('permission_version') or 0),
        mfa_level=str(record.get('mfa_level') or ''), node_id=str(record.get('node_id') or ''),
        created_at=str(record.get('session_created_at') or ''))
    if (not binding.actor or not re.fullmatch('[0-9a-f]{64}', binding.credential_digest)
            or binding.kind not in {'WEB', 'AGENT'}):
        raise PermissionError('The original credential receipt is invalid')
    if binding.kind == 'WEB':
        if (not binding.auth_method or binding.permission_version < 1 or not binding.created_at
                or binding.required_scope or binding.instance_id or binding.fencing_token):
            raise PermissionError('The original Web Session receipt is invalid')
    elif (not binding.instance_id or binding.fencing_token < 1 or not binding.required_scope
            or binding.auth_method or binding.permission_version or binding.mfa_level or binding.node_id or binding.created_at):
        raise PermissionError('The original machine credential receipt is invalid')
    return binding


@contextmanager
def dispatch_context(binding, source_kind, source_id, source_attempt_id, *, reauthorize, worker_key,
                     origin_id=None, allow_wait=True, cancelled=None, lock_principals=()):
    if binding is None:
        # A nested business request without its original credential must not
        # borrow a caller's otherwise valid model identity or source binding.
        from .model_dispatch import _context
        token = _context.set(None)
        try:
            yield
        finally:
            _context.reset(token)
        return
    from .model_dispatch import authenticated_context
    def authorize(tx, admission):
        recheck(tx, binding)
        if admission.get('credential_digest') != binding.credential_digest:
            raise PermissionError('The admission credential differs from the original identity')
        reauthorize(tx, admission)
    with authenticated_context(binding.actor, source_kind, source_id, source_attempt_id,
            credential_digest=binding.credential_digest, reauthorize=authorize, worker_key=worker_key,
            origin_id=origin_id, allow_wait=allow_wait, cancelled=cancelled, lock_principals=tuple(lock_principals)):
        yield
