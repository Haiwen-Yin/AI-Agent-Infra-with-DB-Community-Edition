"""Portable HTTP session for an already registered external Agent (stdlib only).

No registration, automatic grants, scope probes, or replay of business writes.
Import from a Windows/Linux client, supply its protected credential in memory,
and call maintain() between turns and at most every 30 seconds in long tasks.
"""
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class SessionError(RuntimeError):
    def __init__(self, code, message, *, status=0, recovery_action="", correlation_id=""):
        super().__init__(message)
        self.code, self.status = code, status
        self.recovery_action, self.correlation_id = recovery_action, correlation_id


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class AgentSession:
    def __init__(self, origin, agent_id, client_secret, *, instance_id="",
                 security_domain_id="", channel_id="", transport=None, clock=time.monotonic):
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or
                parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError("Use the trusted platform HTTP(S) origin")
        self.origin, self.agent_id, self._secret = origin.rstrip("/"), agent_id, client_secret
        self.instance_id, self.domain, self.channel = instance_id, security_domain_id, channel_id
        self._transport, self._clock = transport or self._http, clock
        self._token, self.scopes = "", []
        self._token_deadline = self._lease_deadline = self._maintenance_due = 0

    def _http(self, method, path, body, token):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept":"application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(self.origin + path, data=data, headers=headers, method=method)
        try:
            with build_opener(_NoRedirect).open(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                error = json.loads(exc.read())
            except (ValueError, UnicodeError):
                error = {"code":"HTTP_ERROR", "message":"Gateway request rejected"}
            return exc.code, error
        except Exception:
            # A timeout may follow an instance/token commit. Never resend it here.
            raise SessionError("TRANSPORT_OUTCOME_UNKNOWN", "Gateway result is unknown; reconcile before retry") from None

    def _call(self, method, path, body=None, *, token=""):
        status, result = self._transport(method, path, body, token)
        if status != 200:
            raise SessionError(str(result.get("code") or "HTTP_" + str(status)),
                str(result.get("message") or "Gateway request rejected"), status=status,
                recovery_action=str(result.get("recovery_action") or ""),
                correlation_id=str(result.get("correlation_id") or ""))
        return result

    def token(self, scopes, *, new_instance=False):
        requested = sorted(set(scopes))
        if not requested:
            raise ValueError("Request explicit scopes")
        reuse = bool(self.instance_id) and not new_instance
        body = {"agent_id":self.agent_id, "client_secret":self._secret, "scopes":requested}
        if reuse:
            body["instance_id"] = self.instance_id
        else:
            if not (self.domain or self.channel):
                raise SessionError("DOMAIN_REQUIRED", "New instance requires an authorized Domain or Channel")
            if self.domain:
                body["security_domain_id"] = self.domain
            if self.channel:
                body["channel_id"] = self.channel
        sent = self._clock()
        try:
            result = self._call("POST", "/api/gateway/token", body)
        except SessionError as exc:
            if reuse and exc.code == "INSTANCE_LEASE_EXPIRED":
                # One bounded retry, only for this definite pre-issuance rejection.
                return self.token(requested, new_instance=True)
            raise
        if result.get("agent_id") != self.agent_id or (reuse and result.get("instance_id") != self.instance_id):
            raise SessionError("IDENTITY_MISMATCH", "Token response identity mismatch")
        instance, token = result.get("instance_id"), result.get("access_token")
        if not instance or not token or sorted(result.get("scopes", [])) != requested:
            raise SessionError("INVALID_RESPONSE", "Token response is incomplete")
        ttl, lease = int(result["expires_in"]), int(result["lease_expires_in"])
        if ttl <= 0 or lease < 0:
            raise SessionError("INVALID_RESPONSE", "Token lifetime is invalid")
        # Publish new state only after a complete successful response.
        self.instance_id, self._token, self.scopes = instance, token, requested
        self._token_deadline, self._lease_deadline = sent + ttl, sent + lease
        self._maintenance_due = sent + max(0, min(ttl, lease) / 3)
        return {k:v for k,v in result.items() if k != "access_token"}

    def heartbeat(self):
        sent = self._clock()
        result = self._call("POST", "/api/gateway/heartbeat", {}, token=self._token)
        if not result.get("success") or result.get("instance_id") != self.instance_id:
            raise SessionError("INVALID_RESPONSE", "Heartbeat did not renew the expected instance")
        self._lease_deadline = sent + int(result["lease_expires_in"])
        self._maintenance_due = min(self._token_deadline, self._lease_deadline) - 30
        return result

    def maintain(self):
        if self._clock() < self._maintenance_due:
            return
        if not self.scopes:
            raise SessionError("TOKEN_REQUIRED", "Request an explicitly scoped token first")
        # A live token+lease can renew first. Expired leases recover through the
        # credential exchange; /instances and /heartbeat require a live Bearer.
        if self._clock() + 5 < min(self._token_deadline, self._lease_deadline):
            self.heartbeat()
        self.token(self.scopes)

    def read(self, path):
        parsed = urlsplit(path)
        if not path.startswith("/api/") or parsed.scheme or parsed.netloc or parsed.fragment:
            raise ValueError("Use a platform API path")
        self.maintain()
        return self._call("GET", path, token=self._token)
