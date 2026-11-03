"""An enabled trigger is insufficient when its native compiler status is invalid."""
import pytest

from lib import knowledge_native_governance as governance


@pytest.mark.parametrize('database',['oracle','yashandb'])
@pytest.mark.parametrize('compiled',['VALID','INVALID',None])
def test_native_guard_checks_compilation_as_well_as_enablement(database,compiled):
    guards=governance.render(database,legacy_shared=True)[2]['guards']
    by_name={guard['trigger']:guard for guard in guards}
    class Cursor:
        def execute(self,sql,params=None):
            if sql=='SELECT USER FROM DUAL':self.row=('AIADMIN',)
            elif 'FROM USER_TRIGGERS' in sql:
                guard=by_name[params['trigger_name']]
                body=governance._legacy_shared_body(database,guard['table'],
                    governance._native_body(database,guard['table'],'AIADMIN'))
                self.row=(body,'ENABLED','BEFORE EACH ROW','INSERT OR DELETE OR UPDATE')
            elif 'FROM USER_OBJECTS' in sql:
                self.row=None if compiled is None else (compiled,)
            else:pytest.fail('Unexpected metadata query')
        def fetchone(self):return self.row
    failures=governance.errors(Cursor(),database,legacy_shared=True)
    assert failures==([] if compiled=='VALID' else [guard['trigger']+':EXECUTABLE_GUARD' for guard in guards])
