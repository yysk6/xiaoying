from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from content_planner.catalog import load_catalog
from content_planner.contracts import Request
from content_planner.domain import Fault
from content_planner.model import FakeModelClient
from content_planner.storage import Repository
from content_planner.tools import LocalTools


class FixedClock:
    value = datetime(2026, 10, 30, 4, tzinfo=timezone.utc)

    def now(self):
        return self.value


@pytest.fixture
def task(tmp_path):
    path = tmp_path / 'runtime.db'
    repo = Repository(path)
    clock = FixedClock()
    request = Request(request_id='save-s3', topic='字幕推广', budget_units=10,
                      deadline_at='2026-10-30T16:00:00+08:00')
    draft = json.dumps({'title': '字幕演示', 'hook': '试试字幕', 'body': '自动生成的字幕文本可以编辑。',
                        'cta': '体验字幕编辑', 'source_ids': ['M01']})
    tools = LocalTools(request, load_catalog(), FakeModelClient([draft]), clock, repository=repo)
    assert tools.search_materials('search', {'query': '字幕', 'top_k': 1, 'rationale': '检索'})['ok']
    assert tools.revise_plan('revise', {'material_id': 'M01', 'creative_brief': '演示编辑',
                                      'production_mode': 'basic', 'rationale': '建立候选'})['ok']
    assert tools.generate_script('generate', {'plan_revision': 1, 'rationale': '生成'})['ok']
    estimate = tools.estimate_cost('estimate', {'plan_revision': 1, 'rationale': '估算'})['data']
    yield tools, repo, path, clock, estimate
    repo.close()


def save(task, call_id='save-1', **changes):
    tools, _, _, _, estimate = task
    return tools.save_plan(call_id, {'plan_revision': 1, 'estimate_id': estimate['estimate_id'],
                                     'rationale': '保存当前可行方案', **changes})


def test_save_commits_plan_and_success_event_before_marking_completed(task):
    tools, repo, path, _, _ = task
    result = save(task)
    assert result['ok'] and not result['reused']
    assert tools.snapshot()['status'] == 'completed'
    data = result['data']
    assert repo.get_plan('save-s3') == data
    assert data['saved_plan']['total_units'] == 8
    assert data['saved_plan']['estimated_finish_at'] == '2026-10-30T05:30:00+00:00'
    steps = data['saved_plan']['task_plan']
    assert [step['status'] for step in steps] == ['planned'] * 4
    assert [step['depends_on'] for step in steps] == [[], ['material_prepare'], ['script_finalize'], ['video_edit']]
    common = json.loads((Path(__file__).resolve().parents[2] / 'contracts/common.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator({'$ref': '#/$defs/ToolResult', '$defs': common['$defs']},
                        format_checker=FormatChecker()).validate(result)
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM plans').fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM events WHERE phase='succeeded'").fetchone()[0] == 1
    success = repo.events('save-s3')[-1]
    assert success['result'] == result
    assert success['state_patch'] == {'status': 'completed', 'saved_plan_id': data['plan_id']}


def test_success_event_write_failure_rolls_back_plan_and_retains_failure(task):
    tools, repo, path, _, _ = task
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER fail_success BEFORE INSERT ON events
            WHEN NEW.phase='succeeded' BEGIN SELECT RAISE(ABORT,'injected commit failure'); END""")
    result = save(task)
    assert not result['ok'] and result['error']['code'] == 'SAVE_FAILED'
    assert result['error']['retryable'] and tools.snapshot()['status'] == 'running'
    assert repo.get_plan('save-s3') is None
    assert [event['phase'] for event in repo.events('save-s3')] == ['started', 'failed']
    assert tools.snapshot()['script_artifacts'] and tools.snapshot()['estimate_history']
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM plans').fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM events WHERE phase='succeeded'").fetchone()[0] == 0
        connection.execute('DROP TRIGGER fail_success')
    assert save(task, call_id='save-retry')['ok']


@pytest.mark.parametrize('change,expected', [('estimate', 'STALE_ESTIMATE'), ('revision', 'STALE_REVISION'),
                                           ('deadline', 'CONSTRAINT_VIOLATION'),
                                           ('premium', 'CONSTRAINT_VIOLATION')])
def test_save_rejects_stale_or_infeasible_inputs_without_a_plan(task, change, expected):
    tools, repo, _, clock, _ = task
    arguments = {}
    if change == 'estimate':
        tools.estimate_cost('estimate-new', {'plan_revision': 1, 'rationale': '重新估算'})
    elif change == 'revision':
        tools.revise_plan('revise-new', {'material_id': 'M01', 'creative_brief': '演示编辑',
                                       'production_mode': 'premium', 'rationale': '换档位'})
    elif change == 'deadline':
        clock.value += timedelta(hours=3)
    else:
        tools.revise_plan('revise-new', {'material_id': 'M01', 'creative_brief': '演示编辑',
                                       'production_mode': 'premium', 'rationale': '换档位'})
        arguments['plan_revision'] = 2
        arguments['estimate_id'] = tools.estimate_cost('premium-estimate', {'plan_revision': 2, 'rationale': '估算'})['data']['estimate_id']
    result = save(task, **arguments)
    assert not result['ok'] and result['error']['code'] == expected
    if change == 'deadline':
        assert result['error']['details']['deadline_gap_minutes'] == 30
    assert tools.snapshot()['status'] == 'running'
    assert repo.get_plan('save-s3') is None
    assert repo.events('save-s3')[-1]['phase'] == 'rejected'


def test_same_content_reuses_committed_plan_even_after_deadline_and_new_call_id(task):
    tools, repo, path, clock, _ = task
    first = save(task)
    clock.value += timedelta(days=1)
    second = save(task, call_id='save-again', rationale='读取已提交内容')
    assert second['ok'] and second['reused'] and second['data'] == first['data']
    assert len(repo.events('save-s3')) == 4
    with Repository(path) as reopened:
        assert reopened.get_plan('save-s3') == first['data']
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM plans').fetchone()[0] == 1


def test_successful_operation_replay_restores_original_result_without_duplicate_events(task):
    tools, repo, _, _, _ = task
    first = save(task)
    # A committed operation is authoritative even if its in-memory checkpoint was lost.
    request = Request.model_validate(tools.snapshot()['request'])
    recovered = LocalTools(request, load_catalog(), FakeModelClient([]), FixedClock(), repository=repo)
    result = recovered.save_plan('save-1', {'plan_revision': 1, 'estimate_id': task[4]['estimate_id'],
                                          'rationale': '保存当前可行方案'})
    assert result['ok'] and result['reused'] and result['data'] == first['data']
    assert recovered.snapshot()['status'] == 'completed'
    assert len(repo.events('save-s3')) == 2


def test_committed_task_rejects_mutating_actions(task):
    tools, repo, _, _, _ = task
    original = save(task)['data']
    result = tools.revise_plan('revise-after-save', {'material_id': 'M01', 'creative_brief': '改变内容',
                                                   'production_mode': 'basic', 'rationale': '修改'})
    assert not result['ok'] and result['error']['code'] == 'TASK_ALREADY_COMPLETED'
    assert tools.snapshot()['current_revision'] == 1
    assert repo.get_plan('save-s3') == original


def test_database_unique_constraint_and_content_conflict_preserve_committed_plan(task):
    _, repo, path, _, _ = task
    original = save(task)['data']
    different = json.loads(json.dumps(original['saved_plan']))
    different['content_hash'] = '0' * 64
    different['script']['body'] = '不同草稿'
    with pytest.raises(Fault, match='SAVE_CONFLICT'):
        repo.save_plan(different, 'save-different', {'rationale': '冲突'})
    assert repo.get_plan('save-s3') == original
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('INSERT INTO plans VALUES (?,?,?,?,?)',
                               ('another-id', 'save-s3', '0' * 64, '{}', original['saved_at']))
    with Repository(path) as another_connection:
        data, reused = another_connection.save_plan(original['saved_plan'], 'another-connection',
                                                    {'rationale': '复用'})
        assert reused and data == original


def test_save_requires_candidate_script_and_estimate(task):
    tools, repo, _, clock, _ = task
    request = Request.model_validate(tools.snapshot()['request'])
    empty = LocalTools(request, load_catalog(), FakeModelClient([]), clock, repository=repo)
    arguments = {'plan_revision': 1, 'estimate_id': 'unknown', 'rationale': '尝试保存'}
    assert empty.save_plan('no-candidate', arguments)['error']['code'] == 'PRECONDITION_FAILED'
    empty.search_materials('search-empty', {'query': '字幕', 'top_k': 1, 'rationale': '检索'})
    empty.revise_plan('revise-empty', {'material_id': 'M01', 'creative_brief': '演示编辑',
                                      'production_mode': 'basic', 'rationale': '建立'})
    assert empty.save_plan('no-script', arguments)['error']['code'] == 'PRECONDITION_FAILED'
    assert repo.get_plan('save-s3') is None


@pytest.mark.parametrize('changes', [{'plan_revision': True}, {'estimate_id': ''}, {'rationale': ' '},
                                    {'price': 1}])
def test_save_rejects_invalid_model_arguments(task, changes):
    assert save(task, **changes)['error']['code'] == 'INVALID_ARGUMENT'
    assert task[1].get_plan('save-s3') is None
