"""Independent, opt-in evaluation of budget replanning and failure recovery."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from content_planner.catalog import load_catalog
from content_planner.contracts import Request
from content_planner.domain import SystemClock
from content_planner.graph import PlanningAgent
from content_planner.model import ModelUnavailable
from content_planner.reporting import task_result
from content_planner.service import run_task, export_task
from content_planner.storage import Repository
from content_planner.tools import LocalTools
from langgraph.checkpoint.sqlite import SqliteSaver


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_database(database, request_id):
    with sqlite3.connect(f'{Path(database).resolve().as_uri()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        events = []
        for row in db.execute('SELECT * FROM events WHERE request_id=? ORDER BY event_id', (request_id,)):
            event = dict(row)
            for name in ('args', 'result', 'state_patch'):
                value = event.pop(name + '_json')
                event[name] = json.loads(value) if value is not None else None
            events.append(event)
        plans = [json.loads(row[0]) for row in db.execute('SELECT payload_json FROM plans WHERE request_id=?', (request_id,))]
    return events, plans


class ObservedModel:
    """Record only safe decision facts at the existing ModelClient seam."""
    def __init__(self, model, database, request_id, *, fail_first=False):
        self.model, self.model_id = model, model.model_id
        self.database, self.request_id = database, request_id
        self.fail_first, self.injected = fail_first, False
        self.decisions, self.script_attempts = [], 0

    @property
    def last_usage(self):
        return getattr(self.model, 'last_usage', None)

    def decide(self, context):
        memory = context['memory']
        events, _ = read_database(self.database, self.request_id)
        observation = memory['last_observation'] or {}
        record = {'event_id': events[-1]['event_id'], 'operation_id': events[-1]['operation_id'],
                  'memory': {key: deepcopy(memory[key]) for key in (
                      'candidate', 'latest_estimate', 'seen_material_ids', 'script', 'evaluated_quotes')},
                  'response': None}
        record['memory'].update(budget_units=memory['request']['budget_units'],
            last_observation={key: deepcopy(observation.get(key)) for key in ('tool_call_id', 'tool', 'ok', 'error')})
        self.decisions.append(record)
        response = self.model.decide(context)
        record['response'] = {key: deepcopy(value) for key, value in response.items() if key in {'role', 'content', 'tool_calls'}}
        return response

    def generate_script(self, context):
        self.script_attempts += 1
        if self.fail_first and not self.injected:
            self.injected = True
            raise ModelUnavailable('Declared evaluation failure before HTTP')
        return self.model.generate_script(context)


def verify_quote(value, request, material, pricing, mode):
    """Recompute expected values directly from source data, without domain.quote."""
    expected = [
        ('material_prepare', material['material_id'], material['fee_units'], material['lead_minutes']),
        ('script_finalize', 'script_finalize', pricing['script_finalize']['fee_units'], pricing['script_finalize']['duration_minutes']),
        ('video_edit', 'video_edit:' + mode, pricing['video_edit'][mode]['fee_units'], pricing['video_edit'][mode]['duration_minutes']),
        ('review', 'review', pricing['review']['fee_units'], pricing['review']['duration_minutes']),
    ]
    try:
        if 'line_items' in value and value['line_items'] != [
                dict(step_id=step, catalog_item_id=item, fee_units=fee, duration_minutes=minutes)
                for step, item, fee, minutes in expected]:
            return False
        units = sum(row[2] for row in expected)
        minutes = sum(row[3] for row in expected)
        finish = datetime.fromisoformat(value['quoted_at']) + timedelta(minutes=minutes)
        deadline = datetime.fromisoformat(request['deadline_at'])
        late_seconds = (finish - deadline).total_seconds()
        gap_minutes = max(0, int(-(-late_seconds // 60)))
        fields = dict(total_units=units, total_minutes=minutes, estimated_finish_at=finish.isoformat(),
                      within_budget=units <= request['budget_units'], within_deadline=finish <= deadline,
                      feasible=units <= request['budget_units'] and finish <= deadline,
                      budget_gap_units=max(0, units - request['budget_units']), deadline_gap_minutes=gap_minutes)
        return all(type(value[key]) is type(wanted) and value[key] == wanted for key, wanted in fields.items())
    except (KeyError, ValueError, TypeError):
        return False


def evaluate_evidence(case, bundle):
    """Check persisted facts independently; content remains pending human review."""
    try:
        return _evaluate_evidence(case, bundle)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return {'case': case, 'invariants_pass': False, 'behavior_pass': False,
                'errors': ['MALFORMED_EVIDENCE:' + type(error).__name__],
                'content_pass': None, 'content_review': 'PENDING', 'passed': False}


def _evaluate_evidence(case, bundle):
    output, events, plans = (bundle[key] for key in ('output', 'events', 'plans'))
    request = bundle['input']
    catalog = bundle['catalog']
    materials = {m['material_id']: m for m in catalog['materials']}
    errors = []

    def check(condition, label):
        if not condition:
            errors.append(label)

    completed = output['status'] == 'completed'
    check(len(plans) == int(completed), 'database_plan_count')
    check(output['saved_plan'] == (plans[0] if plans else None), 'database_payload')
    ended = {event['operation_id']: event for event in events if event['phase'] != 'started'}
    for step in output['execution_steps']:
        end = ended.get(step['operation_id'])
        check(end is not None and step['status'] == end['phase'] and step['error_code'] == end['error_code'],
              'attempt_status:' + step['operation_id'])
    actual_results = [event['result'] for event in events if isinstance(event['result'], dict)
                      and 'tool_call_id' in event['result']]
    check(all(value in output['tool_results'] for value in actual_results), 'retained_tool_results')
    for event in events:
        value = event['result'] or {}
        if 'tool_call_id' in value:
            expected_phase = 'succeeded' if value['ok'] else ('failed' if value['error']['retryable'] else 'rejected')
            check(event['phase'] == expected_phase
                  and event['error_code'] == (None if value['ok'] else value['error']['code']), 'result_phase_semantics')
    starts = {e['operation_id']: e for e in events if e['phase'] == 'started'}
    seen, scripts, candidate, latest = set(), {}, None, None
    for event in events:
        result = event['result'] or {}
        if 'tool_call_id' not in result or not result['ok']:
            continue
        start_args = starts[event['operation_id']]['args']
        args = start_args.get('arguments', start_args)
        name, data = result['tool'], result['data']
        if name == 'search_materials':
            seen.update(m['material_id'] for m in data['materials'])
        elif name == 'revise_plan':
            check(args['material_id'] in seen and data['material_id'] == args['material_id']
                  and data['production_mode'] == args['production_mode']
                  and data['creative_brief'] == args['creative_brief'], 'observed_candidate')
            if candidate is None or candidate['candidate_hash'] != data['candidate_hash']:
                latest = None
            candidate = data
        elif name == 'generate_script':
            check(candidate is not None and args['plan_revision'] == candidate['revision']
                  and data['script_input_hash'] == candidate['script_input_hash']
                  and data['source_ids'] == [candidate['material_id']], 'script_dependencies')
            scripts[data['script_input_hash']] = data
        elif name == 'estimate_cost':
            script = scripts.get(candidate['script_input_hash']) if candidate else None
            check(candidate is not None and args['plan_revision'] == candidate['revision']
                  and data['revision'] == candidate['revision'] and data['candidate_hash'] == candidate['candidate_hash']
                  and script is not None and data['script_id'] == script['script_id'], 'estimate_dependencies')
            latest = data
        elif name == 'save_plan':
            check(latest is not None and latest['feasible'] and args['estimate_id'] == latest['estimate_id']
                  and args['plan_revision'] == candidate['revision']
                  and data['saved_plan']['candidate']['candidate_hash'] == candidate['candidate_hash'], 'save_dependencies')
    quotes = []
    for result in output['tool_results']:
        if not result['ok'] or result['tool'] != 'estimate_cost':
            continue
        value = result['data']
        item_id = value['line_items'][0]['catalog_item_id']
        mode = value['line_items'][2]['catalog_item_id'].split(':')[-1]
        check(item_id in materials and verify_quote(value, request, materials[item_id], catalog['pricing'], mode),
              'quote:' + value['estimate_id'])
        quotes.append(value)
        for alternative in value['alternatives']:
            check(verify_quote({**alternative, 'quoted_at': value['quoted_at']}, request,
                               materials[item_id], catalog['pricing'], alternative['production_mode']), 'alternative_quote')
    if plans:
        plan = plans[0]
        mode = plan['candidate']['production_mode']
        material = materials[plan['candidate']['material_id']]
        quotation = {**plan, 'quoted_at': plan['saved_at'], 'within_budget': plan['total_units'] <= request['budget_units'],
                     'within_deadline': plan['estimated_finish_at'] <= request['deadline_at'],
                     'feasible': True, 'budget_gap_units': 0, 'deadline_gap_minutes': 0}
        check(verify_quote(quotation, request, material, catalog['pricing'], mode), 'saved_quote')
        check(output['total_units'] == plan['total_units'] and output['candidate'] == plan['candidate'], 'output_candidate')
        previous = None
        for step, line in zip(plan['task_plan'], plan['line_items']):
            check(step['status'] == 'planned' and step['depends_on'] == ([previous['step_id']] if previous else []), 'planned_dependencies')
            check(step['step_id'] == line['step_id'] and step['fee_units'] == line['fee_units']
                  and step['duration_minutes'] == line['duration_minutes'], 'planned_line_items')
            check((not previous or step['starts_at'] == previous['finishes_at'])
                  and datetime.fromisoformat(step['finishes_at']) - datetime.fromisoformat(step['starts_at'])
                  == timedelta(minutes=step['duration_minutes']), 'planned_timing')
            previous = step
        check(len(plan['task_plan']) == 4 and output['task_plan'] == plan['task_plan'], 'four_planned_steps')
        check(bool(plan['task_plan']) and plan['task_plan'][0]['starts_at'] == plan['saved_at']
              and plan['estimated_start_at'] == plan['saved_at']
              and plan['task_plan'][-1]['finishes_at'] == plan['estimated_finish_at']
              and datetime.fromisoformat(plan['estimated_finish_at']) <= datetime.fromisoformat(request['deadline_at']),
              'plan_time_anchors')
    for decision in bundle['decisions']:
        event = next((e for e in events if e['event_id'] == decision['event_id']), None)
        check(event is not None and event['name'] == 'planner' and event['phase'] == 'started', 'decision_event')
        response = ended.get(decision['operation_id'], {}).get('result') or {}
        check(decision['response'] == response.get('response'), 'decision_response')
        check(decision['memory']['budget_units'] == request['budget_units'], 'observed_budget')
        prior_state = {}
        for prior in events:
            if prior['event_id'] >= decision['event_id']:
                break
            prior_state.update(prior['state_patch'] or {})
            if isinstance(prior['result'], dict) and 'tool_call_id' in prior['result']:
                # A save transaction can persist its failure without a graph state patch.
                prior_state['last_observation'] = prior['result']
        expected_estimate = prior_state.get('estimate_history', {}).get(prior_state.get('current_estimate_id'))
        check(decision['memory']['latest_estimate'] == expected_estimate, 'observed_quote')
        prior_observation = prior_state.get('last_observation') or {}
        check(decision['memory']['last_observation'] == {
            key: prior_observation.get(key) for key in ('tool_call_id', 'tool', 'ok', 'error')}, 'observed_tool_result')
    failures = [r for r in output['tool_results'] if r['tool'] == 'generate_script' and not r['ok']
                and r['error']['code'] == 'SCRIPT_MODEL_UNAVAILABLE']
    observed_failure = any(d['memory']['last_observation']['tool_call_id'] in {r['tool_call_id'] for r in failures}
                           and (d['memory']['last_observation']['error'] or {}).get('code') == 'SCRIPT_MODEL_UNAVAILABLE'
                           for d in bundle['decisions'])
    retained = sum(s['tool'] == 'search_materials' for s in output['execution_steps']) == 1
    failure_handling = bool(failures) and observed_failure and retained and (
        completed or output['reason'] == 'tool_failure')
    recovery = failure_handling and completed
    behavior = recovery if case == 'L02' else completed
    if case == 'L04':
        saw_twelve = any(d['memory']['latest_estimate'] and d['memory']['latest_estimate']['total_units'] == 12
                         and d['memory']['latest_estimate']['budget_gap_units'] == 2 for d in bundle['decisions'])
        behavior = completed and saw_twelve and output['total_units'] == 8 and output['current_revision'] >= 2
    minimum_gap = min((value['budget_gap_units'] for q in quotes for value in [q, *q['alternatives']]), default=None)
    if case == 'L05':
        behavior = output['status'] == 'incomplete' and output['reason'] == 'constraints_unsatisfied' and minimum_gap == 3
    return {'case': case, 'invariants_pass': not errors, 'errors': errors, 'behavior_pass': behavior,
            'failure_handling_pass': failure_handling if case == 'L02' else None,
            'recovery_pass': recovery if case == 'L02' else None,
            'content_pass': None, 'passed': None, 'content_review': 'PENDING',
            'minimum_budget_gap_units': minimum_gap,
            'plan_rows': len(plans), 'decision_event_ids': [d['event_id'] for d in bundle['decisions']]}


class FixtureScript:
    """Account for the actual model request made by the declared setup actions."""
    def __init__(self, model, repo, request_id, clock):
        self.model, self.model_id = model, model.model_id
        self.repo, self.request_id, self.clock = repo, request_id, clock

    def generate_script(self, context):
        fields = dict(kind='model', name='script', args={'origin': 'fixture_setup'}, rationale='',
                      created_at=self.clock.now().isoformat())
        self.repo.start_operation(self.request_id, 'fixture:script', limit=32, **fields)
        try:
            response = self.model.generate_script(context)
        except ModelUnavailable as error:
            self.repo.record_event(self.request_id, 'fixture:script', 'failed', error_code=error.code,
                                   result={'usage': error.usage, 'retryable': error.retryable}, **fields)
            raise
        self.repo.record_event(self.request_id, 'fixture:script', 'succeeded',
                               result={'response': response, 'usage': self.model.last_usage}, **fields)
        return response


def run_seeded(request, catalog, observed, clock, database):
    """Initialize real tool state and checkpoint; no assistant messages are invented."""
    with Repository(database) as repo, SqliteSaver.from_conn_string(str(database)) as saver:
        agent = PlanningAgent(Request.model_validate(request), catalog, observed, clock, repo, saver)
        fixture = LocalTools(Request.model_validate(request), catalog,
                             FixtureScript(observed, repo, request['request_id'], clock), clock, repository=repo)
        actions = [('search_materials', {'query': '字幕', 'top_k': 1}),
                   ('revise_plan', {'material_id': 'M01', 'creative_brief': '展示字幕编辑', 'production_mode': 'premium'}),
                   ('generate_script', {'plan_revision': 1}), ('estimate_cost', {'plan_revision': 1})]
        for index, (name, args) in enumerate(actions):
            args = {**args, 'rationale': 'fixture_setup：建立题目给定的初始方案'}
            call_id = f'fixture-{index}'
            operation = 'tool:' + call_id
            fields = dict(kind='control' if name == 'revise_plan' else 'tool', name=name,
                          args={'origin': 'fixture_setup', 'arguments': args, 'tool_call_id': call_id},
                          rationale=args['rationale'], created_at=clock.now().isoformat())
            repo.start_operation(request['request_id'], operation, limit=24, **fields)
            result = getattr(fixture, name)(call_id, args)
            repo.record_event(request['request_id'], operation,
                              'succeeded' if result['ok'] else ('failed' if result['error']['retryable'] else 'rejected'),
                              result=result, state_patch=fixture.snapshot(),
                              error_code=None if result['ok'] else result['error']['code'], **fields)
            if not result['ok']:
                state = {**fixture.snapshot(), 'status': 'incomplete', 'reason': result['error']['code'],
                         'message': 'Declared fixture setup failed before planner handover'}
                return task_result(repo.get_request(request['request_id']), state, repo.events(request['request_id']), None)
        state = {**fixture.snapshot(), 'planner_messages': [], 'decision_seq': 0,
                 'consecutive_protocol_errors': 0, 'pending_call': None, 'message': ''}
        agent.graph.update_state(agent.config, state, as_node='dispatch')
        state = agent.resume()
        return task_result(repo.get_request(request['request_id']), state, repo.events(request['request_id']),
                           repo.get_plan(request['request_id']))


def run_case(case, model, *, database, folder, clock=None):
    clock = clock or SystemClock()
    now = clock.now()
    request = {'request_id': case + '-' + uuid.uuid4().hex[:12], 'topic': '影芽剪辑字幕功能推广',
               'budget_units': 5 if case == 'L05' else 10,
               'deadline_at': (now + timedelta(hours=4)).isoformat()}
    folder = Path(folder)
    catalog = load_catalog()
    observed = ObservedModel(model, database, request['request_id'], fail_first=case == 'L02')
    scenario = {'clock_source': type(clock).__name__, 'fixture_setup': case == 'L04',
                'fault_injection': 'first script request before HTTP' if case == 'L02' else None}
    write_json(folder / 'input.json', request)
    write_json(folder / 'scenario.json', scenario)
    if case == 'L04':
        result = run_seeded(request, catalog, observed, clock, database)
    else:
        result = run_task(request, database=database, model=observed, clock=clock,
                          backend='mock' if model.model_id == 'mock' else 'deepseek')
    result = export_task(result, database=database, directory=folder)
    events, plans = read_database(database, request['request_id'])
    bundle = {'input': request, 'output': result, 'events': events, 'plans': plans,
              'decisions': observed.decisions, 'script_attempts': observed.script_attempts,
              'catalog': {'materials': [m.model_dump(mode='json') for m in catalog.materials],
                          'pricing': catalog.pricing.model_dump(mode='json')}}
    write_json(folder / 'evidence.json', bundle)
    verdict = evaluate_evidence(case, bundle)
    write_json(folder / 'verdict.json', verdict)
    return bundle, verdict


def main(argv=None):
    import argparse
    import getpass
    import subprocess
    import sys

    from content_planner.deepseek import DeepSeekModelClient
    from content_planner.domain import Fault

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Explicitly permit paid API requests')
    parser.add_argument('--key-stdin', action='store_true', help='Read key through hidden terminal input')
    parser.add_argument('--output-dir', type=Path, default=Path('examples/live/budget-replan'))
    parser.add_argument('--db', type=Path, default=Path('work/budget-evaluation.db'))
    args = parser.parse_args(argv)
    if not args.live or not args.key_stdin:
        parser.error('--live and --key-stdin are required; no HTTP requests were made')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    folder = args.output_dir / run_id
    root = Path(__file__).resolve().parents[1]
    source = {}
    for field, command in [('commit', ['rev-parse', 'HEAD']), ('status', ['status', '--porcelain'])]:
        process = subprocess.run(['git', '-c', f'safe.directory={root.as_posix()}', *command],
                                 cwd=root, capture_output=True, text=True)
        source[field] = process.stdout.strip() if process.returncode == 0 else None
    summary = {'run_id': run_id, 'started_at': datetime.now(timezone.utc).isoformat(), 'source': source,
               'cases': [], 'samples_per_case': 1, 'backend': 'deepseek', 'model': 'deepseek-v4-pro',
               'parameters': {'temperature': 0, 'thinking': 'disabled', 'planner_max_tokens': 2048, 'script_max_tokens': 1536},
               'argv': list(sys.argv), 'http_attempts': 0, 'api_cost_usd': None, 'content_review': 'PENDING'}
    key = getpass.getpass('DeepSeek API key (hidden): ')
    try:
        with DeepSeekModelClient(api_key=key) as model:
            key = None
            try:
                for case in ('L04', 'L05', 'L02'):
                    started = datetime.now(timezone.utc).isoformat()
                    before = model.http_attempts
                    bundle, verdict = run_case(case, model, database=args.db, folder=folder / case)
                    metadata = {'case': case, 'started_at': started, 'ended_at': datetime.now(timezone.utc).isoformat(),
                                'source': source, 'backend': 'deepseek', 'model': model.model_id,
                                'parameters': summary['parameters'], 'argv': summary['argv'],
                                'status': bundle['output']['status'], 'reason': bundle['output']['reason'],
                                'http_attempts': model.http_attempts - before, 'usage': bundle['output']['usage'],
                                'manifest': bundle['output']['manifest'], 'verdict': verdict}
                    write_json(folder / case / 'run.json', metadata)
                    summary['cases'].append(metadata)
                    print(f"{case}: status={metadata['status']} invariants={verdict['invariants_pass']} behavior={verdict['behavior_pass']}", flush=True)
                    if metadata['reason'] in {'AUTH_ERROR', 'MODEL_CONFIG_ERROR'}:
                        break
            finally:
                summary['http_attempts'] = model.http_attempts
    except (Fault, ModelUnavailable) as error:
        summary['error'] = {'code': error.code, 'message': str(error)}
    except Exception as error:
        summary['error'] = {'code': 'EVALUATOR_ERROR', 'exception_type': type(error).__name__}
    finally:
        key = None
        summary['ended_at'] = datetime.now(timezone.utc).isoformat()
        summary['technical_pass'] = len(summary['cases']) == 3 and all(
            c['verdict']['invariants_pass'] and c['verdict']['behavior_pass'] for c in summary['cases'])
        summary['passed'] = None
        write_json(folder / 'summary.json', summary)
        print(json.dumps({'summary': str(folder / 'summary.json'), 'technical_pass': summary['technical_pass'],
                          'http_attempts': summary['http_attempts']}, ensure_ascii=False), flush=True)
    return 0 if summary['technical_pass'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
