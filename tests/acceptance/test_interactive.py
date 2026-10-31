"""Manual input follows the same service path as the CLI, with real SQLite."""

from io import StringIO
import json
import os
import pytest

from content_planner.model import FakeModelClient


def test_missing_deadline_through_interactive_input_never_calls_model_or_creates_database(tmp_path):
    from scripts.interactive_planner import console_session

    model = FakeModelClient([])
    source = StringIO(json.dumps({'request_id': 'manual-missing', 'topic': '字幕推广', 'budget_units': 10}) + '\nexit\n')
    target = StringIO()
    console_session(model, source, target, database=tmp_path / 'runtime.db', output_root=tmp_path / 'runs', input_mode='json')
    result = json.loads((tmp_path / 'runs/manual-missing/output.json').read_text(encoding='utf-8'))
    assert result['status'] == 'needs_input' and result['missing_fields'] == ['deadline_at']
    assert model.requests == model.decision_requests == []
    assert not (tmp_path / 'runtime.db').exists()


def test_manual_session_runs_exports_and_reads_repeated_input_without_new_calls(tmp_path):
    from datetime import datetime, timedelta, timezone
    from content_planner.model import load_mock_scenario
    from scripts.interactive_planner import console_session

    model, _ = load_mock_scenario()
    request = {'request_id': 'manual-normal', 'topic': '影芽剪辑字幕功能推广', 'budget_units': 10,
               'deadline_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    line = json.dumps(request, ensure_ascii=False)
    source = StringIO('not json\n' + line + '\n' + line + '\nshow manual-normal\nexit\n')
    target = StringIO()
    console_session(model, source, target, database=tmp_path / 'runtime.db', output_root=tmp_path / 'runs', input_mode='json')
    result = json.loads((tmp_path / 'runs/manual-normal/output.json').read_text(encoding='utf-8'))
    assert result['status'] == 'completed' and result['total_units'] == 8
    assert len(model.requests) == 1 and len(model.decision_requests) == 5
    assert len(result['execution_steps']) == 5
    assert 'INVALID_JSON' in target.getvalue()
    assert (tmp_path / 'runs/manual-normal/trace.jsonl').is_file()


def test_natural_draft_without_confirmation_does_not_start_business(tmp_path):
    from datetime import datetime, timezone
    from scripts.interactive_planner import console_session
    class Clock:
        def now(self):
            return datetime(2026, 10, 31, 2, tzinfo=timezone.utc)
    patch = {key: {'value': value, 'source': value} for key, value in
             [('topic', '字幕推广'), ('budget_units', '预算10'), ('deadline_at', '明天下午六点')]}
    model = FakeModelClient([], intake_responses=[json.dumps(patch, ensure_ascii=False)])
    target = StringIO()
    console_session(model, StringIO('请做字幕推广，预算10，明天下午六点\nexit\n'), target,
                    database=tmp_path / 'runtime.db', output_root=tmp_path / 'runs', clock=Clock())
    assert not (tmp_path / 'runtime.db').exists()
    assert len(model.intake_requests) == 1 and model.requests == model.decision_requests == []
    assert '2026-11-01 18:00:00' in target.getvalue() and 'UTC+08:00' in target.getvalue()
    assert '确认' in target.getvalue()
    log = (tmp_path / 'runs/intake.jsonl').read_text(encoding='utf-8')
    assert '请做字幕推广，预算10，明天下午六点' not in log
    assert 'intake-v2' in log and 'ready' in log


def test_natural_multiturn_edit_confirm_and_repeat_use_real_sqlite_once(tmp_path):
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock
    from content_planner.storage import Repository
    from scripts.interactive_planner import console_session
    def patch(**fields):
        return json.dumps({key: {'value': value, 'source': value} for key, value in fields.items()}, ensure_ascii=False)
    model = FakeModelClient([DRAFT], decisions=NORMAL, intake_responses=[
        patch(topic='字幕推广'), patch(budget_units='预算10', deadline_at='明天下午六点'),
        patch(budget_units='预算8')])
    target = StringIO()
    console_session(model, StringIO('字幕推广\n预算10，明天下午六点\n预算8，其他不变\n确认\n确认\nexit\n'), target,
                    database=tmp_path / 'runtime.db', output_root=tmp_path / 'runs', clock=FixedClock())
    outputs = list((tmp_path / 'runs').glob('nl-*/output.json'))
    assert len(outputs) == 1
    result = json.loads(outputs[0].read_text(encoding='utf-8'))
    assert result['status'] == 'completed' and result['total_units'] == 8
    with Repository(tmp_path / 'runtime.db') as repo:
        request = repo.get_request(result['request_id'])['input']
        assert request['budget_units'] == 8 and request['topic'] == '字幕推广'
        assert request['deadline_at'] == '2026-11-01T10:00:00+00:00'
        assert repo.get_plan(result['request_id'])['saved_plan'] == result['saved_plan']
    assert len(model.intake_requests) == 3 and len(model.requests) == 1 and len(model.decision_requests) == 5
    records = [json.loads(line) for line in (tmp_path / 'runs/intake.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len([r for r in records if r['kind'] == 'confirmed']) == 1
    assert records[-1]['kind'] == 'business_result'
    assert '需求理解用量' in target.getvalue() and '业务用量' in target.getvalue()


def test_natural_json_paste_cancel_and_extraction_failure_do_not_execute(tmp_path):
    from content_planner.model import ModelUnavailable
    from scripts.interactive_planner import console_session
    model = FakeModelClient([], intake_responses=[json.dumps({'topic': {'value': '字幕推广', 'source': '字幕推广'}}),
                                                ModelUnavailable('PRIVATE_PROVIDER_BODY', code='AUTH_ERROR', retryable=False)])
    target = StringIO()
    console_session(model, StringIO('{"topic":"不绕过确认"}\n字幕推广\n预算10\n确认\n取消\n确认\nexit\n'), target,
                    database=tmp_path / 'runtime.db', output_root=tmp_path / 'runs')
    assert not (tmp_path / 'runtime.db').exists()
    assert len(model.intake_requests) == 2 and not model.decision_requests
    assert 'PRIVATE_PROVIDER_BODY' not in target.getvalue()
    log = (tmp_path / 'runs/intake.jsonl').read_text(encoding='utf-8')
    assert 'PRIVATE_PROVIDER_BODY' not in log and 'extraction_failed' in log


def test_confirmed_natural_task_can_resume_after_a_script_failure(tmp_path):
    from tests.acceptance.test_cli import DRAFT, SEARCH, REVISE, GENERATE, ESTIMATE, SAVE, FixedClock, call
    from content_planner.model import ModelUnavailable
    from scripts.interactive_planner import console_session
    patch = {key: {'value': value, 'source': value} for key, value in
             [('topic', '字幕推广'), ('budget_units', '预算10'), ('deadline_at', '明天下午六点')]}
    model = FakeModelClient([ModelUnavailable('injected script failure'), DRAFT], decisions=[
        SEARCH, REVISE, GENERATE, ModelUnavailable('planner temporarily unavailable'),
        call('generate_script', 'generate-retry', plan_revision=1), ESTIMATE, SAVE],
        intake_responses=[json.dumps(patch, ensure_ascii=False)])
    class Input:
        lines = iter(['字幕推广，预算10，明天下午六点\n', '确认\n', 'RESUME', 'exit\n'])
        def readline(self):
            value = next(self.lines)
            if value == 'RESUME':
                path = next((tmp_path / 'runs').glob('nl-*/output.json'))
                first = json.loads(path.read_text(encoding='utf-8'))
                assert first['status'] == 'incomplete'
                assert first['execution_steps'][0]['status'] == 'succeeded'
                return 'resume ' + first['request_id'] + '\n'
            return value
    console_session(model, Input(), StringIO(), database=tmp_path / 'runtime.db', output_root=tmp_path / 'runs', clock=FixedClock())
    result = json.loads(next((tmp_path / 'runs').glob('nl-*/output.json')).read_text(encoding='utf-8'))
    assert result['status'] == 'completed'
    scripts = [s for s in result['execution_steps'] if s['tool'] == 'generate_script']
    assert [s['status'] for s in scripts] == ['failed', 'succeeded']
    assert len([s for s in result['execution_steps'] if s['tool'] == 'search_materials']) == 1


def test_real_terminal_process_starts_and_exits_without_http_or_exposing_stdin_key(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    ready = tmp_path / 'ready.json'
    result = subprocess.run([sys.executable, '-X', 'utf8', 'scripts/interactive_planner.py', '--key-stdin',
        '--db', str(tmp_path / 'runtime.db'), '--output-root', str(tmp_path / 'runs'), '--ready-file', str(ready)],
        input='offline-placeholder-credential\nexit\n', capture_output=True, text=True, encoding='utf-8',
        cwd=Path(__file__).resolve().parents[2], timeout=20)
    assert result.returncode == 0, result.stderr
    status = json.loads(ready.read_text(encoding='utf-8'))
    assert status['status'] == 'stopped' and status['http_attempts'] == 0 and status['input_mode'] == 'natural'
    assert not (tmp_path / 'runtime.db').exists()
    assert 'offline-placeholder-credential' not in result.stdout + result.stderr + ready.read_text(encoding='utf-8')


@pytest.mark.skipif(os.name != 'nt', reason='Windows console launcher')
@pytest.mark.parametrize('redirected_pid', [False, True])
@pytest.mark.parametrize('input_mode', ['natural', 'json'])
def test_launcher_waits_for_a_complete_ready_file(tmp_path, monkeypatch, redirected_pid, input_mode):
    import getpass
    import subprocess
    from scripts.interactive_planner import main

    ready = tmp_path / 'session.json'

    class StartingProcess:
        pid = 987654

        def __init__(self, command, **kwargs):
            assert command[command.index('--input-mode') + 1] == input_mode
            self.stdin = StringIO()
            self.launch_id = command[command.index('--launch-id') + 1] if '--launch-id' in command else None
            ready.write_text('', encoding='utf-8')

        def poll(self):
            ready.write_text(json.dumps({'pid': self.pid + int(redirected_pid), 'launch_id': self.launch_id,
                                        'status': 'ready', 'http_attempts': 0}), encoding='utf-8')
            return None

    monkeypatch.setattr(getpass, 'getpass', lambda prompt: 'unit-hidden-key')
    monkeypatch.setattr(subprocess, 'Popen', StartingProcess)
    assert main(['--launch-window', '--input-mode', input_mode, '--ready-file', str(ready)]) == 0
