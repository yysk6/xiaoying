from datetime import datetime, timedelta, timezone
import json

import pytest

from content_planner.catalog import load_catalog
from content_planner.contracts import Request
from content_planner.model import FakeModelClient


class FixedClock:
    def __init__(self):
        self.value = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)

    def now(self):
        return self.value


@pytest.fixture
def tools():
    from content_planner.tools import LocalTools

    request = Request(request_id='s2', topic='字幕推广', budget_units=10,
                      deadline_at='2026-10-29T13:00:00+08:00')
    return LocalTools(request, load_catalog(), FakeModelClient([]), FixedClock())


def search(tools, query='字幕', call_id='search-1'):
    return tools.search_materials(call_id, {'query': query, 'top_k': 5, 'rationale': '查找素材'})


def test_empty_then_rewritten_search_accumulates_observed_materials(tools):
    empty = search(tools, '不存在的功能')
    assert empty['ok'] and empty['data']['materials'] == []
    assert tools.snapshot()['seen_material_ids'] == []
    assert [item['material_id'] for item in search(tools, 'caption', 'search-2')['data']['materials']] == ['M01']
    search(tools, '裁剪', 'search-3')
    assert tools.snapshot()['seen_material_ids'] == ['M01', 'M02']
    assert len(tools.snapshot()['tool_results']) == 3


@pytest.mark.parametrize('arguments', [
    {'query': '字幕', 'top_k': True, 'rationale': '查找'},
    {'query': '字幕', 'top_k': 0, 'rationale': '查找'},
    {'query': '字幕', 'top_k': 6, 'rationale': '查找'},
    {'query': '字幕', 'top_k': 1.0, 'rationale': '查找'},
    {'query': '字幕', 'top_k': '1', 'rationale': '查找'},
    {'query': ' ', 'top_k': 1, 'rationale': '查找'},
    {'query': '字幕', 'top_k': 1, 'rationale': ''},
    {'query': '字幕', 'top_k': 1},
    {'query': '字幕', 'top_k': 1, 'rationale': '查找', 'budget_units': 100},
])
def test_search_rejects_invalid_arguments_without_observing_materials(tools, arguments):
    result = tools.search_materials('invalid', arguments)
    assert not result['ok'] and result['error']['code'] == 'INVALID_ARGUMENT'
    assert result['data'] is None and not result['error']['retryable']
    assert tools.snapshot()['seen_material_ids'] == []


def revise(tools, material_id='M01', brief='演示字幕编辑', mode='premium', call_id='revise-1'):
    return tools.revise_plan(call_id, {'material_id': material_id, 'creative_brief': brief,
                                      'production_mode': mode, 'rationale': '建立候选'})


def test_revision_requires_observed_material_and_reuses_same_candidate(tools):
    unknown = revise(tools, material_id='M99')
    assert unknown['error']['code'] == 'MATERIAL_NOT_FOUND'
    unseen = revise(tools)
    assert unseen['error']['code'] == 'MATERIAL_NOT_OBSERVED'
    search(tools)
    first = revise(tools)
    assert first['ok'] and first['data']['revision'] == 1 and not first['reused']
    same = revise(tools, brief=' 演示字幕编辑 ', call_id='revise-2')
    assert same['reused'] and same['data']['revision'] == 1
    assert first['data']['candidate_hash'] == same['data']['candidate_hash']
    assert len(tools.snapshot()['candidate_history']) == 1


def test_fifth_candidate_is_rejected_without_changing_fourth(tools):
    search(tools)
    for number in range(4):
        assert revise(tools, brief=f'方案{number}', call_id=f'revision-{number}')['ok']
    rejected = revise(tools, brief='第五版', call_id='revision-5')
    assert not rejected['ok'] and rejected['error']['code'] == 'REVISION_LIMIT_REACHED'
    state = tools.snapshot()
    assert state['current_revision'] == 4 and len(state['candidate_history']) == 4
    assert state['status'] == 'incomplete' and state['reason'] == 'REVISION_LIMIT_REACHED'


def draft_json(material_id='M01', body='自动生成的字幕文本可以编辑。'):
    return json.dumps({'title': '字幕演示', 'hook': '试试字幕', 'body': body,
                       'cta': '体验字幕编辑', 'source_ids': [material_id]}, ensure_ascii=False)


def make_script_tools(responses, clock=None):
    from content_planner.model import FakeModelClient
    from content_planner.tools import LocalTools

    client = FakeModelClient(responses)
    clock = clock if clock is not None else FixedClock()
    req = Request(request_id='script-s2', topic='字幕推广', budget_units=10,
                  deadline_at='2026-10-29T13:00:00+08:00')
    return LocalTools(req, load_catalog(), client, clock), client, clock


def generate(tools, revision=1, call_id='generate-1'):
    return tools.generate_script(call_id, {'plan_revision': revision, 'rationale': '生成当前草稿'})


def test_script_generation_produces_program_owned_id_and_fact_context():
    tools, client, _ = make_script_tools([draft_json()])
    search(tools)
    candidate = revise(tools)['data']
    result = generate(tools)
    assert result['ok'] and not result['reused']
    assert result['data']['script_id'] == 'script_' + candidate['script_input_hash']
    assert result['data']['source_ids'] == ['M01']
    context = client.requests[0]
    assert context['material']['facts'] == ['影芽剪辑支持自动生成字幕。', '自动生成的字幕文本可以编辑。']
    assert context['creative_brief'] == '演示字幕编辑'
    assert set(context) == {'topic', 'material', 'creative_brief', 'audience', 'platform', 'output_schema'}
    assert len(client.requests) == 1


def test_matching_script_is_reused_without_another_model_request():
    tools, client, _ = make_script_tools([draft_json()])
    search(tools)
    revise(tools)
    first = generate(tools)
    second = generate(tools, call_id='generate-2')
    assert second['ok'] and second['reused']
    assert second['data'] == first['data']
    assert len(client.requests) == 1


def test_generation_failure_is_observed_without_automatic_retry_or_lost_search():
    from content_planner.model import ModelUnavailable

    tools, client, _ = make_script_tools([ModelUnavailable('temporary'), draft_json()])
    search_result = search(tools)
    revise(tools)
    failed = generate(tools)
    assert not failed['ok'] and failed['error']['code'] == 'SCRIPT_MODEL_UNAVAILABLE'
    assert failed['error']['retryable'] and failed['data'] is None
    assert len(client.requests) == 1
    state = tools.snapshot()
    assert state['seen_material_ids'] == ['M01'] and state['script_artifacts'] == {}
    assert state['tool_results'][0] == search_result and state['last_observation'] == failed
    assert generate(tools, call_id='generate-retry')['ok']
    assert len(client.requests) == 2
    assert tools.snapshot()['tool_results'][2] == failed


def estimate(tools, revision=1, call_id='estimate-1'):
    return tools.estimate_cost(call_id, {'plan_revision': revision, 'rationale': '核对约束'})


def test_estimation_reports_premium_gap_and_basic_alternative_without_selecting_it():
    tools, _, _ = make_script_tools([draft_json()])
    search(tools)
    revise(tools)
    generate(tools)
    result = estimate(tools)
    assert result['ok'] and not result['reused']
    value = result['data']
    assert (value['total_units'], value['total_minutes'], value['budget_gap_units']) == (12, 135, 2)
    assert value['feasible'] is False
    assert [(row['production_mode'], row['total_units'], row['total_minutes'], row['feasible'])
            for row in value['alternatives']] == [('basic', 8, 90, True)]
    state = tools.snapshot()
    assert state['candidate_history']['1']['production_mode'] == 'premium'
    assert state['current_estimate_id'] == value['estimate_id']


def test_estimate_and_alternative_share_one_instant_and_next_estimate_refreshes_it():
    class AdvancingClock(FixedClock):
        def now(self):
            result = self.value
            self.value += timedelta(seconds=1)
            return result

    tools, _, _ = make_script_tools([draft_json()], AdvancingClock())
    search(tools)
    revise(tools)
    generate(tools)
    first = estimate(tools)['data']
    quoted = datetime.fromisoformat(first['quoted_at'])
    assert first['alternatives'][0]['estimated_finish_at'] == (quoted + timedelta(minutes=90)).isoformat()
    second = estimate(tools, call_id='estimate-2')['data']
    assert second['estimate_id'] != first['estimate_id']
    assert datetime.fromisoformat(second['quoted_at']) - quoted == timedelta(seconds=1)
    assert len(tools.snapshot()['estimate_history']) == 2


def test_unavailable_clock_retains_previous_estimate_and_reports_retryable_failure():
    class SwitchableClock(FixedClock):
        unavailable = False

        def now(self):
            if self.unavailable:
                raise OSError('clock unavailable')
            return super().now()

    tools, _, clock = make_script_tools([draft_json()], SwitchableClock())
    search(tools)
    revise(tools)
    generate(tools)
    previous = estimate(tools)['data']
    clock.unavailable = True
    failed = estimate(tools, call_id='unavailable')
    assert not failed['ok'] and failed['error']['code'] == 'ESTIMATOR_UNAVAILABLE'
    assert failed['error']['retryable']
    state = tools.snapshot()
    assert state['current_estimate_id'] == previous['estimate_id']
    assert list(state['estimate_history'].values()) == [previous]


def test_mode_revision_reuses_script_but_requires_new_estimate():
    tools, client, _ = make_script_tools([draft_json()])
    search(tools)
    revise(tools)
    script = generate(tools)['data']
    old = estimate(tools)['data']
    revision = revise(tools, mode='basic', call_id='revise-2')['data']
    assert revision['revision'] == 2 and revision['script_reused']
    assert revision['invalidated'] == ['estimate']
    assert tools.snapshot()['current_estimate_id'] is None
    assert generate(tools, revision=2, call_id='generate-2')['data'] == script
    assert len(client.requests) == 1
    for action in (generate, estimate):
        assert action(tools, call_id='stale-' + action.__name__)['error']['code'] == 'STALE_REVISION'
    current = estimate(tools, revision=2, call_id='estimate-2')['data']
    assert (current['total_units'], current['total_minutes'], current['feasible']) == (8, 90, True)
    assert current['candidate_hash'] != old['candidate_hash']
    assert len(tools.snapshot()['estimate_history']) == 2


@pytest.mark.parametrize('changed', ['brief', 'material'])
def test_content_revision_invalidates_both_artifacts_without_removing_history(changed):
    new_material = 'M02' if changed == 'material' else 'M01'
    body = '视频片段可裁剪和拼接。' if changed == 'material' else '自动生成的字幕文本可以编辑。'
    tools, client, _ = make_script_tools([draft_json(), draft_json(new_material, body)])
    search(tools, '字幕 裁剪')
    revise(tools)
    old_script = generate(tools)['data']
    old_estimate = estimate(tools)['data']
    revision = revise(tools, material_id=new_material, brief='展示编辑操作', call_id='revise-2')['data']
    assert not revision['script_reused'] and revision['invalidated'] == ['script', 'estimate']
    assert tools.snapshot()['current_estimate_id'] is None
    assert estimate(tools, revision=2, call_id='missing-script')['error']['code'] == 'PRECONDITION_FAILED'
    current = generate(tools, revision=2, call_id='generate-2')['data']
    assert current['script_id'] != old_script['script_id']
    assert current['source_ids'] == [new_material] and len(client.requests) == 2
    state = tools.snapshot()
    assert old_script in state['script_artifacts'].values()
    assert old_estimate in state['estimate_history'].values()


@pytest.mark.parametrize('raw', ['not json', draft_json('M02'), draft_json(body='效率提升80%'),
                                  draft_json(body='行业第一'),
                                  json.dumps({'script_id': 'untrusted'})])
def test_invalid_script_returns_failure_without_an_artifact_or_automatic_retry(raw):
    tools, client, _ = make_script_tools([raw])
    search(tools)
    revise(tools)
    result = generate(tools)
    assert not result['ok'] and result['error']['code'] == 'SCRIPT_INVALID'
    assert not result['error']['retryable'] and len(client.requests) == 1
    assert tools.snapshot()['script_artifacts'] == {}
    assert estimate(tools)['error']['code'] == 'PRECONDITION_FAILED'


def test_preconditions_and_snapshot_copies_keep_state_json_safe(tools):
    assert generate(tools)['error']['code'] == 'PRECONDITION_FAILED'
    assert estimate(tools)['error']['code'] == 'PRECONDITION_FAILED'
    result = search(tools)
    result['data']['materials'][0]['facts'].clear()
    copy = tools.snapshot()
    assert copy == json.loads(json.dumps(copy))
    copy['seen_material_ids'].clear()
    assert tools.snapshot()['seen_material_ids'] == ['M01']
    assert tools.snapshot()['tool_results'][-1]['data']['materials'][0]['facts']


@pytest.mark.parametrize('revision', [True, 1.0, '1', 0, 5])
def test_revision_arguments_are_strict_for_generation_and_estimation(tools, revision):
    for action in (generate, estimate):
        result = action(tools, revision=revision, call_id=action.__name__)
        assert result['error']['code'] == 'INVALID_ARGUMENT'


def test_later_estimate_can_be_infeasible_without_becoming_tool_failure():
    tools, _, clock = make_script_tools([draft_json()])
    search(tools)
    revise(tools, mode='basic')
    generate(tools)
    assert estimate(tools)['data']['feasible']
    clock.value += timedelta(hours=2)
    result = estimate(tools, call_id='estimate-later')
    assert result['ok'] and not result['data']['feasible']
    assert result['data']['deadline_gap_minutes'] == 30


def test_success_and_failure_results_match_published_schema():
    from pathlib import Path
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[2]
    common = json.loads((root / 'contracts/common.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator({'$ref': '#/$defs/ToolResult', '$defs': common['$defs']})
    tools, _, _ = make_script_tools([draft_json()])
    search(tools, 'nothing')
    generate(tools)
    search(tools)
    revise(tools)
    generate(tools)
    estimate(tools)
    revise(tools, mode='basic', call_id='revise-2')
    generate(tools, revision=2, call_id='generate-2')
    estimate(tools, revision=2, call_id='estimate-2')
    for result in tools.snapshot()['tool_results']:
        validator.validate(result)


def test_task_owns_its_validated_catalog_snapshot():
    from content_planner.tools import LocalTools

    catalog = load_catalog()
    tools = LocalTools(Request(request_id='snapshot', topic='字幕', budget_units=10,
                               deadline_at='2026-10-29T13:00:00+08:00'),
                       catalog, FakeModelClient([draft_json()]), FixedClock())
    catalog.materials[0].facts.clear()
    catalog.pricing.video_edit.basic.fee_units = 999
    assert search(tools)['data']['materials'][0]['facts'] == [
        '影芽剪辑支持自动生成字幕。', '自动生成的字幕文本可以编辑。']
    revise(tools, mode='basic')
    generate(tools)
    assert estimate(tools)['data']['total_units'] == 8
