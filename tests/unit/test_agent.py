from datetime import datetime, timezone
import hashlib
import json
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
import pytest

from content_planner.catalog import load_catalog
from content_planner.contracts import Request
from content_planner.domain import build_saved_plan
from content_planner.graph import PlanningAgent
from content_planner.model import FakeModelClient, ModelUnavailable
from content_planner.storage import Repository


class FixedClock:
    def now(self):
        return datetime(2026, 10, 30, 4, tzinfo=timezone.utc)


def call(name, call_id, **arguments):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': call_id, 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps({'rationale': '测试显式动作', **arguments}, ensure_ascii=False)}}]}


def revise(mode='basic', call_id='revise', brief='展示字幕编辑'):
    return call('revise_plan', call_id, material_id='M01', creative_brief=brief, production_mode=mode)


def estimate_id(call_id):
    return 'estimate_' + hashlib.sha256(call_id.encode()).hexdigest()


DRAFT = json.dumps({'title': '字幕演示', 'hook': '试试字幕', 'body': '自动生成的字幕文本可以编辑。',
                    'cta': '体验字幕编辑', 'source_ids': ['M01']})
SEARCH = call('search_materials', 'search', query='字幕', top_k=1)
GENERATE = call('generate_script', 'generate', plan_revision=1)


@pytest.fixture
def run_agent(tmp_path):
    path = tmp_path / 'runtime.db'
    with Repository(path) as repo, SqliteSaver.from_conn_string(str(path)) as saver:
        def run(decisions, responses=(), budget=10, recursion_limit=80, prior_model_calls=0, catalog=None):
            model = FakeModelClient(responses, decisions=decisions)
            request = Request(request_id='s4', topic='字幕推广', budget_units=budget,
                              deadline_at='2026-10-30T16:00:00+08:00')
            agent = PlanningAgent(request, catalog or load_catalog(), model, FixedClock(), repo, saver)
            for number in range(prior_model_calls):
                repo.record_event('s4', f'fixture-model:{number}', 'started', kind='model', name='fixture_setup',
                                  args={'origin': 'fixture_setup'}, rationale='', created_at=FixedClock().now().isoformat())
            return agent.run(recursion_limit=recursion_limit), model, repo, path
        yield run


def test_model_observes_premium_quote_then_explicitly_revises_and_saves(run_agent):
    decisions = [SEARCH, revise('premium'), GENERATE, call('estimate_cost', 'premium', plan_revision=1),
                 revise('basic', 'revise-basic'), call('generate_script', 'reuse', plan_revision=2),
                 call('estimate_cost', 'basic', plan_revision=2),
                 call('save_plan', 'save', plan_revision=2, estimate_id=estimate_id('basic'))]
    state, model, repo, path = run_agent(decisions, [DRAFT])
    assert state['status'] == 'completed'
    assert repo.get_plan('s4')['saved_plan']['total_units'] == 8
    assert model.decision_requests[4]['memory']['latest_estimate']['total_units'] == 12
    assert len(model.requests) == 1 and len(model.decision_requests) == 8
    assert state['current_revision'] == 2 and len(state['planner_messages']) == 16
    events = repo.events('s4')
    assert sum(e['kind'] == 'model' and e['phase'] == 'started' for e in events) == 9
    assert sum(e['kind'] in {'tool', 'control'} and e['phase'] == 'started' for e in events) == 8
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM plans').fetchone()[0] == 1


def test_script_failure_is_observed_before_explicit_retry_and_failure_is_retained(run_agent):
    decisions = [SEARCH, revise(), GENERATE, call('generate_script', 'retry', plan_revision=1),
                 call('estimate_cost', 'estimate', plan_revision=1),
                 call('save_plan', 'save', plan_revision=1, estimate_id=estimate_id('estimate'))]
    state, model, repo, _ = run_agent(decisions, [ModelUnavailable('temporary'), DRAFT])
    assert state['status'] == 'completed' and len(model.requests) == 2
    observed = model.decision_requests[3]['memory']['last_observation']
    assert observed['error']['code'] == 'SCRIPT_MODEL_UNAVAILABLE'
    assert state['tool_results'][2] == observed
    assert [e['name'] for e in repo.events('s4') if e['kind'] == 'model' and e['phase'] == 'failed'] == ['script']


@pytest.mark.parametrize('reason', ['no_material', 'constraints_unsatisfied', 'tool_failure'])
def test_stop_requires_real_evidence_and_retains_artifacts(run_agent, reason):
    responses = []
    if reason == 'no_material':
        decisions = [call('search_materials', 'empty', query='无此素材', top_k=1)]
    elif reason == 'constraints_unsatisfied':
        decisions = [SEARCH, revise('premium'), GENERATE, call('estimate_cost', 'estimate', plan_revision=1)]
        responses = [DRAFT]
    else:
        decisions = [SEARCH, revise(), GENERATE]
        responses = [ModelUnavailable('temporary')]
    decisions.append(call('stop_task', 'stop', reason=reason, message='根据已有结果结束'))
    state, _, repo, _ = run_agent(decisions, responses)
    assert state['status'] == 'incomplete' and state['reason'] == reason
    assert repo.get_plan('s4') is None
    assert state['tool_results'][-1]['ok']
    if reason == 'constraints_unsatisfied':
        assert state['tool_results'][-1]['data']['latest_gap']['budget_gap_units'] == 2
        assert state['script_artifacts']


@pytest.mark.parametrize('bad', ['unknown', 'json', 'arguments', 'multiple'])
def test_invalid_decisions_are_paired_without_executing_actions(run_agent, bad):
    decisions = []
    for number in range(2):
        decision = call('search_materials', f'bad-{number}', query='字幕', top_k=1)
        if bad == 'unknown':
            decision['tool_calls'][0]['function']['name'] = 'erase_database'
        elif bad == 'json':
            decision['tool_calls'][0]['function']['arguments'] = 'not json'
        elif bad == 'arguments':
            decision['tool_calls'][0]['function']['arguments'] = '{"query":"字幕","top_k":true,"rationale":"查找"}'
        else:
            decision['tool_calls'].append(call('search_materials', f'extra-{number}', query='裁剪', top_k=1)['tool_calls'][0])
        decisions.append(decision)
    state, model, repo, _ = run_agent(decisions)
    assert state['reason'] == 'MODEL_PROTOCOL_ERROR'
    assert state['seen_material_ids'] == []
    assert not any(e['kind'] in {'tool', 'control'} for e in repo.events('s4'))
    assert len(model.decision_requests) == 2
    messages = model.decision_requests[1]['messages']
    ids = [c['id'] for c in messages[0]['tool_calls']]
    assert [m['tool_call_id'] for m in messages[1:]] == ids


@pytest.mark.parametrize('decision,reason', [({'role': 'assistant', 'content': '已经完成'}, 'MODEL_STOPPED'),
    ({'role': 'assistant', 'tool_calls': [{'type': 'function', 'function': {'name': 'save_plan', 'arguments': '{}'}}]},
     'MODEL_PROTOCOL_ERROR'), (ModelUnavailable('offline'), 'MODEL_UNAVAILABLE')])
def test_unusable_model_response_stops_without_claiming_success(run_agent, decision, reason):
    state, _, repo, _ = run_agent([decision])
    assert state['status'] == 'incomplete' and state['reason'] == reason
    assert repo.get_plan('s4') is None


def test_third_same_key_retry_is_rejected_without_a_third_generation_request(run_agent):
    decisions = [SEARCH, revise(), GENERATE, call('generate_script', 'retry-2', plan_revision=1),
                 call('generate_script', 'retry-3', plan_revision=1),
                 call('stop_task', 'stop', reason='tool_failure', message='生成持续失败')]
    state, model, repo, _ = run_agent(decisions, [ModelUnavailable('one'), ModelUnavailable('two'), DRAFT])
    assert len(model.requests) == 2
    assert state['tool_results'][-2]['error']['code'] == 'TOOL_RETRY_LIMIT_REACHED'
    assert state['reason'] == 'tool_failure' and repo.get_plan('s4') is None


def test_action_limit_counts_repeated_successes_and_stops_at_24(run_agent):
    decisions = [call('search_materials', f'search-{number}', query='字幕', top_k=1) for number in range(26)]
    state, model, repo, _ = run_agent(decisions)
    assert state['reason'] == 'ACTION_LIMIT_REACHED'
    assert len(model.decision_requests) == 24
    assert sum(e['kind'] == 'tool' and e['phase'] == 'started' for e in repo.events('s4')) == 24


def test_model_limit_uses_persisted_started_calls_without_reset(run_agent):
    state, model, repo, _ = run_agent([SEARCH, revise()], prior_model_calls=31)
    assert state['reason'] == 'MODEL_CALL_LIMIT_REACHED' and len(model.decision_requests) == 1
    assert sum(e['kind'] == 'model' and e['phase'] == 'started' for e in repo.events('s4')) == 32


def test_graph_limit_is_reported_without_losing_completed_search(run_agent):
    state, _, repo, _ = run_agent([SEARCH, revise()], recursion_limit=2)
    assert state['reason'] == 'GRAPH_LIMIT_REACHED'
    assert state['seen_material_ids'] == ['M01'] and repo.get_plan('s4') is None


def test_graph_limit_before_dispatch_pairs_pending_call_with_rejection(run_agent):
    state, _, repo, _ = run_agent([SEARCH], recursion_limit=1)
    assert state['reason'] == 'GRAPH_LIMIT_REACHED' and state['pending_call'] is None
    assert len(state['planner_messages']) == 2
    assert state['planner_messages'][1]['tool_call_id'] == 'search'
    assert not any(e['kind'] in {'tool', 'control'} for e in repo.events('s4'))


def test_repeat_run_reads_checkpoint_without_more_model_or_tool_calls(run_agent):
    state, model, repo, path = run_agent([SEARCH, call('stop_task', 'unsupported', reason='no_material', message='无素材'),
                                       {'role': 'assistant', 'content': '结束'}])
    before = repo.events('s4')
    with SqliteSaver.from_conn_string(str(path)) as saver:
        request = Request.model_validate(state['request'])
        another = PlanningAgent(request, load_catalog(), model, FixedClock(), repo, saver)
        assert another.run() == state
    assert repo.events('s4') == before


def test_context_compacts_whole_pairs_but_keeps_full_checkpoint_history(run_agent):
    decisions = [call('search_materials', f'search-{number}', query='字幕', top_k=1) for number in range(23)]
    decisions.append({'role': 'assistant', 'content': '结束'})
    state, model, _, _ = run_agent(decisions)
    context = model.decision_requests[-1]
    assert len(context['messages']) < len(state['planner_messages']) - 1
    assert len(json.dumps(context['messages'], ensure_ascii=False)) <= 12000
    assert context['history_summary'] and context['memory']['request']['budget_units'] == 10
    assert context['memory']['seen_material_ids'] == ['M01']
    assert len(state['planner_messages']) == 47
    for number in range(0, len(context['messages']), 2):
        assert context['messages'][number]['tool_calls'][0]['id'] == context['messages'][number + 1]['tool_call_id']


def test_committed_plan_takes_priority_over_an_older_incomplete_checkpoint(run_agent):
    decisions = [SEARCH, revise(), GENERATE, call('estimate_cost', 'estimate', plan_revision=1),
                 {'role': 'assistant', 'content': '先停止'}]
    state, model, repo, path = run_agent(decisions, [DRAFT])
    request = Request.model_validate(state['request'])
    candidate = state['candidate_history']['1']
    script = state['script_artifacts'][candidate['script_input_hash']]
    quotation = state['estimate_history'][state['current_estimate_id']]
    payload = build_saved_plan(request, candidate, script, state['manifest']['pricing_sha256'], quotation)
    repo.save_plan(payload, 'fixture-commit', {'rationale': 'fixture_setup：提交事实先于checkpoint'})
    before = len(model.decision_requests)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        current = PlanningAgent(request, load_catalog(), model, FixedClock(), repo, saver).run()
    assert current['status'] == 'completed' and current['reason'] is None
    assert current['saved_plan_id'] == payload['plan_id']
    assert len(model.decision_requests) == before


def test_invalid_assistant_content_is_rejected_before_action_execution(run_agent):
    bad = call('search_materials', 'bad-content', query='字幕', top_k=1)
    bad['content'] = {'invalid': 'object'}
    state, _, repo, _ = run_agent([bad])
    assert state['reason'] == 'MODEL_PROTOCOL_ERROR'
    assert not any(e['kind'] in {'tool', 'control'} for e in repo.events('s4'))


def test_provider_reasoning_is_excluded_from_memory_and_persisted_events(run_agent):
    response = call('search_materials', 'empty', query='不存在', top_k=1)
    response['reasoning_content'] = 'PRIVATE_REASONING_MUST_NOT_BE_STORED'
    state, _, repo, _ = run_agent([response, call('stop_task', 'stop', reason='no_material', message='未命中')])
    assert 'PRIVATE_REASONING' not in json.dumps(state)
    assert 'PRIVATE_REASONING' not in json.dumps(repo.events('s4'))


def test_script_call_cannot_exceed_model_quota_after_planner_used_last_slot(run_agent):
    state, model, repo, _ = run_agent([SEARCH, revise(), GENERATE], [DRAFT], prior_model_calls=29)
    assert state['reason'] == 'MODEL_CALL_LIMIT_REACHED' and model.requests == []
    assert sum(e['kind'] == 'model' and e['phase'] == 'started' for e in repo.events('s4')) == 32


def test_fifth_revision_stops_graph_without_creating_a_fifth_candidate(run_agent):
    decisions = [SEARCH] + [revise(call_id=f'revision-{number}', brief=f'创意{number}') for number in range(5)]
    state, _, repo, _ = run_agent(decisions)
    assert state['reason'] == 'REVISION_LIMIT_REACHED' and state['current_revision'] == 4
    assert len(state['candidate_history']) == 4 and repo.get_plan('s4') is None


def test_successful_generation_resolves_failure_and_cannot_justify_tool_failure_stop(run_agent):
    decisions = [SEARCH, revise(), GENERATE, call('generate_script', 'retry', plan_revision=1),
                 call('stop_task', 'unsupported', reason='tool_failure', message='工具坏了'),
                 {'role': 'assistant', 'content': '不保存'}]
    state, _, _, _ = run_agent(decisions, [ModelUnavailable('temporary'), DRAFT])
    assert state['tool_results'][-1]['error']['code'] == 'STOP_REASON_UNSUPPORTED'
    assert state['reason'] == 'MODEL_STOPPED'


def test_new_brief_removes_inapplicable_failure_from_current_memory(run_agent):
    decisions = [SEARCH, revise(), GENERATE, revise(call_id='new-brief', brief='新的编辑创意'),
                 {'role': 'assistant', 'content': '结束'}]
    state, model, _, _ = run_agent(decisions, [ModelUnavailable('temporary')])
    assert model.decision_requests[-1]['memory']['unresolved_failures'] == {}
    assert state['tool_results'][2]['error']['code'] == 'SCRIPT_MODEL_UNAVAILABLE'


def test_latest_estimate_rejection_is_observed_before_model_chooses_current_id(run_agent):
    decisions = [SEARCH, revise(), GENERATE, call('estimate_cost', 'old', plan_revision=1),
                 call('estimate_cost', 'new', plan_revision=1),
                 call('save_plan', 'stale', plan_revision=1, estimate_id=estimate_id('old')),
                 call('save_plan', 'current', plan_revision=1, estimate_id=estimate_id('new'))]
    state, model, repo, _ = run_agent(decisions, [DRAFT])
    assert state['status'] == 'completed' and repo.get_plan('s4')
    assert model.decision_requests[-1]['memory']['last_observation']['error']['code'] == 'STALE_ESTIMATE'


def test_whole_message_group_feedback_matches_original_ids_for_all_results(run_agent):
    from pathlib import Path
    from jsonschema import Draft202012Validator

    bad = call('unknown', 'bad')
    state, _, _, _ = run_agent([bad, call('search_materials', 'empty', query='无素材', top_k=1),
                               call('stop_task', 'stop', reason='no_material', message='未命中')])
    common = json.loads((Path(__file__).resolve().parents[2] / 'contracts/common.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator({'$ref': '#/$defs/ToolResult', '$defs': common['$defs']})
    for result in state['tool_results']:
        validator.validate(result)
    for index in range(0, len(state['planner_messages']), 2):
        pair = state['planner_messages'][index:index + 2]
        assert pair[0]['tool_calls'][0]['id'] == pair[1]['tool_call_id']


def test_required_context_overflow_stops_before_another_model_request(run_agent, tmp_path):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / 'contracts/fixtures'
    data = tmp_path / 'large-data'
    data.mkdir()
    for name in ('materials.json', 'pricing.json', 'aliases.json'):
        (data / name).write_bytes((root / name).read_bytes())
    materials = json.loads((data / 'materials.json').read_text(encoding='utf-8'))
    materials['materials'][0]['facts'] = ['字' * 300] * 100
    (data / 'materials.json').write_text(json.dumps(materials, ensure_ascii=False), encoding='utf-8')
    state, model, _, _ = run_agent([SEARCH, revise()], catalog=load_catalog(data))
    assert state['reason'] == 'CONTEXT_LIMIT_REACHED' and len(model.decision_requests) == 1
    assert state['seen_material_ids'] == ['M01']
