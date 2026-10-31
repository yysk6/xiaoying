"""Run with the installed wheel's Python -I from a non-repository directory; zero network."""
from datetime import datetime, timezone
from importlib import resources
import json
from pathlib import Path
import socket
import sys
import tempfile

import httpx
import content_planner
from content_planner.deepseek import DeepSeekModelClient
from content_planner.intake import IntakeSession
from content_planner.service import run_task


def forbidden(*args, **kwargs):
    raise AssertionError('Network forbidden in installed-package verification')


socket.socket.connect = forbidden
assert Path(content_planner.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
fixture = json.loads(resources.files('content_planner').joinpath('data/mock-scenario.json').read_text(encoding='utf-8'))
decisions, payloads = iter(fixture['decisions']), []


def handler(request):
    payload = json.loads(request.content)
    payloads.append(payload)
    if payload['messages'][0]['content'].startswith('intake-v2'):
        patch = {key: dict(value=value, source=value) for key, value in
                 [('topic', '字幕推广'), ('budget_units', '预算10'), ('deadline_at', '明天下午六点')]}
        message = dict(role='assistant', content=json.dumps(patch, ensure_ascii=False))
    elif 'response_format' in payload:
        message = dict(role='assistant', content=fixture['responses'][0])
    else:
        message = next(decisions)
    return httpx.Response(200, json={'choices': [{'message': message,
        'finish_reason': 'tool_calls' if message.get('tool_calls') else 'stop'}],
        'usage': {'prompt_tokens': 3, 'completion_tokens': 2}})


class Clock:
    def now(self):
        return datetime(2026, 10, 31, 2, tzinfo=timezone.utc)


with tempfile.TemporaryDirectory(prefix='intake-wheel-') as temporary, \
        httpx.Client(transport=httpx.MockTransport(handler)) as client:
    model = DeepSeekModelClient(client=client, api_key='offline-package-placeholder')
    intake = IntakeSession(model, Clock())
    assert intake.receive('字幕推广，预算10，明天下午六点')['state'] == 'ready'
    request = intake.receive('确认')['request']
    assert request['deadline_at'] == '2026-11-01T10:00:00+00:00'
    database = Path(temporary) / 'runtime.db'
    result = run_task(request, database=database, model=model, clock=Clock(), backend='deepseek')
    assert result['status'] == 'completed' and result['total_units'] == 8
    assert run_task(request, database=database, model=model, clock=Clock(), backend='deepseek') == result
    assert model.http_attempts == len(payloads) == 7
    assert result['usage']['model_requests'] == 6 and intake.usage()['model_requests'] == 1
    print(json.dumps({'passed': True, 'import_path': content_planner.__file__, 'http_transport': 'MockTransport',
        'live_http_requests': 0, 'adapter_calls': len(payloads), 'status': result['status'], 'total_units': 8,
        'repeat_read_only': True, 'intake_prompt': 'intake-v2', 'python': sys.version}, ensure_ascii=False))
