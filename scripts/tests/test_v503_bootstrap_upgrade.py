"""The packaged upgrade must preserve predecessor and resume boundaries."""
from pathlib import Path
from types import SimpleNamespace
import runpy
import sys

import pytest

import migration_runner as runner
from lib import deployment_orchestrator as deployment
from product_delivery import acceptance_targets


@pytest.mark.parametrize('target', acceptance_targets(), ids=lambda row: row['key'])
@pytest.mark.parametrize('predecessor_ok', (True, False))
def test_declared_bootstrap_checks_predecessor_before_any_additive_ddl(monkeypatch, tmp_path, target, predecessor_ok):
    database = target['database']
    names = runner.v503_runtime_migration_scripts(database)
    deploy = tmp_path / 'scripts/deploy'
    deploy.mkdir(parents=True)
    events = []

    class Probe:
        def close(self):
            events.append('closed')

    def preflight(_probe, selected_database, scripts):
        assert selected_database == database
        assert [path.name for path in scripts] == list(names)
        assert runner.MIGRATION_VERSION == '5.0.3'
        assert runner.MIGRATION_FROM_VERSION == '5.0.2'
        events.append('predecessor')
        return dict(passed=predecessor_ok, error_type='PredecessorEvidenceIncomplete')

    def apply(_config, script):
        assert events[:2] == ['predecessor', 'closed']
        events.append(script.name)
        return SimpleNamespace(passed=True, ledger_status='APPLIED', checksum='digest', error_type='')

    monkeypatch.setattr(deployment, '_connect', lambda *_: Probe())
    monkeypatch.setattr(runner, '_preflight', preflight)
    monkeypatch.setattr(runner, '_order_successor_recovery', lambda _db, _cfg, paths, **_kw: paths)
    monkeypatch.setattr(runner, '_apply_' + database, apply)
    # The process-global runner selection is restored after each test.
    for key in ('MIGRATION_VERSION', 'MIGRATION_EDITION', 'MIGRATION_FROM_VERSION'):
        monkeypatch.setattr(runner, key, getattr(runner, key))
    if predecessor_ok:
        results = deployment._migration_apply('5.0.3', database, target['edition'].lower(),
            tmp_path / 'config.json', {}, tmp_path, from_version='5.0.2')
        assert [result['script'] for result in results] == list(names)
        assert events[2:] == list(names)
    else:
        with pytest.raises(deployment.DeploymentError, match='PredecessorEvidenceIncomplete'):
            deployment._migration_apply('5.0.3', database, target['edition'].lower(),
                tmp_path / 'config.json', {}, tmp_path, from_version='5.0.2')
        assert events == ['predecessor', 'closed']


@pytest.mark.parametrize('mode,version', [('INITIALIZE', '5.0.3'), ('VERIFY', '5.0.3'), ('UPGRADE', '5.0.2')])
def test_invalid_declared_transition_stops_before_config_activation(monkeypatch, mode, version, tmp_path):
    monkeypatch.setattr(deployment, 'release_baseline', lambda *_: {})
    monkeypatch.setattr(deployment, 'release_version', lambda *_: version)
    monkeypatch.setattr(deployment, '_read_config', lambda *_: pytest.fail('Invalid upgrade read credentials'))
    with pytest.raises(deployment.DeploymentError, match='supported v5.0.2'):
        deployment.run(mode, database='pg', edition='community', root=tmp_path,
                       config_path=tmp_path / 'config.json', from_version='5.0.2')


def test_packaged_cli_forwards_explicit_predecessor(monkeypatch):
    calls = []
    monkeypatch.setattr(deployment, 'run', lambda *args, **kwargs: calls.append((args, kwargs)) or {'status': 'VERIFIED'})
    monkeypatch.setattr(sys, 'argv', ['bootstrap_deployment_agent.py', 'upgrade', '--database', 'pg',
        '--edition', 'community', '--version', '5.0.3', '--from-version', '5.0.2', '--confirm-database-backup'])
    entry = Path(__file__).resolve().parents[1] / 'scripts/bootstrap_deployment_agent.py'
    if not entry.is_file():
        entry = Path(__file__).resolve().parents[1] / 'bootstrap_deployment_agent.py'
    namespace = runpy.run_path(str(entry))
    assert namespace['main']() == 0
    assert len(calls) == 1 and calls[0][1]['from_version'] == '5.0.2'
    assert calls[0][1]['database_backup_confirmed'] is True
