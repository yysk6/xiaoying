from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from content_planner.model import FakeModelClient, ModelUnavailable


ROOT = Path(__file__).resolve().parents[2]


class FixedClock:
    def now(self):
        return datetime(2026, 10, 31, 2, tzinfo=timezone.utc)


def validate(value, schema='result'):
    schemas = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in (ROOT / 'contracts').glob('*.schema.json')}
    registry = Registry().with_resources((name, Resource.from_contents(data)) for name, data in schemas.items())
    Draft202012Validator(schemas[schema + '.schema.json'], registry=registry, format_checker=FormatChecker()).validate(value)


def request(**changes):
    return {'request_id': 's5', 'topic': '字幕推广', 'budget_units': 14,
            'deadline_at': '2026-10-31T06:00:00+00:00', **changes}


def call(name, call_id, **arguments):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': call_id, 'type': 'function', 'function': {'name': name,
         'arguments': json.dumps({'rationale': '显式离线动作', **arguments}, ensure_ascii=False)}}]}


DRAFT = json.dumps({'title': '字幕演示', 'hook': '试试字幕', 'body': '自动生成的字幕文本可以编辑。',
                    'cta': '体验字幕编辑', 'source_ids': ['M01']}, ensure_ascii=False)
SEARCH = call('search_materials', 'search', query='字幕', top_k=1)
REVISE = call('revise_plan', 'revise', material_id='M01', creative_brief='展示字幕编辑', production_mode='basic')
GENERATE = call('generate_script', 'generate', plan_revision=1)
ESTIMATE = call('estimate_cost', 'estimate', plan_revision=1)
SAVE = call('save_plan', 'save', plan_revision=1,
            estimate_id='estimate_' + hashlib.sha256(b'estimate').hexdigest())
NORMAL = [SEARCH, REVISE, GENERATE, ESTIMATE, SAVE]


def test_missing_input_returns_schema_result_without_creating_database(tmp_path):
    from content_planner.service import run_task

    model = FakeModelClient([])
    result = run_task(request(budget_units=None), database=tmp_path / 'runtime.db', model=model, clock=FixedClock())
    validate(result)
    assert result['status'] == 'needs_input' and result['missing_fields'] == ['budget_units']
    assert result['tool_results'] == [] and result['manifest'] is None
    assert model.requests == model.decision_requests == []
    assert not (tmp_path / 'runtime.db').exists()


def test_normal_task_reports_committed_plan_and_real_execution_history(tmp_path):
    from content_planner.service import run_task
    from content_planner.storage import Repository

    model = FakeModelClient([DRAFT], decisions=NORMAL)
    result = run_task(request(), database=tmp_path / 'runtime.db', model=model, clock=FixedClock())
    validate(result)
    assert result['status'] == 'completed' and result['total_units'] == 8
    assert len(result['task_plan']) == 4 and all(s['status'] == 'planned' for s in result['task_plan'])
    assert [s['status'] for s in result['execution_steps']] == ['succeeded'] * 5
    assert [s['result_index'] for s in result['execution_steps']] == [0, 1, 2, 3, 4]
    assert result['usage']['model_requests'] == 6 and result['usage']['action_calls'] == 5
    assert result['backend'] == result['model'] == 'mock'
    with Repository(tmp_path / 'runtime.db') as repo:
        assert repo.get_plan('s5')['saved_plan'] == result['saved_plan']


@pytest.mark.parametrize('changes', [{'budget_units': True}, {'budget_units': 10.5}, {'topic': ''},
    {'deadline_at': '2026-10-30T06:00:00+00:00'}, {'deadline_at': '2026-10-31T02:00:00+00:00'},
    {'deadline_at': '2026-10-31T06:00:00'}, {'extra': 'forbidden'}])
def test_invalid_input_keeps_valid_id_and_does_not_create_task(tmp_path, changes):
    from content_planner.service import run_task

    model = FakeModelClient([])
    result = run_task(request(**changes), database=tmp_path / 'runtime.db', model=model, clock=FixedClock())
    validate(result)
    assert result['status'] == 'needs_input' and result['request_id'] == 's5'
    assert result['reason'] == 'INVALID_ARGUMENT' and model.decision_requests == []
    assert not (tmp_path / 'runtime.db').exists()


def cli(tmp_path, *arguments):
    return subprocess.run([sys.executable, '-X', 'utf8', '-m', 'content_planner', *map(str, arguments)],
                          cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')


def files(tmp_path, *, changes=None, decisions=NORMAL, responses=None):
    source, scenario = tmp_path / 'input.json', tmp_path / 'scenario.json'
    source.write_text(json.dumps(request(**(changes or {})), ensure_ascii=False), encoding='utf-8')
    scenario.write_text(json.dumps({'decisions': decisions, 'responses': [DRAFT] if responses is None else responses,
                                   'now': FixedClock().now().isoformat()}, ensure_ascii=False), encoding='utf-8')
    return source, scenario


def test_cli_run_exports_schema_json_markdown_and_linked_trace(tmp_path):
    source, scenario = files(tmp_path)
    completed = cli(tmp_path, 'run', '--input', source, '--mock-scenario', scenario,
                    '--db', tmp_path / 'runtime.db', '--output-dir', tmp_path / 'out')
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    validate(result)
    assert result == json.loads((tmp_path / 'out/output.json').read_text(encoding='utf-8'))
    trace = [json.loads(line) for line in Path(result['trace_path']).read_text(encoding='utf-8').splitlines()]
    for event in trace:
        validate(event, 'trace-event')
        assert event['backend'] == event['model'] == 'mock'
        assert event['next_decision_event_id'] is None or event['next_decision_event_id'] > event['event_id']
    generated = next(e for e in trace if e['name'] == 'generate_script' and e['phase'] == 'succeeded')
    assert generated['result_ref'] == 'tool_results:2' and generated['next_decision_event_id']
    assert 'response' not in ''.join(json.dumps(e) for e in trace)
    markdown = (tmp_path / 'out/plan.md').read_text(encoding='utf-8')
    assert '8' in markdown and 'M01' in markdown and '自动生成的字幕文本可以编辑' in markdown
    assert 'planned' in markdown and 'mock' in markdown


def test_repeat_run_and_show_read_history_even_after_deadline_and_without_scenario(tmp_path):
    from content_planner.service import run_task, show_task
    from content_planner.storage import Repository

    db = tmp_path / 'runtime.db'
    first = run_task(request(), database=db, model=FakeModelClient([DRAFT], decisions=NORMAL), clock=FixedClock())
    with Repository(db) as repo:
        before = repo.events('s5')
    # SystemClock is now later than the fixed task deadline. Missing scenario must never be opened.
    second = run_task(request(), database=db, mock_scenario=tmp_path / 'missing.json')
    assert second == first == show_task('s5', database=db)
    with Repository(db) as repo:
        assert repo.events('s5') == before
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT count(*) FROM plans').fetchone()[0] == 1


@pytest.mark.parametrize('changes', [{'budget_units': 13}, {'topic': '另一个主题'},
                                    {'deadline_at': '2026-10-31T07:00:00+00:00'}])
def test_conflicting_run_does_not_change_original_task(tmp_path, changes):
    from content_planner.service import run_task, show_task

    db = tmp_path / 'runtime.db'
    first = run_task(request(), database=db, model=FakeModelClient([DRAFT], decisions=NORMAL), clock=FixedClock())
    conflict = run_task(request(**changes), database=db, mock_scenario=tmp_path / 'missing.json')
    validate(conflict)
    assert conflict['reason'] == 'REQUEST_CONFLICT' and conflict['saved_plan'] is None
    assert show_task('s5', database=db) == first


def test_export_failure_keeps_committed_plan_and_show_can_export_again(tmp_path):
    source, scenario = files(tmp_path)
    out = tmp_path / 'blocked'
    out.write_text('file blocks directory', encoding='utf-8')
    first = cli(tmp_path, 'run', '--input', source, '--mock-scenario', scenario,
                '--db', tmp_path / 'runtime.db', '--output-dir', out)
    assert first.returncode == 0, first.stderr
    result = json.loads(first.stdout)
    validate(result)
    assert result['warnings'][0]['code'] == 'EXPORT_FAILED' and result['trace_path'] is None
    assert 'EXPORT_FAILED' in first.stderr and result['saved_plan']
    shown = cli(tmp_path, 'show', '--request-id', 's5', '--db', tmp_path / 'runtime.db', '--output-dir', tmp_path / 'good')
    assert shown.returncode == 0, shown.stderr
    recovered = json.loads(shown.stdout)
    assert recovered['saved_plan'] == result['saved_plan'] and recovered['usage'] == result['usage']
    assert recovered['warnings'] == [] and (tmp_path / 'good/plan.md').is_file()


@pytest.mark.parametrize('case', ['missing', 'retry', 'persistent_failure', 'budget', 'deadline',
                                  'revision', 'deadline_revision', 'empty_then_hit', 'no_material', 'invalid_script', 'protocol'])
def test_cli_core_cases_preserve_actual_observations_and_status(tmp_path, case):
    decisions, responses, changes = list(NORMAL), [DRAFT], {}
    expected_status, expected_reason, expected_code = 'completed', None, 0
    if case == 'missing':
        changes = {'topic': None, 'budget_units': None}
        expected_status, expected_reason, expected_code = 'needs_input', 'NEEDS_INPUT', 2
    elif case == 'retry':
        decisions.insert(3, call('generate_script', 'retry', plan_revision=1))
        responses.insert(0, {'error': 'MODEL_UNAVAILABLE'})
    elif case in {'persistent_failure', 'invalid_script'}:
        decisions = NORMAL[:3]
        if case == 'persistent_failure':
            decisions.append(call('generate_script', 'retry', plan_revision=1))
            responses = [{'error': 'MODEL_UNAVAILABLE'}] * 2
        else:
            responses = [DRAFT.replace('M01', 'M02')]
        decisions.append(call('stop_task', 'stop', reason='tool_failure', message='保留检索与候选，生成失败'))
        expected_status, expected_reason, expected_code = 'incomplete', 'tool_failure', 3
    elif case in {'budget', 'deadline'}:
        changes = {'budget_units': 5} if case == 'budget' else {'deadline_at': '2026-10-31T03:00:00+00:00'}
        decisions = NORMAL[:4] + [call('stop_task', 'stop', reason='constraints_unsatisfied', message='已评估候选不满足约束')]
        expected_status, expected_reason, expected_code = 'incomplete', 'constraints_unsatisfied', 3
    elif case in {'revision', 'deadline_revision'}:
        decisions = [SEARCH, call('revise_plan', 'premium', material_id='M01', creative_brief='展示字幕编辑',
                     production_mode='premium'), GENERATE, ESTIMATE,
                     call('revise_plan', 'basic', material_id='M01', creative_brief='展示字幕编辑', production_mode='basic'),
                     call('generate_script', 'reuse', plan_revision=2),
                     call('estimate_cost', 'reestimate', plan_revision=2),
                     call('save_plan', 'save', plan_revision=2,
                          estimate_id='estimate_' + hashlib.sha256(b'reestimate').hexdigest())]
        changes = {'budget_units': 10} if case == 'revision' else {'deadline_at': '2026-10-31T03:40:00+00:00'}
    elif case == 'empty_then_hit':
        decisions.insert(0, call('search_materials', 'empty', query='不存在的素材', top_k=1))
    elif case == 'no_material':
        decisions = [call('search_materials', 'empty', query='不存在的素材', top_k=1),
                     call('stop_task', 'stop', reason='no_material', message='未检索到可用资料')]
        expected_status, expected_reason, expected_code = 'incomplete', 'no_material', 3
    elif case == 'protocol':
        decisions = [call('erase_database', 'bad-1'), call('erase_database', 'bad-2')]
        expected_status, expected_reason, expected_code = 'incomplete', 'MODEL_PROTOCOL_ERROR', 3
    source, scenario = files(tmp_path, changes=changes, decisions=decisions, responses=responses)
    process = cli(tmp_path, 'run', '--input', source, '--mock-scenario', scenario,
                  '--db', tmp_path / 'runtime.db', '--output-dir', tmp_path / 'out')
    assert process.returncode == expected_code, process.stderr
    result = json.loads(process.stdout)
    validate(result)
    assert (result['status'], result['reason']) == (expected_status, expected_reason)
    if case == 'missing':
        assert result['missing_fields'] == ['topic', 'budget_units'] and result['usage']['model_requests'] == 0
        assert result['trace_path'] is None and not (tmp_path / 'runtime.db').exists()
        assert (tmp_path / 'out/trace.jsonl').read_text(encoding='utf-8') == ''
        return
    with sqlite3.connect(tmp_path / 'runtime.db') as db:
        assert db.execute('SELECT count(*) FROM plans').fetchone()[0] == (expected_status == 'completed')
    trace = [json.loads(line) for line in Path(result['trace_path']).read_text(encoding='utf-8').splitlines()]
    for event in trace:
        validate(event, 'trace-event')
    if case in {'retry', 'persistent_failure'}:
        attempts = [s for s in result['execution_steps'] if s['tool'] == 'generate_script']
        assert [s['attempt'] for s in attempts] == [1, 2]
        assert attempts[0]['status'] == 'failed' and attempts[0]['error_code'] == 'SCRIPT_MODEL_UNAVAILABLE'
        failed = next(e for e in trace if e['name'] == 'generate_script' and e['phase'] == 'failed')
        assert failed['next_decision_event_id'] is not None
        assert result['execution_steps'][0]['tool'] == 'search_materials'
        assert sum(s['tool'] == 'search_materials' for s in result['execution_steps']) == 1
    if case in {'budget', 'deadline'}:
        assert result['total_units'] == 8 and result['task_plan'] == []
        gap = result['tool_results'][-1]['data']['latest_gap']
        assert gap['budget_gap_units'] == (3 if case == 'budget' else 0)
        assert gap['deadline_gap_minutes'] == (30 if case == 'deadline' else 0)
    if case in {'revision', 'deadline_revision'}:
        assert result['current_revision'] == 2 and result['total_units'] == 8
        assert [r['data']['total_units'] for r in result['tool_results'] if r['tool'] == 'estimate_cost'] == [12, 8]
        assert result['tool_results'][5]['reused'] and result['usage']['model_requests'] == 9


def test_database_failure_before_commit_never_claims_plan_saved(tmp_path):
    from content_planner.storage import Repository

    db = tmp_path / 'runtime.db'
    with Repository(db):
        pass
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TRIGGER fail_save BEFORE INSERT ON plans BEGIN SELECT RAISE(ABORT,'test fault'); END")
    source, scenario = files(tmp_path, decisions=NORMAL + [call('stop_task', 'stop', reason='tool_failure', message='保存失败')])
    process = cli(tmp_path, 'run', '--input', source, '--mock-scenario', scenario, '--db', db)
    assert process.returncode == 3, process.stderr
    result = json.loads(process.stdout)
    validate(result)
    assert result['saved_plan'] is None and result['tool_results'][-2]['error']['code'] == 'SAVE_FAILED'
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT count(*) FROM plans').fetchone()[0] == 0


def test_save_rechecks_clock_and_reports_new_deadline_gap(tmp_path):
    from content_planner.service import run_task

    class MovingClock:
        instant = FixedClock().now()

        def now(self):
            return self.instant

    clock = MovingClock()

    class DelayedModel(FakeModelClient):
        def decide(self, context):
            response = super().decide(context)
            if response['tool_calls'][0]['function']['name'] == 'save_plan':
                clock.instant = datetime(2026, 10, 31, 5, tzinfo=timezone.utc)
            return response

    decisions = NORMAL + [call('stop_task', 'stop', reason='tool_failure', message='保存时已无法按期完成')]
    result = run_task(request(), database=tmp_path / 'runtime.db',
                      model=DelayedModel([DRAFT], decisions=decisions), clock=clock)
    validate(result)
    assert result['status'] == 'incomplete' and result['saved_plan'] is None
    rejection = result['tool_results'][-2]
    assert rejection['error']['code'] == 'CONSTRAINT_VIOLATION'
    assert rejection['error']['details']['deadline_gap_minutes'] == 30


@pytest.mark.parametrize('arguments,code,reason', [
    (['show', '--request-id', 'missing'], 2, 'REQUEST_NOT_FOUND'),
    (['resume', '--request-id', 'missing'], 2, 'CONFIG_ERROR'),
    (['run', '--input', 'input.json', '--backend', 'deepseek'], 2, 'CONFIG_ERROR'),
    (['run', '--input', 'missing.json'], 2, 'INVALID_ARGUMENT'),
    (['run', '--input', 'input.json', '--mock-scenario', 'broken.json'], 2, 'CONFIG_ERROR')])
def test_cli_configuration_errors_are_explicit_and_never_fall_back(tmp_path, arguments, code, reason):
    files(tmp_path)
    process = cli(tmp_path, *arguments)
    assert process.returncode == code, process.stderr
    result = json.loads(process.stdout)
    validate(result)
    assert result['reason'] == reason and result['usage']['model_requests'] == 0
    assert not (tmp_path / 'work/runtime.db').exists()


def test_cli_storage_path_error_is_process_failure_without_guessing_status(tmp_path):
    source, scenario = files(tmp_path)
    blocked = tmp_path / 'blocked'
    blocked.write_text('file prevents database directory', encoding='utf-8')
    process = cli(tmp_path, 'run', '--input', source, '--mock-scenario', scenario,
                  '--db', blocked / 'runtime.db')
    assert process.returncode == 1
    assert process.stdout == '' and 'STORAGE_UNAVAILABLE' in process.stderr


def test_trace_preserves_maximum_length_model_call_id(tmp_path):
    from content_planner.service import export_task, run_task

    long_id = 'a' * 200
    decisions = NORMAL[:2] + [call('generate_script', long_id, plan_revision=1)] + NORMAL[3:]
    db = tmp_path / 'runtime.db'
    result = run_task(request(), database=db, model=FakeModelClient([DRAFT], decisions=decisions), clock=FixedClock())
    exported = export_task(result, database=db, directory=tmp_path / 'out')
    validate(exported)
    trace = [json.loads(line) for line in Path(exported['trace_path']).read_text(encoding='utf-8').splitlines()]
    for event in trace:
        validate(event, 'trace-event')
    assert any(e['operation_id'] == 'tool:' + long_id + ':script' for e in trace)
    assert result['tool_results'][2]['tool_call_id'] == long_id


def test_markdown_displays_beijing_time(tmp_path):
    from content_planner.service import export_task, run_task

    db = tmp_path / 'runtime.db'
    successful = run_task(request(), database=db, model=FakeModelClient([DRAFT], decisions=NORMAL), clock=FixedClock())
    export_task(successful, database=db, directory=tmp_path / 'success')
    text = (tmp_path / 'success/plan.md').read_text(encoding='utf-8')
    assert '2026-10-31T10:00:00+08:00' in text and 'UTC+08:00' in text


def test_markdown_preserves_gap_after_later_observation(tmp_path):
    from content_planner.service import export_task, run_task

    db = tmp_path / 'runtime.db'
    decisions = NORMAL[:4] + [call('search_materials', 'later-search', query='字幕', top_k=1),
                              {'role': 'assistant', 'content': '停止'}]
    failed = run_task(request(request_id='gap', budget_units=5), database=db,
                      model=FakeModelClient([DRAFT], decisions=decisions), clock=FixedClock())
    export_task(failed, database=db, directory=tmp_path / 'incomplete')
    text = (tmp_path / 'incomplete/plan.md').read_text(encoding='utf-8')
    assert '"budget_gap_units": 3' in text and '"deadline_gap_minutes": 0' in text


def test_cli_stdout_is_utf8_without_python_encoding_flags(tmp_path):
    source, scenario = files(tmp_path)
    process = subprocess.run([sys.executable, '-I', '-m', 'content_planner', 'run', '--input', str(source),
                              '--mock-scenario', str(scenario), '--db', str(tmp_path / 'runtime.db')],
                             cwd=tmp_path, capture_output=True)
    assert process.returncode == 0
    result = json.loads(process.stdout.decode('utf-8'))
    validate(result)
    assert result['status'] == 'completed'
