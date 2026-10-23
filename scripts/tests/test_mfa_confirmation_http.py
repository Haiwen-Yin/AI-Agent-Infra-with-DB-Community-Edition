"""Exercise the actual MFA payload and handlers without altering any real factor."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
import pytest


SOURCE = Path(__file__).resolve().parents[1] / "web_app.py"


def app_fixture(*, confirmed=True, promoted=True):
    """Compile the production class/routes; only external services are doubles."""
    tree = ast.parse(SOURCE.read_text())
    names = {"MfaConfirmBody", "mfa_confirm", "user_mfa_confirm"}
    selected = [deepcopy(node) for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                and node.name in names]
    assert len(selected) == len(names)
    app, calls = FastAPI(), []
    session = {"principal_id": "synthetic-human", "session_digest": "synthetic-session", "mfa_level": "SETUP"}
    def confirm(*args):
        calls.append(("confirm", args))
        return confirmed
    def promote(*args):
        calls.append(("promote", args))
        return promoted
    namespace = {"app": app, "BaseModel": BaseModel, "Field": Field,
                 "Dict": Dict, "Any": Any, "Depends": Depends, "HTTPException": HTTPException,
                 "require_csrf": lambda: session,
                 "security_lifecycle": SimpleNamespace(confirm_totp=confirm),
                 "identity_api": SimpleNamespace(set_session_mfa_level=promote),
                 "_identity_http_error": lambda *_: HTTPException(400, "MFA confirmation failed")}
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), str(SOURCE), "exec"), namespace)
    return TestClient(app), session, calls


@pytest.mark.parametrize("route", ["/api/auth/mfa/confirm", "/portal/api/auth/mfa/confirm",
                                   "/api/users/synthetic-human/mfa/confirm"])
@pytest.mark.parametrize("reason", [None, "Confirm my new factor"])
def test_real_payload_reaches_confirmation_with_default_or_explicit_audit_reason(route, reason):
    client, session, calls = app_fixture()
    payload = {"factor_id": "synthetic-factor", "code": "123456"}
    if reason is not None:
        payload["reason"] = reason
    response = client.post(route, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    assert calls[0] == ("confirm", ("synthetic-human", "synthetic-factor", "123456",
                                   reason or "MFA enrollment confirmation"))
    assert calls[1] == ("promote", ("synthetic-session", "STRONG"))
    assert session["mfa_level"] == "STRONG"


@pytest.mark.parametrize("field,value", [("reason", ""), ("reason", "x" * 2001),
                                          ("factor_id", ""), ("code", "123")])
def test_invalid_confirmation_payload_never_reaches_the_service(field, value):
    client, session, calls = app_fixture()
    response = client.post("/api/auth/mfa/confirm", json={"factor_id": "synthetic-factor", "code": "123456", field: value})
    assert response.status_code == 422
    assert not calls and session["mfa_level"] == "SETUP"


def test_rejected_factor_does_not_promote_the_session():
    client, session, calls = app_fixture(confirmed=False)
    response = client.post("/portal/api/auth/mfa/confirm", json={"factor_id": "synthetic-factor", "code": "123456"})
    assert response.status_code == 400
    assert len(calls) == 1 and session["mfa_level"] == "SETUP"


def test_session_promotion_failure_is_not_reported_as_strong_authentication():
    client, session, calls = app_fixture(promoted=False)
    response = client.post("/api/auth/mfa/confirm", json={"factor_id": "synthetic-factor", "code": "123456"})
    assert response.status_code == 503
    assert len(calls) == 2 and session["mfa_level"] == "SETUP"


def test_compatibility_confirmation_cannot_target_another_person():
    client, session, calls = app_fixture()
    response = client.post("/api/users/another-person/mfa/confirm", json={"factor_id": "synthetic-factor", "code": "123456"})
    assert response.status_code == 403
    assert not calls and session["mfa_level"] == "SETUP"


def test_all_local_request_models_declare_every_field_read_by_their_handlers():
    """Catch this class of omission across request bodies, including inheritance."""
    tree = ast.parse(SOURCE.read_text())
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    def fields(name):
        if name == "BaseModel":
            return {"model_dump", "model_fields_set", "dict"}
        node = classes.get(name)
        if node is None:
            return None
        inherited = [fields(base.id) for base in node.bases if isinstance(base, ast.Name)]
        inherited = [value for value in inherited if value is not None]
        if not inherited:
            return None
        own = {item.target.id for item in node.body if isinstance(item, ast.AnnAssign)
               and isinstance(item.target, ast.Name)}
        return own.union(*inherited)
    findings = []
    for function in tree.body:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for argument in function.args.args:
            declared = fields(argument.annotation.id) if isinstance(argument.annotation, ast.Name) else None
            if declared is None:
                continue
            accessed = {node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)
                        and isinstance(node.value, ast.Name) and node.value.id == argument.arg}
            findings.extend(f"{function.name}: {argument.annotation.id}.{name}" for name in accessed - declared)
    assert not findings, findings
