"""An omitted UI context must be absent, never an invalid numeric identifier."""
import pytest
from lib import branch_api


@pytest.mark.parametrize('context,expected', [('',None),('   ',None),(None,None),('123','123'),('0','0')])
@pytest.mark.parametrize('native_id',[456,'456'])
def test_optional_fork_context_is_normalized_without_discarding_nonempty_ids(monkeypatch,context,expected,native_id):
    writes=[]
    monkeypatch.setattr(branch_api,'DATABASE_DIALECT','postgresql')
    monkeypatch.setattr(branch_api,'execute_insert_returning_id',lambda sql,params: writes.append(params) or native_id)
    assert branch_api.fork_branch('123',context,'owned branch','EXPLORATION','owned-agent')=='456'
    assert writes[0]['vfcid']==expected


def test_loop_permission_denial_is_forbidden_without_a_success_receipt(monkeypatch):
    from visualization import server
    handler=server.VisHandler.__new__(server.VisHandler)
    monkeypatch.setattr(handler,'_read_body',lambda: b'{"loop_id":"owned-loop"}')
    monkeypatch.setattr(handler,'_authenticated_principal',lambda: {'actor_id':'owner'})
    responses=[]
    monkeypatch.setattr(handler,'_send_error',lambda status,message: responses.append((status,message)))
    monkeypatch.setattr(handler,'_send_json',lambda *_: pytest.fail('Denied Loop returned success'))
    def deny(*_args,**_kwargs):
        raise PermissionError('Private execution detail must not be returned')
    monkeypatch.setattr(server.loop_api,'start_run_for_actor',deny)
    handler._handle_loop_run_start()
    assert responses==[(403,'Loop execution access denied')]
