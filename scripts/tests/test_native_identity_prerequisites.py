"""Offline bounded administrator-script and version-bound preflight contracts."""
from pathlib import Path

import pytest

from lib import deployment_orchestrator as deployment
from lib.package_layout import databases, deployment_dir

ROOT = Path(__file__).resolve().parents[2]
BACKENDS = tuple(name for name in databases(ROOT) if name in {'oracle', 'yashandb'})


@pytest.mark.parametrize('backend', BACKENDS)
def test_new_administrator_prerequisite_is_exact_readonly_and_not_an_owner_action(backend):
    path = deployment_dir(ROOT, backend) / f'0_{backend}_v5_0_1_native_identity_prerequisites.sql'
    sql = path.read_text()
    executable = '\n'.join(line for line in sql.upper().splitlines() if not line.lstrip().startswith('--'))
    assert "DEFINE TARGET_PDB = 'REPLACE_WITH_APPLICATION_PDB'" in executable
    assert "SYS_CONTEXT('USERENV','SESSION_USER') <> 'SYS'" in executable
    assert "UPPER(V_PDB) <> UPPER('&&TARGET_PDB')" in executable
    assert "('CDB$ROOT','PDB$SEED')" in executable
    assert "CREATE VIEW SYS.CX_AGENT_ACCOUNT_STATUS AS " in executable
    catalog = 'DBA_END_USERS' if backend == 'oracle' else 'DBA_USERS'
    assert f'SELECT USERNAME, ACCOUNT_STATUS FROM SYS.{catalog} WITH READ ONLY' in executable
    assert 'SELECT TEXT, READ_ONLY' in executable
    assert "V_DEFINITION IS NULL OR V_READ_ONLY IS NULL" in executable
    assert 'V_COLUMNS <> 2 OR V_EXPECTED_COLUMNS <> 2' in executable
    assert "SUM(CASE WHEN COLUMN_NAME IN ('USERNAME','ACCOUNT_STATUS')" in executable
    assert 'COLUMN_ID=' not in executable  # Oracle uses 1-based, YashanDB 0-based.
    assert "GRANTEE<>V_OWNER OR PRIVILEGE<>'SELECT' OR GRANTABLE NOT IN ('N','NO')" in executable
    assert 'GRANT SELECT ON SYS.CX_AGENT_ACCOUNT_STATUS TO "' in executable
    assert not any(token in executable for token in ('CREATE OR REPLACE', 'CONTAINER=ALL',
        'WITH GRANT OPTION', 'TO PUBLIC', 'TO DEEP_SEC_SESSION_ROLE', 'SELECT *',
        'GRANT DBA ', 'SELECT ANY DICTIONARY', 'GRANT SELECT ON SYS.DBA_',
        'ALTER USER ', 'ALTER END USER ', 'DROP ', 'REVOKE '))
    # The normal Owner deployment must never run administrator prerequisites.
    source = Path(deployment.__file__).read_text()
    manifest = source.split('def manifest(', 1)[1].split('\ndef ', 1)[0]
    assert 'native_identity_prerequisites.sql' not in manifest


class ProjectionCursor:
    def __init__(self, columns=('USERNAME', 'ACCOUNT_STATUS'), readonly='Y', denied=False):
        self.columns, self.readonly, self.denied = columns, readonly, denied
        self.statements = []
        self.current = ''

    def execute(self, statement, params=None):
        assert statement.startswith('SELECT ')
        self.statements.append((statement, params))
        self.current = statement
        if self.denied:
            raise RuntimeError('ORA-00942 synthetic-password-never-output')

    def fetchall(self):
        return [(item,) for item in self.columns] if 'ALL_TAB_COLUMNS' in self.current else []

    def fetchone(self):
        return (self.readonly,) if self.readonly is not None else None


@pytest.mark.parametrize('backend', ('oracle', 'yashandb'))
@pytest.mark.parametrize('version', ('5.0.1', '5.1.0'))
def test_preflight_binds_exact_release_root_and_queries_only_the_sys_projection(monkeypatch, tmp_path, backend, version):
    observed = []
    monkeypatch.setattr(deployment, 'release_version', lambda db, root, requested: (
        observed.append((db, root, requested)) or version))
    monkeypatch.setattr(deployment, '_package_deploy_dir', lambda db, root: root / 'scripts/deploy' / db)
    cursor = ProjectionCursor()
    result = deployment._native_identity_status_preflight(cursor, backend, root=tmp_path, target_version=version)
    assert observed == [(backend, tmp_path, version)]
    assert result['code'] == 'NATIVE_IDENTITY_STATUS_VIEW' and result['state'] == 'PASS'
    assert f'scripts/deploy/{backend}/0_{backend}_v5_0_1_native_identity_prerequisites.sql' in result['remediation']
    assert cursor.statements[-1][0] == 'SELECT USERNAME,ACCOUNT_STATUS FROM SYS.CX_AGENT_ACCOUNT_STATUS WHERE 1=0'
    assert all('DBA_USERS' not in text and 'DBA_END_USERS' not in text for text, _ in cursor.statements)


@pytest.mark.parametrize('backend', ('oracle', 'yashandb'))
@pytest.mark.parametrize('case', ('absent', 'extra_column', 'reordered', 'not_readonly', 'null_readonly', 'denied'))
def test_preflight_fails_closed_for_missing_inexact_or_unreadable_projection(monkeypatch, tmp_path, backend, case):
    monkeypatch.setattr(deployment, 'release_version', lambda *_: '5.0.1')
    monkeypatch.setattr(deployment, '_package_deploy_dir', lambda db, root: root / 'scripts/deploy')
    cursor = ProjectionCursor()
    if case == 'absent':
        cursor.columns = ()
    elif case == 'extra_column':
        cursor.columns += ('PASSWORD',)
    elif case == 'reordered':
        cursor.columns = tuple(reversed(cursor.columns))
    elif case == 'not_readonly':
        cursor.readonly = 'N'
    elif case == 'null_readonly':
        cursor.readonly = None
    else:
        cursor.denied = True
    result = deployment._native_identity_status_preflight(cursor, backend, root=tmp_path, target_version='5.0.1')
    assert result['state'] == 'BLOCKED'
    assert 'synthetic-password' not in str(result)


@pytest.mark.parametrize('backend,version', (('pg', '5.0.1'), ('oracle', ''), ('yashandb', ''),
    ('oracle', '5.0.0'), ('yashandb', '4.5.2')))
def test_historical_release_and_pg_do_not_acquire_new_admin_prerequisite(monkeypatch, tmp_path, backend, version):
    monkeypatch.setattr(deployment, 'release_version', lambda *_: version)
    cursor = ProjectionCursor(denied=True)
    assert deployment._native_identity_status_preflight(cursor, backend, root=tmp_path, target_version=version) is None
    assert cursor.statements == []


def test_preflight_refuses_a_requested_version_unbound_to_the_selected_package(monkeypatch, tmp_path):
    def mismatch(*args):
        raise deployment.DeploymentError('requested version does not match the packaged deployment baseline')
    monkeypatch.setattr(deployment, 'release_version', mismatch)
    cursor = ProjectionCursor()
    with pytest.raises(deployment.DeploymentError, match='does not match'):
        deployment._native_identity_status_preflight(cursor, 'oracle', root=tmp_path, target_version='5.0.1')
    assert not cursor.statements


def test_normal_deployment_forwards_the_exact_root_and_target_version():
    source = Path(deployment.__file__).read_text()
    assert 'root=root, target_version=target_version' in source.split('if mode in {"STATUS", "VERIFY"}:', 1)[1].split('resuming =', 1)[0]
    assert 'root=root, target_version=target_version' in source.split('first = preflight(', 1)[1].split('if not first', 1)[0]
