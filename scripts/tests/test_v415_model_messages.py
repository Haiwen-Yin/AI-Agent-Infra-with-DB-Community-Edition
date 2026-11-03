"""Provider compatibility must preserve instruction order and role boundaries."""
import json
import hashlib
import pytest
from lib import native_runtime


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize('budgeted',[False,True])
def test_provider_receives_one_leading_system_message(monkeypatch, stream,budgeted):
    from lib import model_dispatch, model_coordinator_origin
    monkeypatch.setattr(model_dispatch,'_lookup',lambda _:None)
    monkeypatch.setattr(model_coordinator_origin, "selected_route", lambda profile: None)
    messages = [{"role": "system", "content": "Rules"},
                {"role": "system", "content": "Quoted reference data"},
                {"role": "user", "content": "Question"}]
    sent = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, *_):
            return json.dumps({"model": "demo", "choices": [{"message": {"content": "42"}, "finish_reason": "stop"}]}).encode()
        def __iter__(self):
            yield b'data: {"model":"demo","choices":[{"delta":{"content":"42"}}]}\n'
            yield b'data: {"model":"demo","choices":[{"delta":{},"finish_reason":"stop"}]}\n'
            yield b'data: [DONE]\n'

    def open_request(request, **_):
        sent.append((json.loads(request.data),request.data))
        return Response()

    monkeypatch.setattr(native_runtime.urllib.request, "urlopen", open_request)
    profile = {"provider_url": "http://example.test/v1", "model_id": "demo"}
    from lib import answer_context
    selection=dict(policy_revision='whole-reference-v1',stage='PREPARED_ANSWER_MESSAGES',
        budget=dict(token_budget=32768,byte_budget=131072,output_reserve=4096)) if budgeted else None
    with answer_context.dispatch_budget(selection):
        result = native_runtime._stream_llm(profile, messages, lambda _: None) if stream else native_runtime._call_llm(profile, messages)
    assert result["content"] == "42"
    assert sent[0][0]["messages"] == [{"role": "system", "content": "Rules\n\nQuoted reference data"}, messages[2]]
    assert len(messages) == 3 and messages[0]["content"] == "Rules"
    if budgeted:
        assert sent[0][0]['max_tokens']==4096
        receipt=result['provider_input_budget']
        assert receipt['input_digest']==hashlib.sha256(sent[0][1]).hexdigest()
        assert receipt['input_bytes']==len(sent[0][1])
        assert receipt['stage']=='FINAL_PROVIDER_JSON'
    else:
        assert 'max_tokens' not in sent[0][0] and 'provider_input_budget' not in result


def test_conversation_messages_are_never_promoted_or_reordered():
    messages = [{"role": "user", "content": "untrusted"}, {"role": "system", "content": "later"}]
    assert native_runtime._provider_messages(messages) == messages
