from copy import deepcopy
import json
from importlib import resources
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from content_planner.storage import Repository


ROOT = Path(__file__).resolve().parents[2]
NOW = '2026-10-31T02:00:00+00:00'
INPUT = {'request_id': 's6', 'topic': '字幕推广', 'budget_units': 14,
         'deadline_at': '2026-10-31T06:00:00+00:00'}
NORMAL = json.loads(resources.files('content_planner').joinpath('data/mock-scenario.json').read_text(encoding='utf-8'))


def action(name, call_id, **arguments):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': call_id, 'type': 'function', 'function': {'name': name,
         'arguments': json.dumps({'rationale': '显式续跑动作', **arguments}, ensure_ascii=False)}}]}


def scenario(tmp_path, name, decisions, responses=()):
    path = tmp_path / (name + '.json')
    path.write_text(json.dumps({'now': NOW, 'decisions': decisions, 'responses': list(responses)}, ensure_ascii=False), encoding='utf-8')
    return path


def cli(tmp_path, *args):
    return subprocess.run([sys.executable, '-X', 'utf8', '-m', 'content_planner', *map(str, args)],
                          cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')


def failed_run(tmp_path, *, decisions=None, responses=None):
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(INPUT, ensure_ascii=False), encoding='utf-8')
    decisions = decisions or NORMAL['decisions'][:3] + [action('stop_task', 'stop', reason='tool_failure', message='生成失败')]
    setup = scenario(tmp_path, 'first', decisions, [{'error': 'MODEL_UNAVAILABLE'}] if responses is None else responses)
    process = cli(tmp_path, 'run', '--input', source, '--mock-scenario', setup, '--db', tmp_path / 'runtime.db')
    assert process.returncode == 3, process.stderr
    return json.loads(process.stdout)


def test_new_process_resume_reuses_search_and_keeps_failed_attempt(tmp_path):
    first = failed_run(tmp_path)
    continuation = deepcopy(NORMAL['decisions'][2:])
    continuation[0]['tool_calls'][0]['id'] = 'retry'
    setup = scenario(tmp_path, 'next', continuation, NORMAL['responses'])
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--mock-scenario', setup,
                  '--db', tmp_path / 'runtime.db', '--output-dir', tmp_path / 'resumed')
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['status'] == 'completed' and result['total_units'] == 8
    assert result['usage']['model_requests'] == first['usage']['model_requests'] + 4
    assert [s['attempt'] for s in result['execution_steps'] if s['tool'] == 'generate_script'] == [1, 2]
    assert sum(s['tool'] == 'search_materials' for s in result['execution_steps']) == 1
    assert result['tool_results'][:4] == first['tool_results']
    with Repository(tmp_path / 'runtime.db') as repo:
        assert repo.get_plan('s6')['saved_plan'] == result['saved_plan']


@pytest.mark.parametrize('changed', ['materials', 'pricing', 'aliases', 'model'])
def test_resume_rejects_manifest_changes_without_modifying_history(tmp_path, changed):
    from content_planner.catalog import load_catalog
    from content_planner.model import FakeModelClient
    from content_planner.service import resume_task, show_task

    first = failed_run(tmp_path)
    model = FakeModelClient(NORMAL['responses'], decisions=NORMAL['decisions'])
    if changed == 'model':
        model.model_id = 'deepseek-v4-pro'
        catalog = load_catalog()
    else:
        directory = tmp_path / 'data'
        directory.mkdir()
        for name in ('materials', 'pricing', 'aliases'):
            raw = resources.files('content_planner').joinpath('data/' + name + '.json').read_bytes()
            (directory / (name + '.json')).write_bytes(raw + (b'\n' if name == changed else b''))
        catalog = load_catalog(directory)
    with Repository(tmp_path / 'runtime.db') as repo:
        before = repo.events('s6')
    result = resume_task('s6', database=tmp_path / 'runtime.db', model=model, catalog=catalog)
    assert result['reason'] == 'MANIFEST_MISMATCH' and result['status'] == 'incomplete'
    assert model.requests == model.decision_requests == []
    assert show_task('s6', database=tmp_path / 'runtime.db')['tool_results'] == first['tool_results']
    with Repository(tmp_path / 'runtime.db') as repo:
        assert repo.events('s6') == before


@pytest.mark.parametrize('stop', ['no_material', 'constraints_unsatisfied', 'MODEL_STOPPED', 'MODEL_PROTOCOL_ERROR', 'invalid_script'])
def test_nonrecoverable_stop_is_read_only_and_does_not_request_model(tmp_path, stop):
    from content_planner.model import FakeModelClient
    from content_planner.service import resume_task

    responses = NORMAL['responses']
    if stop == 'no_material':
        decisions = [action('search_materials', 'empty', query='不存在的素材', top_k=1),
                     action('stop_task', 'stop', reason='no_material', message='无素材')]
    elif stop == 'constraints_unsatisfied':
        decisions = NORMAL['decisions'][:4] + [action('stop_task', 'stop', reason='constraints_unsatisfied', message='已评估报价不可行')]
        request = {**INPUT, 'budget_units': 5}
    elif stop == 'MODEL_STOPPED':
        decisions = [{'role': 'assistant', 'content': '停止'}]
    elif stop == 'MODEL_PROTOCOL_ERROR':
        decisions = [action('unknown', 'bad-1'), action('unknown', 'bad-2')]
    else:
        decisions = NORMAL['decisions'][:3] + [action('stop_task', 'stop', reason='tool_failure', message='脚本来源非法')]
        responses = [NORMAL['responses'][0].replace('M01', 'M02')]
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(request if stop == 'constraints_unsatisfied' else INPUT), encoding='utf-8')
    setup = scenario(tmp_path, 'first', decisions, responses)
    assert cli(tmp_path, 'run', '--input', source, '--mock-scenario', setup, '--db', tmp_path / 'runtime.db').returncode == 3
    with Repository(tmp_path / 'runtime.db') as repo:
        before = repo.events('s6')
    model = FakeModelClient([], decisions=[NORMAL['decisions'][0]])
    result = resume_task('s6', database=tmp_path / 'runtime.db', model=model)
    assert result['reason'] == 'RESUME_NOT_ALLOWED'
    assert model.requests == model.decision_requests == []
    with Repository(tmp_path / 'runtime.db') as repo:
        assert repo.events('s6') == before


CRASH_PROCESS = '''
import json,os,sys
from content_planner import service
from content_planner.storage import Repository
where=sys.argv[1]
class CrashRepository(Repository):
    def record_event(self,request_id,operation_id,phase,**fields):
        result=super().record_event(request_id,operation_id,phase,**fields)
        if where=='save_failure' and phase=='failed' and fields['name']=='save_plan': os._exit(91)
        if phase=='succeeded' and ((where=='planner' and fields['name']=='planner')
            or (where=='script' and fields['name']=='script')
            or (where=='tool' and fields['name']=='generate_script')):
            if 'checkpoint_ready' in sys.argv[5:]:
                import sqlite3,time
                for attempt in range(500):
                    with sqlite3.connect(sys.argv[3]) as connection:
                        rows=connection.execute('SELECT checkpoint_id,metadata FROM checkpoints').fetchall()
                        checkpoint=next((row[0] for row in rows if json.loads(row[1])['step']==2),None)
                        if checkpoint and connection.execute('SELECT count(*) FROM writes WHERE checkpoint_id=?',(checkpoint,)).fetchone()[0]:
                            break
                    time.sleep(0.01)
                else:
                    raise AssertionError('Checkpoint fixture did not flush')
            os._exit(91)
        return result
    def save_plan(self,*args,**kwargs):
        if where=='unknown_save': os._exit(91)
        result=super().save_plan(*args,**kwargs)
        if where=='save': os._exit(91)
        return result
service.Repository=CrashRepository
if where.startswith('unknown_'):
    from datetime import datetime
    from content_planner.model import FakeModelClient
    setup=json.load(open(sys.argv[4],encoding='utf-8'))
    class Clock:
        def now(self): return datetime.fromisoformat(setup['now'])
    class CrashModel(FakeModelClient):
        def decide(self,context):
            response=super().decide(context)
            if where=='unknown_planner': os._exit(91)
            return response
        def generate_script(self,context):
            response=super().generate_script(context)
            if where=='unknown_script': os._exit(91)
            return response
    model=CrashModel(setup['responses'],decisions=setup['decisions'])
    service.run_task(json.load(open(sys.argv[2],encoding='utf-8')),database=sys.argv[3],model=model,clock=Clock())
else:
    if len(sys.argv)>5 and sys.argv[5]=='resume':
        service.resume_task('s6',database=sys.argv[3],mock_scenario=sys.argv[4])
    else:
        service.run_task(json.load(open(sys.argv[2],encoding='utf-8')),database=sys.argv[3],mock_scenario=sys.argv[4])
'''


def crash_run(tmp_path, where, *, resume=False, checkpoint_ready=False):
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(INPUT, ensure_ascii=False), encoding='utf-8')
    setup = scenario(tmp_path, 'crash', NORMAL['decisions'], NORMAL['responses'])
    process = subprocess.run([sys.executable, '-X', 'utf8', '-c', CRASH_PROCESS, where, str(source),
                              str(tmp_path / 'runtime.db'), str(setup), *(['resume'] if resume else []),
                              *(['checkpoint_ready'] if checkpoint_ready else [])], cwd=tmp_path, capture_output=True)
    assert process.returncode == 91, process.stderr.decode('utf-8')


@pytest.mark.parametrize('where', ['planner', 'script', 'tool', 'save'])
def test_new_process_recovers_committed_response_or_artifact_without_repeating_it(tmp_path, where):
    crash_run(tmp_path, where)
    start = 1 if where == 'planner' else 3
    # A persisted script response or artifact must not need a second script response.
    continuation = NORMAL['decisions'][start:]
    setup = scenario(tmp_path, 'resume', continuation, NORMAL['responses'] if where == 'planner' else [])
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--db', tmp_path / 'runtime.db',
                  '--mock-scenario', setup, '--output-dir', tmp_path / 'resumed')
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['status'] == 'completed' and result['usage']['model_requests'] == 6
    with sqlite3.connect(tmp_path / 'runtime.db') as connection:
        assert connection.execute('SELECT count(*) FROM plans').fetchone()[0] == 1
    with Repository(tmp_path / 'runtime.db') as repo:
        events = repo.events('s6')
    assert sum(e['name'] == 'script' and e['phase'] == 'started' for e in events) == 1
    assert sum(e['name'] == 'save_plan' and e['phase'] == 'started' for e in events) == 1
    assert len({r['tool_call_id'] for r in result['tool_results']}) == len(result['tool_results'])


@pytest.mark.parametrize('where', ['unknown_planner', 'unknown_script'])
def test_unknown_external_result_is_interrupted_and_new_attempt_consumes_quota(tmp_path, where):
    crash_run(tmp_path, where)
    setup = scenario(tmp_path, 'resume', NORMAL['decisions'] if where == 'unknown_planner' else NORMAL['decisions'][3:],
                     NORMAL['responses'])
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--db', tmp_path / 'runtime.db', '--mock-scenario', setup)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['usage']['model_requests'] == 7 and result['limits']['remaining_model_requests'] == 25
    with Repository(tmp_path / 'runtime.db') as repo:
        events = repo.events('s6')
    assert sum(e['kind'] == 'model' and e['phase'] == 'interrupted' for e in events) == 1
    assert any(e['kind'] == 'model' and e['phase'] == 'started' and e['args'].get('recovery_of') for e in events)
    if where == 'unknown_script':
        attempts = [s for s in result['execution_steps'] if s['tool'] == 'generate_script']
        assert [s['status'] for s in attempts] == ['interrupted', 'succeeded']
        assert attempts[0]['result_index'] is None
        assert [s['tool_call_id'] for s in attempts] == ['generate', 'generate']


@pytest.mark.parametrize('kind,limit,reason', [('model', 32, 'MODEL_CALL_LIMIT_REACHED'),
                                           ('tool', 24, 'ACTION_LIMIT_REACHED')])
def test_resume_cannot_reset_exhausted_cumulative_quota(tmp_path, kind, limit, reason):
    from content_planner.model import FakeModelClient
    from content_planner.service import resume_task, show_task

    failed_run(tmp_path)
    with Repository(tmp_path / 'runtime.db') as repo:
        events = repo.events('s6')
        used = sum(e['phase'] == 'started' and (e['kind'] == 'model' if kind == 'model'
                    else e['kind'] in {'tool', 'control'}) for e in events)
        for number in range(limit - used):
            repo.record_event('s6', f'fixture-{kind}:{number}', 'started', kind=kind, name='fixture_setup',
                              args={'origin': 'fixture_setup'}, rationale='', created_at=NOW)
        before = repo.events('s6')
    original = show_task('s6', database=tmp_path / 'runtime.db')
    model = FakeModelClient([], decisions=NORMAL['decisions'])
    result = resume_task('s6', database=tmp_path / 'runtime.db', model=model)
    assert result['reason'] == reason and model.decision_requests == []
    assert show_task('s6', database=tmp_path / 'runtime.db') == original
    with Repository(tmp_path / 'runtime.db') as repo:
        assert repo.events('s6') == before


def test_committed_plan_wins_even_when_checkpoint_cannot_be_read(tmp_path):
    crash_run(tmp_path, 'save')
    with sqlite3.connect(tmp_path / 'runtime.db') as connection:
        connection.execute('ALTER TABLE checkpoints RENAME TO broken_checkpoint_backup')
        connection.execute('CREATE TABLE checkpoints (broken TEXT)')
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--db', tmp_path / 'runtime.db')
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['status'] == 'completed' and result['saved_plan']
    assert any(w['code'] == 'CHECKPOINT_UNAVAILABLE' for w in result['warnings'])


def test_missing_checkpoint_is_refused_without_creating_a_new_execution(tmp_path):
    from datetime import datetime
    from content_planner.catalog import load_catalog
    from content_planner.contracts import Request
    from content_planner.model import FakeModelClient
    from content_planner.service import resume_task
    from content_planner.tools import manifest_for

    class Clock:
        def now(self): return datetime.fromisoformat(NOW)

    with Repository(tmp_path / 'runtime.db') as repo:
        repo.register(Request.model_validate(INPUT), backend='mock', model='mock',
                      manifest=manifest_for(load_catalog(), 'mock'), clock=Clock())
    model = FakeModelClient([], decisions=NORMAL['decisions'])
    result = resume_task('s6', database=tmp_path / 'runtime.db', model=model)
    assert result['reason'] == 'CHECKPOINT_NOT_FOUND' and model.decision_requests == []


@pytest.mark.parametrize('change', ['mode', 'brief'])
def test_resume_reuses_only_valid_script_and_rejects_stale_estimate(tmp_path, change):
    import hashlib

    first = failed_run(tmp_path, decisions=NORMAL['decisions'][:4] + [{'error': 'MODEL_UNAVAILABLE'}],
                       responses=NORMAL['responses'])
    assert first['reason'] == 'MODEL_UNAVAILABLE'
    old_brief = json.loads(NORMAL['decisions'][1]['tool_calls'][0]['function']['arguments'])['creative_brief']
    decisions = [action('revise_plan', 'new-revision', material_id='M01',
                        creative_brief=old_brief if change == 'mode' else '新的字幕创意',
                        production_mode='premium' if change == 'mode' else 'basic'),
                 action('generate_script', 'generate-new', plan_revision=2),
                 action('estimate_cost', 'estimate-new', plan_revision=2),
                 action('save_plan', 'stale', plan_revision=2,
                        estimate_id='estimate_' + hashlib.sha256(b'estimate').hexdigest()),
                 action('save_plan', 'save-new', plan_revision=2,
                        estimate_id='estimate_' + hashlib.sha256(b'estimate-new').hexdigest())]
    setup = scenario(tmp_path, 'resume', decisions, [] if change == 'mode' else NORMAL['responses'])
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--db', tmp_path / 'runtime.db', '--mock-scenario', setup)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['current_revision'] == 2 and result['tool_results'][-2]['error']['code'] == 'STALE_ESTIMATE'
    assert result['tool_results'][-4]['reused'] == (change == 'mode')
    with Repository(tmp_path / 'runtime.db') as repo:
        events = repo.events('s6')
    assert sum(e['name'] == 'script' and e['phase'] == 'started' for e in events) == (1 if change == 'mode' else 2)


def test_resume_does_not_reset_two_failed_attempts_for_same_script(tmp_path):
    first = failed_run(tmp_path, decisions=NORMAL['decisions'][:3] + [action('generate_script', 'retry', plan_revision=1),
                      action('stop_task', 'stop', reason='tool_failure', message='两次失败')],
                      responses=[{'error': 'MODEL_UNAVAILABLE'}] * 2)
    setup = scenario(tmp_path, 'resume', [action('generate_script', 'third', plan_revision=1),
                     action('stop_task', 'stop-again', reason='tool_failure', message='重试次数耗尽')], NORMAL['responses'])
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--db', tmp_path / 'runtime.db', '--mock-scenario', setup)
    assert process.returncode == 3, process.stderr
    result = json.loads(process.stdout)
    assert result['tool_results'][-2]['error']['code'] == 'TOOL_RETRY_LIMIT_REACHED'
    assert result['usage']['model_requests'] == first['usage']['model_requests'] + 2
    assert result['saved_plan'] is None


@pytest.mark.parametrize('recovery', [False, True])
def test_persisted_save_failure_replay_restores_error_without_reexecuting_save(tmp_path, recovery):
    if recovery:
        crash_run(tmp_path, 'unknown_save')
    with Repository(tmp_path / 'runtime.db'):
        pass
    with sqlite3.connect(tmp_path / 'runtime.db') as connection:
        connection.execute("CREATE TRIGGER fail_save BEFORE INSERT ON plans BEGIN SELECT RAISE(ABORT,'test fault'); END")
    crash_run(tmp_path, 'save_failure', resume=recovery)
    with Repository(tmp_path / 'runtime.db') as repo:
        before = sum(e['name'] == 'save_plan' and e['phase'] == 'started' for e in repo.events('s6'))
    setup = scenario(tmp_path, 'resume', [action('stop_task', 'stop-failed', reason='tool_failure', message='确认保存失败')])
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--db', tmp_path / 'runtime.db', '--mock-scenario', setup)
    assert process.returncode == 3, process.stderr
    result = json.loads(process.stdout)
    assert result['reason'] == 'tool_failure'
    assert result['tool_results'][-2]['error']['code'] == 'SAVE_FAILED'
    with Repository(tmp_path / 'runtime.db') as repo:
        events = repo.events('s6')
    assert sum(e['name'] == 'save_plan' and e['phase'] == 'started' for e in events) == before


def test_external_call_id_cannot_collide_with_internal_script_operation(tmp_path):
    import hashlib

    source = tmp_path / 'input.json'
    source.write_text(json.dumps(INPUT), encoding='utf-8')
    decisions = deepcopy(NORMAL['decisions'])
    decisions[3]['tool_calls'][0]['id'] = 'generate:script'
    decisions[4] = action('save_plan', 'save', plan_revision=1,
                          estimate_id='estimate_' + hashlib.sha256(b'generate:script').hexdigest())
    setup = scenario(tmp_path, 'collision', decisions, NORMAL['responses'])
    process = cli(tmp_path, 'run', '--input', source, '--db', tmp_path / 'runtime.db', '--mock-scenario', setup)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['status'] == 'completed' and result['tool_results'][3]['tool_call_id'] == 'generate:script'
    assert result['usage']['model_requests'] == 6 and result['usage']['action_calls'] == 5


def test_resume_preserves_four_revision_limit(tmp_path):
    decisions = [NORMAL['decisions'][0]] + [action('revise_plan', f'revise-{n}', material_id='M01',
                 creative_brief=f'字幕创意{n}', production_mode='basic') for n in range(4)]
    failed_run(tmp_path, decisions=decisions + [{'error': 'MODEL_UNAVAILABLE'}], responses=[])
    setup = scenario(tmp_path, 'resume', [action('revise_plan', 'fifth', material_id='M01',
                      creative_brief='第五版', production_mode='basic')])
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--db', tmp_path / 'runtime.db', '--mock-scenario', setup)
    assert process.returncode == 3, process.stderr
    result = json.loads(process.stdout)
    assert result['reason'] == 'REVISION_LIMIT_REACHED' and result['current_revision'] == 4


def test_resume_applies_persisted_pending_writes_when_next_is_empty(tmp_path):
    from langgraph.checkpoint.sqlite import SqliteSaver

    crash_run(tmp_path, 'tool', checkpoint_ready=True)
    database = tmp_path / 'runtime.db'
    with SqliteSaver.from_conn_string(str(database)) as saver:
        saved = next(item for item in saver.list({'configurable': {'thread_id': 's6'}})
                     if item.metadata['step'] == 2)
        assert saved.pending_writes
        checkpoint_id = saved.config['configurable']['checkpoint_id']
    # Keep a real older checkpoint plus its real completed node writes. This pins the crash window.
    with sqlite3.connect(database) as connection:
        connection.execute('DELETE FROM checkpoints WHERE thread_id=? AND checkpoint_id<>?', ('s6', checkpoint_id))
    setup = scenario(tmp_path, 'resume', NORMAL['decisions'][3:])
    process = cli(tmp_path, 'resume', '--request-id', 's6', '--db', database, '--mock-scenario', setup)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['usage']['model_requests'] == 6 and result['status'] == 'completed'
