"""Historical successor proof is nearest-row, version-bound and fail-closed."""
from pathlib import Path

import pytest

import migration_runner as runner
from lib import continuity_schema_validation
from lib.package_layout import active_database, deployment_dir


CHAIN = ('4.4.15', '4.4.16', '4.5.0', '4.5.1', '4.5.2', '5.0.0', '5.0.1')
HISTORICAL_CASES = [(release, previous) for index, release in enumerate(CHAIN)
                    for previous in CHAIN[:index]]


def deploy_path(database):
    root = Path(__file__).resolve().parents[2]
    selected = database if (root / 'adapters').is_dir() else active_database(root)
    return deployment_dir(root, selected)


@pytest.mark.parametrize('database', ['oracle', 'pg', 'yashandb'])
@pytest.mark.parametrize('release,historical', HISTORICAL_CASES)
@pytest.mark.parametrize('implicit', [False, True])
def test_retired_key_accepts_exact_applied_evidence_from_each_trusted_predecessor(
        monkeypatch, database, release, historical, implicit):
    script = deploy_path(database) / '86_v4_4_15_continuity_entities.sql'
    successor = script.with_name('94_v4_4_15_handoff_policy.sql')
    calls = []

    def row(_cursor, actual_database, actual_script, *, version=None):
        assert actual_database == database and actual_script == successor
        calls.append(version)
        if version == historical:
            return {'status': 'APPLIED', 'checksum': runner._checksum(successor)}
        return None

    def validate(_cursor, actual_database, facts):
        assert actual_database == database
        assert ['U', ['ACTIVE_WORK_ID'], '', []] not in facts['CX_HANDOFFS']['keys']
        return []

    monkeypatch.setattr(runner, '_step_row', row)
    monkeypatch.setattr(runner, 'MIGRATION_VERSION', release if implicit else '4.1.0')
    monkeypatch.setattr(continuity_schema_validation, 'errors', validate)
    kwargs = {} if implicit else {'version': release}
    assert runner._step_objects_complete(None, database, script, **kwargs)
    expected = list(reversed(CHAIN[:CHAIN.index(release) + 1]))
    assert calls == expected[:expected.index(historical) + 1]


@pytest.mark.parametrize('database', ['oracle', 'pg', 'yashandb'])
@pytest.mark.parametrize('nearest', ['5.0.1', '5.0.0', '4.5.2', '4.5.1', '4.5.0', '4.4.16'])
@pytest.mark.parametrize('state', ['FAILED', 'RUNNING', 'PENDING', 'TAMPERED'])
def test_nearest_present_invalid_row_never_falls_back_to_older_applied(
        monkeypatch, database, nearest, state):
    successor = deploy_path(database) / '94_v4_4_15_handoff_policy.sql'
    calls = []

    def row(_cursor, _database, _script, *, version=None):
        calls.append(version)
        if version == nearest:
            return {'status': 'APPLIED' if state == 'TAMPERED' else state,
                    'checksum': 'wrong' if state == 'TAMPERED' else runner._checksum(successor)}
        if version == '4.4.15':
            pytest.fail('Older APPLIED evidence must not override a present invalid row')
        return None

    monkeypatch.setattr(runner, '_step_row', row)
    assert not runner._handoff_policy_applied(None, database, successor, version='5.0.1')
    expected = list(reversed(CHAIN))
    assert calls == expected[:expected.index(nearest) + 1]


@pytest.mark.parametrize('release', ['4.4.14', '5.0.2', '99.0.0', ''])
def test_unrecognized_release_has_no_inferred_historical_trust(monkeypatch, release):
    calls = []

    def row(_cursor, _database, _script, *, version=None):
        calls.append(version)
        return None

    monkeypatch.setattr(runner, '_step_row', row)
    assert not runner._handoff_policy_applied(None, 'pg', Path('94.sql'), version=release)
    assert calls == [release]


def test_older_release_never_uses_newer_applied_evidence(monkeypatch):
    calls = []

    def row(_cursor, _database, _script, *, version=None):
        calls.append(version)
        assert version not in {'5.0.0', '5.0.1'}
        return None

    monkeypatch.setattr(runner, '_step_row', row)
    assert not runner._handoff_policy_applied(None, 'pg', Path('94.sql'), version='4.5.2')
    assert calls == ['4.5.2', '4.5.1', '4.5.0', '4.4.16', '4.4.15']


@pytest.mark.parametrize('state', ['FAILED', 'RUNNING', 'TAMPERED'])
def test_invalid_current_successor_keeps_original_retired_key_contract(monkeypatch, state):
    script = deploy_path('pg') / '86_v4_4_15_continuity_entities.sql'
    calls = []

    def row(_cursor, _database, actual_script, *, version=None):
        calls.append(version)
        assert version == '5.0.1'
        return {'status': 'APPLIED' if state == 'TAMPERED' else state,
                'checksum': 'wrong' if state == 'TAMPERED' else runner._checksum(actual_script)}

    def validate(_cursor, _database, facts):
        assert ['U', ['ACTIVE_WORK_ID'], '', []] in facts['CX_HANDOFFS']['keys']
        return ['CX_HANDOFFS:KEYS']

    monkeypatch.setattr(runner, '_step_row', row)
    monkeypatch.setattr(continuity_schema_validation, 'errors', validate)
    assert not runner._step_objects_complete(None, 'pg', script, version='5.0.1')
    assert calls == ['5.0.1']
