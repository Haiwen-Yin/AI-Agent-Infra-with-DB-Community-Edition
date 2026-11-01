"""Deployment reuse preserves a complete unchanged Embedding configuration.

All persistence and provider operations are local doubles. Explicit Profile
updates retain their revision semantics; deployment is the opt-in caller.
"""
from copy import deepcopy
import json

import pytest

from lib import connection_crypto, deployment_orchestrator, embedding_governance


CONFIG = dict(profile_key="platform-default", provider_url="https://embedding.example/v1",
    model_id="embedding-test", execution_mode="PLATFORM_MANAGED", dimension=1024,
    distance_metric="COSINE", normalize_vectors=False, preprocessing={"trim": True},
    modalities=["TEXT"], secret_reference="vault:embedding/current", reason="Reapply deployment configuration",
    model_fingerprint="sha256:embedding-test")


@pytest.fixture
def persistence(monkeypatch):
    saved = dict(profile_id="EMB_PLATFORM_DEFAULT", profile_key="platform-default", version=7,
        provider_url=CONFIG["provider_url"], model_id=CONFIG["model_id"],
        model_fingerprint=CONFIG["model_fingerprint"], secret_reference=CONFIG["secret_reference"],
        api_key_cipher="", execution_mode=CONFIG["execution_mode"], dimension=1024,
        distance_metric="COSINE", normalize_vectors="N", preprocessing_json='{"trim":true}',
        modalities_json='["TEXT"]', status="ACTIVE", health_state="HEALTHY")

    class Transaction:
        def __init__(self):
            self.saved = saved
            self.writes = []
            self.audits = []

        def query_one(self, sql, params):
            assert "CX_EMBEDDING_PROFILES" in sql and "FOR UPDATE" in sql
            assert params == {"key": "platform-default"}
            return deepcopy(self.saved)

        def execute(self, sql, params):
            self.writes.append((sql, deepcopy(params)))
            return 1

    tx = Transaction()
    monkeypatch.setattr(embedding_governance.connection, "execute_transaction_callback", lambda action: action(tx))
    monkeypatch.setattr(embedding_governance.identity_api, "_audit_tx", lambda *args: tx.audits.append(args))
    monkeypatch.setattr(connection_crypto, "encrypt_section", lambda value: "encrypted-new-key")
    monkeypatch.setattr(connection_crypto, "decrypt_section", lambda value: {"api_key": "current-key"})
    return tx


def apply(config=None, **options):
    return embedding_governance.upsert_profile("deployment-actor", **(CONFIG if config is None else config), **options)


def test_deployment_reapplication_keeps_the_saved_revision_and_cipher(persistence, monkeypatch):
    tx = persistence
    bound = []
    monkeypatch.setattr(embedding_governance, "create_contract", lambda actor, profile, reason:
        bound.append(profile) or {"contract_id": "EC_existing"})
    monkeypatch.setattr(embedding_governance, "create_space", lambda *args, **kwargs: {"space_id": "ES_existing"})
    monkeypatch.setattr(embedding_governance, "bind", lambda *args: None)
    monkeypatch.setattr(embedding_governance, "probe_profile", lambda *args: {"status": "CONFIGURED_ONLY"})
    raw = dict(embedding=dict(api_url=CONFIG["provider_url"], model=CONFIG["model_id"],
        **{name: CONFIG[name] for name in ("profile_key", "execution_mode", "dimension", "distance_metric",
            "normalize_vectors", "preprocessing", "modalities", "secret_reference", "model_fingerprint")}))
    before = deepcopy(tx.saved)
    result = deployment_orchestrator._configure_models(raw, "reapplication-test")
    assert result["embedding"] == "CONFIGURED_ONLY" and bound == ["EMB_PLATFORM_DEFAULT"]
    assert tx.writes == [] and tx.saved == before


def test_explicit_profile_save_still_advances_the_revision(persistence):
    result = apply()
    assert result["version"] == 8 and len(persistence.writes) == 1
    assert persistence.writes[0][1]["profile_version"] == 8


@pytest.mark.parametrize(("field", "value"), [
    ("provider_url", "https://different.example/v1"), ("model_id", "embedding-other"),
    ("model_fingerprint", "sha256:other"), ("execution_mode", "ENTERPRISE_PROXY"),
    ("dimension", 512), ("distance_metric", "DOT_PRODUCT"), ("normalize_vectors", "Y"),
    ("preprocessing_json", '{"trim":false}'), ("modalities_json", '["IMAGE","TEXT"]'),
    ("secret_reference", "vault:embedding/other"), ("status", "RETIRED"),
    ("preprocessing_json", "invalid-json"), ("modalities_json", "invalid-json"),
])
def test_any_configuration_or_credential_source_change_advances_revision(persistence, field, value):
    persistence.saved[field] = value
    result = apply(reuse_unchanged=True)
    assert result["version"] == 8 and len(persistence.writes) == 1


def test_reuse_preserves_native_json_values_without_ignoring_vector_normalization(persistence):
    persistence.saved["preprocessing_json"] = {"trim": True}
    persistence.saved["modalities_json"] = ["TEXT"]
    result = apply(reuse_unchanged=True, expected_version=7)
    assert result["version"] == 7 and result["idempotent"] is True
    assert persistence.writes == [] and "cipher" not in json.dumps(result)


def test_unchanged_reapplication_still_checks_expected_revision(persistence):
    with pytest.raises(embedding_governance.EmbeddingConflict):
        apply(reuse_unchanged=True, expected_version=6)
    assert persistence.writes == []


def test_equal_plaintext_key_reuses_the_existing_encrypted_value(persistence):
    persistence.saved["api_key_cipher"] = "existing-cipher"
    result = apply(dict(CONFIG, api_key="current-key"), reuse_unchanged=True)
    assert result["version"] == 7 and persistence.writes == []
    assert "current-key" not in json.dumps(result) and "existing-cipher" not in json.dumps(result)


def test_equal_non_ascii_key_uses_its_exact_utf8_value(persistence, monkeypatch):
    persistence.saved["api_key_cipher"] = "existing-cipher"
    monkeypatch.setattr(connection_crypto, "decrypt_section", lambda value: {"api_key": "密钥-é"})
    result = apply(dict(CONFIG, api_key="密钥-é"), reuse_unchanged=True)
    assert result["version"] == 7 and persistence.writes == []


def test_equivalent_json_format_does_not_create_a_revision(persistence):
    persistence.saved["preprocessing_json"] = '{ "trim" : true }'
    persistence.saved["modalities_json"] = '[ "TEXT" ]'
    result = apply(reuse_unchanged=True)
    assert result["version"] == 7 and persistence.writes == []


def test_reuse_option_creates_an_absent_profile_normally(persistence):
    persistence.saved = None
    result = apply(reuse_unchanged=True)
    assert result["version"] == 1 and len(persistence.writes) == 1
    assert "INSERT INTO CX_EMBEDDING_PROFILES" in persistence.writes[0][0]


def test_new_plaintext_key_is_a_real_profile_revision(persistence):
    persistence.saved["api_key_cipher"] = "existing-cipher"
    result = apply(dict(CONFIG, api_key="replacement-key"), reuse_unchanged=True)
    assert result["version"] == 8 and len(persistence.writes) == 1
    assert persistence.writes[0][1]["api_cipher"] == "encrypted-new-key"


def test_missing_key_input_retains_the_current_credential_without_decryption(persistence, monkeypatch):
    persistence.saved["api_key_cipher"] = "existing-cipher"
    def forbidden(*args):
        raise AssertionError("An omitted replacement key preserves its existing source")
    monkeypatch.setattr(connection_crypto, "decrypt_section", forbidden)
    result = apply(reuse_unchanged=True)
    assert result["version"] == 7 and persistence.writes == []


def test_unreadable_old_cipher_cannot_establish_equal_replacement_key(persistence, monkeypatch):
    persistence.saved["api_key_cipher"] = "unreadable-cipher"
    def unreadable(*args):
        raise ValueError("synthetic unreadable credential")
    monkeypatch.setattr(connection_crypto, "decrypt_section", unreadable)
    result = apply(dict(CONFIG, api_key="replacement-key"), reuse_unchanged=True)
    assert result["version"] == 8 and len(persistence.writes) == 1


def test_reused_profile_still_requires_atomic_audit(persistence, monkeypatch):
    def audit_failure(*args):
        raise RuntimeError("synthetic audit failure")
    monkeypatch.setattr(embedding_governance.identity_api, "_audit_tx", audit_failure)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        apply(reuse_unchanged=True)
    assert persistence.writes == []


@pytest.mark.parametrize(("native_value", "expected"), [("N", "N"), (False, "N"), ("Y", "Y"), (True, "Y"), (None, "Y")])
def test_created_contract_preserves_the_saved_normalization_setting(persistence, monkeypatch, native_value, expected):
    profile = dict(persistence.saved, normalize_vectors=native_value)
    if native_value is None:
        profile.pop("normalize_vectors")
    writes = []

    class ContractTransaction:
        def query_one(self, sql, params):
            assert "CX_EMBEDDING_CONTRACTS" in sql and params == {"id": profile["profile_id"]}
            return None

        def execute(self, sql, params):
            writes.append((sql, deepcopy(params)))
            return 1

    monkeypatch.setattr(embedding_governance, "_profile_row", lambda profile_id: profile)
    monkeypatch.setattr(embedding_governance.connection, "execute_transaction_callback", lambda action: action(ContractTransaction()))
    result = embedding_governance.create_contract("deployment-actor", profile["profile_id"], "Preserve the actual vector contract")
    assert result["contract_version"] == 1
    assert len(writes) == 1 and writes[0][1]["p_normalize"] == expected


def test_disabled_normalization_cannot_reuse_a_normalized_vector_contract(persistence, monkeypatch):
    profile = deepcopy(persistence.saved)
    normalized_digest = embedding_governance._digest(embedding_governance._contract_payload(dict(profile, normalize_vectors="Y")))
    writes = []

    class ContractTransaction:
        def query_one(self, sql, params):
            return {"contract_id": "EC_normalized", "contract_version": 3, "contract_digest": normalized_digest}

        def execute(self, sql, params):
            writes.append((sql, deepcopy(params)))
            return 1

    monkeypatch.setattr(embedding_governance, "_profile_row", lambda profile_id: profile)
    monkeypatch.setattr(embedding_governance.connection, "execute_transaction_callback", lambda action: action(ContractTransaction()))
    result = embedding_governance.create_contract("deployment-actor", profile["profile_id"], "Select a distinct unnormalized vector contract")
    assert result["contract_version"] == 4 and result["contract_id"] != "EC_normalized"
    assert len(writes) == 1 and writes[0][1]["p_normalize"] == "N"
    assert writes[0][1]["p_digest"] != normalized_digest
