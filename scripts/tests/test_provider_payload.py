"""Final fields and exact sent-byte receipts, with no real inference requests."""
import hashlib
import json

import pytest

from lib import provider_payload, native_runtime, content_security


@pytest.mark.parametrize('field', ['tools', 'response_format', 'provider_extra', 'message_extra'])
def test_credential_in_final_noncontent_field_is_denied_before_dispatch(monkeypatch, field):
    from lib import provider_capability_probes, model_dispatch
    def parameters(profile, value):
        secret='sk-'+'a'*40
        if field=='message_extra': value['messages'][0]['name']=secret
        else: value[field]={'description':secret}
        return value
    monkeypatch.setattr(provider_capability_probes, 'apply_parameters', parameters)
    monkeypatch.setattr(model_dispatch, 'dispatch', lambda *a, **kw: pytest.fail('Denied final fields must not reserve/send'))
    with pytest.raises(content_security.ContentDenied) as caught:
        native_runtime._call_llm(dict(provider_url='https://example.test/v1', model_id='fixture'),
            [dict(role='user', content='Safe fixture question')])
    assert caught.value.model_not_dispatched


def test_final_request_bytes_and_all_fields_are_bound_to_receipt():
    value=dict(model='fixture', messages=[dict(role='user', content='中文内容')], stream=False,
        tools=[dict(type='function', function=dict(name='lookup', parameters={'type':'object'}))])
    payload, raw, budget, receipt = provider_payload.prepare(value)
    assert json.loads(raw)==payload==value and budget is None
    assert receipt['request_sha256']==hashlib.sha256(raw).hexdigest()
    assert receipt['byte_count']==len(raw) and '中文内容' not in str(receipt)
    assert receipt['stage']=='FINAL_SERIALIZED_PROVIDER_JSON'


def test_managed_image_is_bounded_without_claiming_pixel_inspection():
    value=dict(model='fixture', messages=[dict(role='user', content=[
        dict(type='text',text='Describe the managed fixture image'),
        dict(type='image_url',image_url=dict(url='data:image/png;base64,'+'A'*300000))])])
    _, raw, _, receipt=provider_payload.prepare(value,managed_images=True)
    assert receipt['byte_count']==len(raw) and not receipt['managed_image_pixels_inspected']
    value['messages'][0]['content'][0]['text']='-----BEGIN PRIVATE KEY-----'
    with pytest.raises(content_security.ContentDenied):
        provider_payload.prepare(value,managed_images=True)


@pytest.mark.parametrize('stream', [False, True])
def test_native_transport_receives_the_exact_inspected_bytes(monkeypatch, stream):
    from contextlib import contextmanager
    from lib import model_dispatch, provider_capability_probes
    sent, admitted, deltas = [], [], []
    @contextmanager
    def dispatch(profile, payload):
        admitted.append(payload)
        yield model_dispatch.DispatchTicket()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size):
            return json.dumps(dict(model='fixture', choices=[dict(message=dict(content='Safe complete answer'), finish_reason='stop')])).encode()
        def __iter__(self):
            for event in [dict(model='fixture', choices=[dict(index=0, delta=dict(content='Safe complete answer'), finish_reason=None)]),
                          dict(model='fixture', choices=[dict(index=0, delta={}, finish_reason='stop')])]:
                yield ('data: '+json.dumps(event)+'\n\n').encode()
            yield b'data: [DONE]\n\n'
    def open_request(request, **kwargs):
        sent.append(request)
        return Response()
    monkeypatch.setattr(model_dispatch, 'dispatch', dispatch)
    monkeypatch.setattr(native_runtime.urllib.request, 'urlopen', open_request)
    monkeypatch.setattr(provider_capability_probes, 'apply_parameters', lambda profile, value: dict(value, provider_option='safe final option'))
    profile = dict(provider_url='https://example.test/v1', model_id='fixture')
    messages = [dict(role='user', content='中文请求')]
    result = (native_runtime._stream_llm(profile, messages, deltas.append) if stream else native_runtime._call_llm(profile, messages))
    assert len(sent) == len(admitted) == 1
    assert sent[0].get_method() == 'POST' and sent[0].full_url == 'https://example.test/v1/chat/completions'
    assert json.loads(sent[0].data) == admitted[0]
    receipt = result['provider_input_inspection']
    assert receipt['request_sha256'] == hashlib.sha256(sent[0].data).hexdigest()
    assert receipt['byte_count'] == len(sent[0].data)
    assert result['content'] == 'Safe complete answer' and result['request_complete']
    if stream: assert deltas == ['Safe complete answer']
