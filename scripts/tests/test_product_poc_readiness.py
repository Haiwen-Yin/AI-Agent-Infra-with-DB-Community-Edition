"""A selected-backend POC must not require absent or unsupported adapters."""
import pytest
import poc_readiness


def test_single_target_readiness_does_not_probe_other_databases(monkeypatch, tmp_path):
    calls = []
    def probe(database, config, enterprise):
        calls.append((database, config, enterprise))
        return {"database": database, "ready": True}
    monkeypatch.setattr(poc_readiness, "check_target", probe)
    config = tmp_path / "private.json"
    report = poc_readiness.build_report({"pg": config}, enterprise=False, version="5.0.0", databases=("pg",))
    assert report["passed"] and calls == [("pg", config, False)]
    assert len(report["results"]) == 1


@pytest.mark.parametrize("selected", [(), ("mysql",), ("pg", "pg")])
def test_invalid_readiness_selection_fails_before_driver_or_connection(monkeypatch, selected):
    monkeypatch.setattr(poc_readiness, "check_target", lambda *_: pytest.fail("must not probe an invalid selection"))
    with pytest.raises(ValueError, match="distinct"):
        poc_readiness.build_report({}, databases=selected)
