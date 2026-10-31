import json

import httpx
import pytest


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-key')
    monkeypatch.delenv('DEEPSEEK_BASE_URL', raising=False)
    monkeypatch.delenv('DEEPSEEK_MODEL', raising=False)


def context(messages=()):
    return {'system': '规划指令', 'tools': [{'type': 'function', 'function': {'name': 'search_materials',
             'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}}}],
            'memory': {'request': {'topic': '字幕推广', 'budget_units': 10}},
            'history_summary': [], 'limits': {'model_remaining': 31, 'action_remaining': 24}, 'messages': list(messages)}


def completion(message=None, *, reason='tool_calls', usage=None):
    return {'choices': [{'message': message or {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'actual-call', 'type': 'function', 'function': {'name': 'search_materials', 'arguments': '{"query":"字幕"}'}}]},
        'finish_reason': reason}], 'usage': usage if usage is not None else {'prompt_tokens': 123, 'completion_tokens': 45}}


def test_planner_uses_official_http_protocol_and_keeps_tool_result_pair():
    from content_planner.deepseek import DeepSeekModelClient

    calls = []
    original = completion()['choices'][0]['message']
    observation = {'role': 'tool', 'tool_call_id': 'actual-call', 'content': '{"ok":true,"materials":[]}'}

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=completion())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = DeepSeekModelClient(client=client)
        result = model.decide(context([original, observation]))
    assert result == original and len(calls) == 1
    request = calls[0]
    assert str(request.url) == 'https://api.deepseek.com/chat/completions'
    assert request.headers['authorization'] == 'Bearer unit-test-key'
    payload = json.loads(request.content)
    assert payload['model'] == 'deepseek-v4-pro' and payload['thinking'] == {'type': 'disabled'}
    assert payload['temperature'] == 0 and payload['max_tokens'] == 2048 and payload['stream'] is False
    assert payload['tool_choice'] == 'auto' and 'parallel_tool_calls' not in payload
    assert payload['messages'][-2:] == [original, observation]
    assert json.loads(payload['messages'][1]['content'])['memory']['request']['budget_units'] == 10
    assert model.last_usage == {'input_tokens': 123, 'output_tokens': 45}


def test_script_requests_json_without_tools_and_discards_private_reasoning():
    from content_planner.catalog import load_catalog
    from content_planner.contracts import ScriptDraft
    from content_planner.deepseek import DeepSeekModelClient
    from content_planner.domain import parse_script

    draft = {'title': '字幕演示', 'hook': '试试字幕', 'body': '自动生成的字幕文本可以编辑。',
             'cta': '体验字幕编辑', 'source_ids': ['M01']}
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=completion({'role': 'assistant', 'content': json.dumps(draft),
                             'reasoning_content': 'PRIVATE_REASONING'}, reason='stop'))

    script_context = {'topic': '字幕推广', 'material': {'material_id': 'M01', 'facts': ['字幕文本可以编辑。']},
                      'creative_brief': '展示字幕', 'output_schema': ScriptDraft.model_json_schema()}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = DeepSeekModelClient(client=client)
        raw = model.generate_script(script_context)
    assert parse_script(raw, load_catalog().materials[0].model_dump(mode='json')).model_dump() == draft
    assert calls[0]['response_format'] == {'type': 'json_object'} and 'tools' not in calls[0]
    assert calls[0]['max_tokens'] == 1536 and 'json' in calls[0]['messages'][0]['content'].lower()
    assert json.loads(calls[0]['messages'][1]['content']) == script_context
    assert 'PRIVATE_REASONING' not in raw


@pytest.mark.parametrize('status,code,retryable', [(401, 'AUTH_ERROR', False), (403, 'AUTH_ERROR', False),
    (400, 'MODEL_CONFIG_ERROR', False), (402, 'MODEL_CONFIG_ERROR', False), (422, 'MODEL_CONFIG_ERROR', False),
    (302, 'MODEL_CONFIG_ERROR', False), (429, 'MODEL_UNAVAILABLE', True), (500, 'MODEL_UNAVAILABLE', True),
    (503, 'MODEL_UNAVAILABLE', True)])
def test_http_failure_maps_safely_without_retry_or_redirect(status, code, retryable):
    from content_planner.deepseek import DeepSeekModelClient
    from content_planner.model import ModelUnavailable

    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error': {'message': 'unit-test-key PRIVATE_SERVER_BODY'}},
                              headers={'Location': 'https://untrusted.example/collect'})
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        model = DeepSeekModelClient(client=client)
        with pytest.raises(ModelUnavailable) as caught:
            model.decide(context())
    assert caught.value.code == code and caught.value.retryable is retryable
    assert 'unit-test-key' not in str(caught.value) and 'PRIVATE_SERVER_BODY' not in str(caught.value)
    assert len(calls) == 1 and model.last_usage is None


@pytest.mark.parametrize('error', [httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout])
def test_network_failure_is_recoverable_and_single_attempt(error):
    from content_planner.deepseek import DeepSeekModelClient
    from content_planner.model import ModelUnavailable

    calls = []
    def handler(request):
        calls.append(request)
        raise error('unit-test-key SHOULD_NOT_BE_LOGGED', request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelUnavailable) as caught:
            DeepSeekModelClient(client=client).decide(context())
    assert caught.value.code == 'MODEL_UNAVAILABLE' and caught.value.retryable
    assert 'unit-test-key' not in str(caught.value) and len(calls) == 1


@pytest.mark.parametrize('body', [[], {}, {'choices': []},
    {'choices': [{'message': 'invalid', 'finish_reason': 'stop'}]},
    completion(reason='length'), completion(reason='content_filter'),
    {'choices': completion()['choices'] * 2}, {'choices': [{'message': {'role': 'user'}, 'finish_reason': 'stop'}]}])
def test_invalid_or_truncated_completion_is_not_accepted(body):
    from content_planner.deepseek import DeepSeekModelClient
    from content_planner.model import ModelUnavailable

    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        with pytest.raises(ModelUnavailable) as caught:
            DeepSeekModelClient(client=client).decide(context())
    assert caught.value.code == 'MODEL_PROTOCOL_ERROR' and not caught.value.retryable


def test_non_json_response_is_safe_protocol_error():
    from content_planner.deepseek import DeepSeekModelClient
    from content_planner.model import ModelUnavailable

    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'PRIVATE_BODY'))) as client:
        with pytest.raises(ModelUnavailable) as caught:
            DeepSeekModelClient(client=client).decide(context())
    assert caught.value.code == 'MODEL_PROTOCOL_ERROR' and 'PRIVATE_BODY' not in str(caught.value)


@pytest.mark.parametrize('usage', [{}, {'prompt_tokens': True, 'completion_tokens': -1},
                                 {'prompt_tokens': '123', 'completion_tokens': 45}])
def test_usage_does_not_invent_unknown_token_counts(usage):
    from content_planner.deepseek import DeepSeekModelClient

    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=completion(usage=usage)))) as client:
        model = DeepSeekModelClient(client=client)
        model.decide(context())
    assert model.last_usage['input_tokens'] is None
    assert model.last_usage['output_tokens'] == (45 if usage.get('completion_tokens') == 45 else None)


def offline_http_model(handler):
    from content_planner.deepseek import DeepSeekModelClient
    return DeepSeekModelClient(client=httpx.Client(transport=httpx.MockTransport(handler)))


def input_and_clock():
    from datetime import datetime, timezone

    class Clock:
        def now(self): return datetime(2026, 10, 31, 2, tzinfo=timezone.utc)

    return {'request_id': 'http-test', 'topic': '字幕推广', 'budget_units': 14,
            'deadline_at': '2026-10-31T06:00:00+00:00'}, Clock()


def test_real_graph_uses_http_observations_and_persists_safe_actual_usage(tmp_path):
    from importlib import resources
    from content_planner.service import run_task, show_task
    from content_planner.storage import Repository

    fixture = json.loads(resources.files('content_planner').joinpath('data/mock-scenario.json').read_text(encoding='utf-8'))
    decisions = iter(fixture['decisions'])
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        message = ({'role': 'assistant', 'content': fixture['responses'][0]} if 'response_format' in payload else next(decisions))
        return httpx.Response(200, json=completion({**message, 'reasoning_content': 'PRIVATE_REASONING'},
                              reason='stop' if 'response_format' in payload else 'tool_calls'))
    model = offline_http_model(handler)
    raw, clock = input_and_clock()
    result = run_task(raw, database=tmp_path / 'runtime.db', model=model, clock=clock)
    assert result['status'] == 'completed' and result['total_units'] == 8 and len(calls) == 6
    assert result['usage'] == {'model_requests': 6, 'action_calls': 5, 'input_tokens': 738,
                               'output_tokens': 270, 'api_cost_usd': None}
    with Repository(tmp_path / 'runtime.db') as repo:
        events = repo.events(raw['request_id'])
    assert 'unit-test-key' not in json.dumps(events) and 'PRIVATE_REASONING' not in json.dumps(events)
    assert show_task(raw['request_id'], database=tmp_path / 'runtime.db')['usage'] == result['usage']
    assert calls[1]['messages'][-1]['role'] == 'tool'


@pytest.mark.parametrize('where,status,code', [('planner', 401, 'AUTH_ERROR'), ('script', 401, 'AUTH_ERROR'),
                                             ('script', 400, 'MODEL_CONFIG_ERROR'), ('script', 200, 'MODEL_PROTOCOL_ERROR')])
def test_fatal_model_error_keeps_code_and_stops_without_another_planner_call(tmp_path, where, status, code):
    from importlib import resources
    from content_planner.service import run_task, resume_task

    fixture = json.loads(resources.files('content_planner').joinpath('data/mock-scenario.json').read_text(encoding='utf-8'))
    decisions = iter(fixture['decisions'])
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if where == 'planner' or 'response_format' in payload or len(calls) > 4:
            return httpx.Response(status, json=completion(reason='length') if status == 200 else {'error': 'PRIVATE_BODY'})
        return httpx.Response(200, json=completion(next(decisions)))
    model = offline_http_model(handler)
    raw, clock = input_and_clock()
    result = run_task(raw, database=tmp_path / 'runtime.db', model=model, clock=clock)
    assert result['status'] == 'incomplete' and result['reason'] == code
    assert len(calls) == (1 if where == 'planner' else 4)
    assert result['saved_plan'] is None
    if where == 'script':
        assert result['tool_results'][-1]['error']['code'] == code
    assert result['usage']['input_tokens'] == (492 if status == 200 else None)
    refused = resume_task(raw['request_id'], database=tmp_path / 'runtime.db', model=model, clock=clock)
    assert refused['reason'] == 'RESUME_NOT_ALLOWED'


@pytest.mark.parametrize('field,value', [('DEEPSEEK_API_KEY', ''), ('DEEPSEEK_MODEL', 'other-model'),
    ('DEEPSEEK_BASE_URL', 'https://untrusted.example'), ('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/beta')])
def test_invalid_live_configuration_is_not_used(monkeypatch, field, value):
    from content_planner.deepseek import DeepSeekModelClient
    from content_planner.domain import Fault

    monkeypatch.setenv(field, value)
    with pytest.raises(Fault) as caught:
        DeepSeekModelClient()
    assert caught.value.code == 'CONFIG_ERROR'


def test_service_live_backend_requires_key_without_mock_fallback_or_task_creation(tmp_path, monkeypatch):
    from content_planner.service import run_task
    from content_planner.domain import Fault

    monkeypatch.delenv('DEEPSEEK_API_KEY')
    raw, clock = input_and_clock()
    with pytest.raises(Fault) as caught:
        run_task(raw, backend='deepseek', database=tmp_path / 'runtime.db', clock=clock)
    assert caught.value.code == 'CONFIG_ERROR' and not (tmp_path / 'runtime.db').exists()


def test_missing_input_live_does_not_need_credentials(tmp_path, monkeypatch):
    from content_planner.service import run_task

    monkeypatch.delenv('DEEPSEEK_API_KEY')
    raw, clock = input_and_clock()
    result = run_task({**raw, 'budget_units': None}, backend='deepseek', database=tmp_path / 'runtime.db', clock=clock)
    assert result['backend'] == 'deepseek' and result['status'] == 'needs_input'
    assert result['usage']['model_requests'] == 0 and not (tmp_path / 'runtime.db').exists()


def test_live_runner_requires_explicit_paid_flag(tmp_path):
    from pathlib import Path
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[2] / 'scripts/evaluate_live.py'
    process = subprocess.run([sys.executable, '-X', 'utf8', str(script)], cwd=tmp_path, capture_output=True)
    assert process.returncode == 2 and b'--live is required' in process.stderr
    assert not (tmp_path / 'examples').exists() and not (tmp_path / 'work').exists()


def test_completed_live_task_can_be_queried_without_current_key(tmp_path, monkeypatch):
    from importlib import resources
    from content_planner.service import run_task, resume_task

    fixture = json.loads(resources.files('content_planner').joinpath('data/mock-scenario.json').read_text(encoding='utf-8'))
    decisions = iter(fixture['decisions'])
    def handler(request):
        payload = json.loads(request.content)
        message = {'role': 'assistant', 'content': fixture['responses'][0]} if 'response_format' in payload else next(decisions)
        return httpx.Response(200, json=completion(message, reason='stop' if 'response_format' in payload else 'tool_calls'))
    raw, clock = input_and_clock()
    initial = run_task(raw, database=tmp_path / 'runtime.db', model=offline_http_model(handler), clock=clock)
    monkeypatch.delenv('DEEPSEEK_API_KEY')
    assert run_task(raw, database=tmp_path / 'runtime.db', backend='deepseek') == initial
    assert resume_task(raw['request_id'], database=tmp_path / 'runtime.db') == initial


def test_conflicting_input_reports_selected_backend_without_configuring_it(tmp_path, monkeypatch):
    from content_planner.service import run_task
    from content_planner.model import load_mock_scenario

    raw, clock = input_and_clock()
    model, _ = load_mock_scenario(None)
    initial = run_task(raw, database=tmp_path / 'runtime.db', model=model, clock=clock)
    assert initial['status'] == 'completed'
    monkeypatch.delenv('DEEPSEEK_API_KEY')
    conflict = run_task({**raw, 'budget_units': 13}, backend='deepseek', database=tmp_path / 'runtime.db')
    assert conflict['reason'] == 'REQUEST_CONFLICT' and conflict['backend'] == 'deepseek'
    assert conflict['usage']['model_requests'] == 0
