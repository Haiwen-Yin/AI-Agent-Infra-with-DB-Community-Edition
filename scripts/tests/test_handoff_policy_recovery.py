"""Interrupted additive DDL must resume without trusting uncommitted history."""
import ast
from pathlib import Path
import pytest
import migration_runner as runner


@pytest.mark.parametrize('database',['oracle','pg','yashandb'])
@pytest.mark.parametrize('state',['FAILED','RUNNING','APPLIED','ABSENT','CHANGED','PREREQUISITE'])
def test_successor_recovery_is_checksum_bound(monkeypatch,database,state):
    numbers=[number for number in range(85,94) if number!=92 or database=='yashandb']
    scripts=[Path(str(number)+'_predecessor.sql') for number in numbers]+[Path('94_v4_4_15_handoff_policy.sql')]
    closed=[]
    class Probe:
        def cursor(self): return self
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def close(self): closed.append(True)
    monkeypatch.setattr(runner,'_connect_for_preflight',lambda *_:Probe())
    monkeypatch.setattr(runner,'_schema_tables',lambda *_:{'AI_SCHEMA_MIGRATION_STEPS'})
    monkeypatch.setattr(runner,'_checksum',lambda path:path.name)
    def row(_cursor,_database,path, *, version=None):
        if path==scripts[-1]:
            if state=='ABSENT': return None
            return {'status':state if state in {'FAILED','RUNNING','APPLIED'} else 'FAILED',
                    'checksum':'changed' if state=='CHANGED' else path.name}
        return {'status':'FAILED' if state=='PREREQUISITE' else 'APPLIED','checksum':path.name}
    monkeypatch.setattr(runner,'_step_row',row)
    if state in {'CHANGED','PREREQUISITE'}:
        with pytest.raises(ValueError): runner._order_successor_recovery(database,{},scripts)
    else:
        actual=runner._order_successor_recovery(database,{},scripts)
        assert actual==([scripts[-1],*scripts] if state in {'FAILED','RUNNING'} else scripts)
    assert closed==[True]


def _versioned_recovery_fixture(monkeypatch, database):
    numbers = [number for number in range(85, 94)
               if number != 92 or database == 'yashandb']
    scripts = [Path(f'{number}_predecessor.sql') for number in numbers]
    scripts.append(Path('94_v4_4_15_handoff_policy.sql'))
    closed = []

    class Probe:
        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def close(self):
            closed.append(True)

    monkeypatch.setattr(runner, '_connect_for_preflight', lambda *_: Probe())
    monkeypatch.setattr(runner, '_schema_tables', lambda *_: {'AI_SCHEMA_MIGRATION_STEPS'})
    monkeypatch.setattr(runner, '_checksum', lambda path: path.name)
    return scripts, closed


@pytest.mark.parametrize('database', ['oracle', 'pg', 'yashandb'])
@pytest.mark.parametrize('state', ['FAILED', 'RUNNING'])
@pytest.mark.parametrize('explicit', [False, True])
def test_successor_recovery_resolves_selected_version_once(monkeypatch, database, state, explicit):
    scripts, closed = _versioned_recovery_fixture(monkeypatch, database)
    selected_version = '5.0.1'
    monkeypatch.setattr(runner, 'MIGRATION_VERSION', '4.1.0' if explicit else selected_version)
    calls = []

    def row(_cursor, _database, path, *, version=None):
        calls.append((path, version))
        assert version == selected_version
        # A changed process default must not split one recovery across releases.
        monkeypatch.setattr(runner, 'MIGRATION_VERSION', '4.4.15')
        return {'status': state if path == scripts[-1] else 'APPLIED',
                'checksum': path.name}

    monkeypatch.setattr(runner, '_step_row', row)
    kwargs = {'version': selected_version} if explicit else {}
    actual = runner._order_successor_recovery(database, {}, scripts, **kwargs)

    assert actual == [scripts[-1], *scripts]
    assert calls == [(path, selected_version) for path in [scripts[-1], *scripts[:-1]]]
    assert closed == [True]


@pytest.mark.parametrize('database', ['oracle', 'pg', 'yashandb'])
@pytest.mark.parametrize('current', [None, 'APPLIED'])
@pytest.mark.parametrize('historical', ['FAILED', 'RUNNING', 'APPLIED'])
def test_successor_recovery_does_not_read_history_without_current_interruption(
        monkeypatch, database, current, historical):
    scripts, closed = _versioned_recovery_fixture(monkeypatch, database)
    selected_version = '5.0.1'
    monkeypatch.setattr(runner, 'MIGRATION_VERSION', '4.1.0')
    calls = []

    def row(_cursor, _database, path, *, version=None):
        calls.append((path, version))
        state = current if version == selected_version else historical
        return None if state is None else {'status': state, 'checksum': path.name}

    monkeypatch.setattr(runner, '_step_row', row)
    actual = runner._order_successor_recovery(database, {}, scripts, version=selected_version)

    assert actual == scripts
    assert calls == [(scripts[-1], selected_version)]
    assert closed == [True]


@pytest.mark.parametrize('database', ['oracle', 'pg', 'yashandb'])
@pytest.mark.parametrize('state', ['FAILED', 'RUNNING'])
def test_successor_recovery_current_checksum_mismatch_cannot_use_history(monkeypatch, database, state):
    scripts, closed = _versioned_recovery_fixture(monkeypatch, database)
    selected_version = '5.0.1'
    monkeypatch.setattr(runner, 'MIGRATION_VERSION', '4.1.0')
    calls = []

    def row(_cursor, _database, path, *, version=None):
        calls.append((path, version))
        if version == selected_version:
            return {'status': state, 'checksum': 'wrong-current-checksum'}
        return {'status': 'APPLIED', 'checksum': path.name}

    monkeypatch.setattr(runner, '_step_row', row)
    with pytest.raises(ValueError, match='Interrupted policy migration checksum mismatch'):
        runner._order_successor_recovery(database, {}, scripts, version=selected_version)

    assert calls == [(scripts[-1], selected_version)]
    assert closed == [True]


@pytest.mark.parametrize('database', ['oracle', 'pg', 'yashandb'])
@pytest.mark.parametrize('defect', ['MISSING', 'FAILED', 'CHECKSUM'])
def test_successor_recovery_current_predecessor_cannot_use_history(monkeypatch, database, defect):
    scripts, closed = _versioned_recovery_fixture(monkeypatch, database)
    selected_version = '5.0.1'
    broken = scripts[-2]
    monkeypatch.setattr(runner, 'MIGRATION_VERSION', '4.1.0')
    calls = []

    def row(_cursor, _database, path, *, version=None):
        calls.append((path, version))
        if version != selected_version:
            return {'status': 'APPLIED', 'checksum': path.name}
        if path == scripts[-1]:
            return {'status': 'FAILED', 'checksum': path.name}
        if path == broken:
            if defect == 'MISSING':
                return None
            return {'status': 'FAILED' if defect == 'FAILED' else 'APPLIED',
                    'checksum': 'wrong-current-checksum' if defect == 'CHECKSUM' else path.name}
        return {'status': 'APPLIED', 'checksum': path.name}

    monkeypatch.setattr(runner, '_step_row', row)
    with pytest.raises(ValueError, match='Policy recovery requires verified predecessor checksums'):
        runner._order_successor_recovery(database, {}, scripts, version=selected_version)

    assert calls == [(path, selected_version) for path in [scripts[-1], *scripts[:-1]]]
    assert closed == [True]


@pytest.mark.parametrize('database', ['oracle', 'pg', 'yashandb'])
def test_orchestrator_passes_selected_version_to_successor_recovery(monkeypatch, database, tmp_path):
    from lib import deployment_orchestrator as deployment

    selected_version = '5.0.1'
    config_path = tmp_path / 'isolated-config.json'
    config = {'test_target': 'offline-only'}
    deploy = tmp_path / 'deploy'
    names = ['85_predecessor.sql', '94_v4_4_15_handoff_policy.sql']
    scripts = [deploy / name for name in names]
    calls = []
    applied = []
    monkeypatch.setattr(runner, 'MIGRATION_VERSION', '4.1.0')
    monkeypatch.setattr(runner, 'MIGRATION_EDITION', 'community')
    monkeypatch.setattr(deployment, '_package_deploy_dir', lambda *_: deploy)

    def release_script_names(version, selected_database, path, edition):
        assert (version, selected_database, path, edition) == (
            selected_version, database, config_path, 'enterprise')
        return names

    def recovery(selected_database, selected_config, selected_scripts, *, version=None):
        calls.append((selected_database, selected_config, selected_scripts, version))
        return list(reversed(selected_scripts))

    def apply(selected_config, script):
        assert selected_config is config
        applied.append(script)
        return runner.MigrationResult(database=database, passed=True, checksum=script.name,
                                      ledger_status='applied')

    monkeypatch.setattr(runner, 'release_script_names', release_script_names)
    monkeypatch.setattr(runner, '_order_successor_recovery', recovery)
    monkeypatch.setattr(runner, f'_apply_{database}', apply)

    results = deployment._migration_apply(selected_version, database, 'ENTERPRISE',
                                          config_path, config, tmp_path)

    assert calls == [(database, config, scripts, selected_version)]
    assert applied == list(reversed(scripts))
    assert [result['script'] for result in results] == list(reversed(names))
    assert all(result['passed'] for result in results)


def test_main_explicitly_passes_cli_version_to_successor_recovery():
    tree = ast.parse(Path(runner.__file__).read_text(encoding='utf-8'))
    main = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == 'main')
    calls = [node for node in ast.walk(main)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == '_order_successor_recovery']
    assert len(calls) == 1
    keyword = next(item for item in calls[0].keywords if item.arg == 'version')
    assert isinstance(keyword.value, ast.Attribute)
    assert isinstance(keyword.value.value, ast.Name)
    assert keyword.value.value.id == 'args'
    assert keyword.value.attr == 'version'
