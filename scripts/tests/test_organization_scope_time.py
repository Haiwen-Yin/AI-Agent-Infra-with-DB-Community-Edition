"""Organization scope never anticipates a future membership/reporting fact."""
import sqlite3

import pytest

from lib import organization_api


@pytest.mark.parametrize('scope',['OWNED','ASSIGNED','ORG_SUBTREE','DIRECT_REPORTS'])
def test_organization_scope_uses_current_membership_and_reporting(scope,monkeypatch):
    monkeypatch.setattr(organization_api,'_access',lambda *args:dict(scopes=[scope]))
    db=sqlite3.connect(':memory:')
    db.executescript('''
        CREATE TABLE CX_ORGANIZATIONS(ORGANIZATION_ID TEXT);
        CREATE TABLE CX_ORGANIZATION_MEMBERS(ORGANIZATION_ID TEXT,PRINCIPAL_ID TEXT,
            MEMBERSHIP_KIND TEXT,STATUS TEXT,VALID_FROM TEXT,VALID_UNTIL TEXT);
        CREATE TABLE CX_ORGANIZATION_CLOSURE(ANCESTOR_ID TEXT,DESCENDANT_ID TEXT);
        CREATE TABLE CX_REPORTING_RELATIONSHIPS(PRINCIPAL_ID TEXT,MANAGER_PRINCIPAL_ID TEXT,
            RELATIONSHIP_TYPE TEXT,STATUS TEXT,VALID_FROM TEXT,VALID_UNTIL TEXT);
        INSERT INTO CX_ORGANIZATIONS VALUES('org');
        INSERT INTO CX_ORGANIZATION_CLOSURE VALUES('org','org');
        INSERT INTO CX_ORGANIZATION_MEMBERS VALUES('org','actor','PRIMARY','ACTIVE','2000-01-01',NULL);
        INSERT INTO CX_REPORTING_RELATIONSHIPS VALUES('actor','actor','DIRECT','ACTIVE','2000-01-01',NULL);
    ''')
    try:
        clause,params=organization_api._scope_clause('actor')
        visible=lambda:db.execute('SELECT o.ORGANIZATION_ID FROM CX_ORGANIZATIONS o WHERE '+clause,params).fetchall()
        assert visible()==[('org',)]
        db.execute("UPDATE CX_ORGANIZATION_MEMBERS SET VALID_FROM='2999-01-01'")
        assert visible()==[]
        db.execute("UPDATE CX_ORGANIZATION_MEMBERS SET VALID_FROM='2000-01-01',VALID_UNTIL='2001-01-01'")
        assert visible()==[]
        db.execute('UPDATE CX_ORGANIZATION_MEMBERS SET VALID_UNTIL=NULL')
        assert visible()==[('org',)]
        if scope=='DIRECT_REPORTS':
            db.execute("UPDATE CX_REPORTING_RELATIONSHIPS SET VALID_FROM='2999-01-01'")
            assert visible()==[]
    finally:
        db.close()
