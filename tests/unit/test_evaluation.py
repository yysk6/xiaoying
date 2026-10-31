"""Independent evaluation checks use known prices, real tools and temporary SQLite."""

from copy import deepcopy
import json
from pathlib import Path
import hashlib
import pytest
from datetime import datetime, timedelta

from content_planner.model import FakeModelClient


DRAFT = json.dumps(dict(title='字幕演示', hook='字幕可以自动生成', body='影芽剪辑支持自动生成字幕，字幕文本可以编辑。',
                        cta='了解字幕功能', source_ids=['M01']), ensure_ascii=False)


def call(name, call_id, **arguments):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': call_id, 'type': 'function', 'function': {'name': name,
         'arguments': json.dumps({'rationale': '依据当前观察选择动作', **arguments}, ensure_ascii=False)}}]}


def finish(revision=1):
    return [call('estimate_cost', 'estimate', plan_revision=revision),
            call('save_plan', 'save', plan_revision=revision,
                 estimate_id='estimate_' + hashlib.sha256(b'estimate').hexdigest())]

from content_planner.catalog import load_catalog


def test_independent_quote_check_rejects_a_consistent_but_wrong_total():
    from scripts.evaluate_budget import verify_quote

    result = json.loads((Path(__file__).resolve().parents[2] / 'examples/mock/A04/output.json').read_text(encoding='utf-8'))
    quote = next(r['data'] for r in result['tool_results'] if r['tool'] == 'estimate_cost')
    catalog = load_catalog()
    request = {'budget_units': 10, 'deadline_at': '2026-10-31T06:00:00+00:00'}
    assert verify_quote(quote, request, catalog.materials[0].model_dump(), catalog.pricing.model_dump(), 'premium')
    wrong = deepcopy(quote)
    wrong['line_items'][2]['fee_units'] = 4
    wrong.update(total_units=8, within_budget=True, feasible=True, budget_gap_units=0)
    assert not verify_quote(wrong, request, catalog.materials[0].model_dump(), catalog.pricing.model_dump(), 'premium')


def test_failure_evaluation_retains_failed_attempt_and_records_real_observation(tmp_path):
    from scripts.evaluate_budget import run_case

    decisions = [call('search_materials', 'search', query='字幕', top_k=1),
                 call('revise_plan', 'choose', material_id='M01', creative_brief='展示字幕编辑', production_mode='basic'),
                 call('generate_script', 'first', plan_revision=1),
                 call('generate_script', 'retry', plan_revision=1), *finish()]
    bundle, verdict = run_case('L02', FakeModelClient([DRAFT], decisions=decisions),
                               database=tmp_path / 'runtime.db', folder=tmp_path / 'L02')
    assert verdict['invariants_pass'] and verdict['behavior_pass'], verdict
    assert verdict['failure_handling_pass'] and verdict['recovery_pass']
    assert len(bundle['plans']) == 1
    assert [s['status'] for s in bundle['output']['execution_steps'] if s['tool'] == 'generate_script'] == ['failed', 'succeeded']
    assert any(d['memory']['last_observation']['error']['code'] == 'SCRIPT_MODEL_UNAVAILABLE'
               for d in bundle['decisions'] if d['memory']['last_observation'].get('error'))
    assert verdict['content_pass'] is None and verdict['passed'] is None


def test_given_twelve_unit_state_reaches_real_decision_without_fabricated_messages(tmp_path):
    from scripts.evaluate_budget import run_case

    model = FakeModelClient([DRAFT], decisions=[
        call('revise_plan', 'basic', material_id='M01', creative_brief='展示字幕编辑', production_mode='basic'), *finish(2)])
    bundle, verdict = run_case('L04', model, database=tmp_path / 'runtime.db', folder=tmp_path / 'L04')
    assert verdict['invariants_pass'] and verdict['behavior_pass'], verdict
    assert model.decision_requests[0]['messages'] == []
    assert model.decision_requests[0]['memory']['latest_estimate']['total_units'] == 12
    assert [r['data']['total_units'] for r in bundle['output']['tool_results'] if r['tool'] == 'estimate_cost'] == [12, 8]
    assert bundle['script_attempts'] == 1
    assert len([e for e in bundle['events'] if e['args'].get('origin') == 'fixture_setup' and e['phase'] == 'succeeded']) == 5


@pytest.mark.parametrize('corruption', ['stale_estimate', 'unobserved_quote', 'false_success', 'missing_plan', 'wrong_price'])
def test_evaluator_rejects_false_evidence_even_when_task_says_completed(tmp_path, corruption):
    from scripts.evaluate_budget import run_case, evaluate_evidence

    model = FakeModelClient([DRAFT], decisions=[
        call('revise_plan', 'basic', material_id='M01', creative_brief='展示字幕编辑', production_mode='basic'), *finish(2)])
    bundle, _ = run_case('L04', model, database=tmp_path / 'runtime.db', folder=tmp_path / 'L04')
    if corruption == 'stale_estimate':
        next(e for e in bundle['events'] if e['name'] == 'save_plan' and e['phase'] == 'started')['args']['arguments']['estimate_id'] = 'fixture-old-estimate'
    elif corruption == 'unobserved_quote':
        bundle['decisions'][0]['memory']['latest_estimate']['total_units'] = 999
    elif corruption == 'false_success':
        bundle['output']['execution_steps'][0]['status'] = 'failed'
    elif corruption == 'missing_plan':
        bundle['plans'] = []
    else:
        bundle['output']['tool_results'][3]['data']['total_units'] = 8
    assert not evaluate_evidence('L04', bundle)['invariants_pass']


def test_infeasible_result_is_a_successful_evaluation_with_gap_and_no_plan(tmp_path):
    from scripts.evaluate_budget import run_case

    model = FakeModelClient([DRAFT], decisions=[
        call('search_materials', 'search', query='字幕', top_k=1),
        call('revise_plan', 'choose', material_id='M01', creative_brief='展示字幕编辑', production_mode='basic'),
        call('generate_script', 'generate', plan_revision=1), finish()[0],
        call('stop_task', 'stop', reason='constraints_unsatisfied', message='当前资料最低8，预算5，缺口3')])
    bundle, verdict = run_case('L05', model, database=tmp_path / 'runtime.db', folder=tmp_path / 'L05')
    assert verdict['invariants_pass'] and verdict['behavior_pass'], verdict
    assert verdict['minimum_budget_gap_units'] == 3
    assert bundle['output']['status'] == 'incomplete' and verdict['plan_rows'] == 0


def test_evaluation_cli_refuses_paid_calls_without_explicit_flag(tmp_path):
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[2] / 'scripts/evaluate_budget.py'
    result = subprocess.run([sys.executable, str(script), '--output-dir', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 2 and '--live' in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_failed_result_cannot_be_reported_as_success_in_both_events_and_steps(tmp_path):
    from scripts.evaluate_budget import run_case, evaluate_evidence

    decisions = [call('search_materials', 'search', query='字幕', top_k=1),
                 call('revise_plan', 'choose', material_id='M01', creative_brief='展示字幕编辑', production_mode='basic'),
                 call('generate_script', 'first', plan_revision=1),
                 call('generate_script', 'retry', plan_revision=1), *finish()]
    bundle, _ = run_case('L02', FakeModelClient([DRAFT], decisions=decisions),
                         database=tmp_path / 'runtime.db', folder=tmp_path / 'L02')
    next(e for e in bundle['events'] if e['name'] == 'generate_script' and e['phase'] == 'failed')['phase'] = 'succeeded'
    next(s for s in bundle['output']['execution_steps'] if s['tool_call_id'] == 'first')['status'] = 'succeeded'
    assert not evaluate_evidence('L02', bundle)['invariants_pass']


def test_plan_timeline_must_be_anchored_to_save_time_and_deadline(tmp_path):
    from scripts.evaluate_budget import run_case, evaluate_evidence

    model = FakeModelClient([DRAFT], decisions=[
        call('revise_plan', 'basic', material_id='M01', creative_brief='展示字幕编辑', production_mode='basic'), *finish(2)])
    bundle, _ = run_case('L04', model, database=tmp_path / 'runtime.db', folder=tmp_path / 'L04')
    for plan in [bundle['plans'][0], bundle['output']['saved_plan']]:
        for step in plan['task_plan']:
            for field in ('starts_at', 'finishes_at'):
                step[field] = (datetime.fromisoformat(step[field]) + timedelta(days=1)).isoformat()
    bundle['output']['task_plan'] = deepcopy(bundle['output']['saved_plan']['task_plan'])
    assert not evaluate_evidence('L04', bundle)['invariants_pass']


def test_malformed_evidence_is_a_failed_verdict_instead_of_losing_the_report():
    from scripts.evaluate_budget import evaluate_evidence

    verdict = evaluate_evidence('L04', {'output': {'status': 'completed'}})
    assert verdict['invariants_pass'] is False and verdict['behavior_pass'] is False
    assert verdict['errors']
