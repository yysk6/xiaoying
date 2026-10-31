"""Opt-in rubric evaluation of twenty frozen cases; no business policy changes."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Literal
import uuid

from pydantic import Field

from content_planner.catalog import load_catalog
from content_planner.contracts import StrictDTO
from content_planner.model import ModelUnavailable
from content_planner.service import export_task, resume_task, run_task, show_task
from scripts.evaluate_budget import ObservedModel, evaluate_evidence, read_database, run_seeded, write_json


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'examples/evaluation/core20-cases.json'


class Case(StrictDTO):
    case_id: str = Field(pattern=r'^E\d{2}$')
    label: str
    budget: int = 10
    deadline_minutes: int = 240
    topic: str = '影芽剪辑字幕功能推广'
    material_id: str = 'M01'
    seed_premium: bool = False
    allowed_units: list[int] = Field(default_factory=lambda: [8])
    expected_status: Literal['completed', 'incomplete', 'needs_input'] = 'completed'
    expected_reason: str | None = None
    budget_gap: int | None = None
    deadline_gap: int | None = None
    omit: list[Literal['budget_units', 'deadline_at']] = Field(default_factory=list)
    replan: Literal['budget', 'deadline'] | None = None
    exact_deadline: bool = False
    fault: Literal['script_once', 'script_always', 'save_once', 'planner_once'] | None = None
    followup: Literal['resume', 'duplicate', 'conflict'] | None = None


def load_cases():
    cases = [Case.model_validate(value) for value in json.loads(CASES.read_text(encoding='utf-8'))]
    if [case.case_id for case in cases] != [f'E{i:02}' for i in range(1, 21)]:
        raise ValueError('Exactly E01 through E20 are required')
    return cases


class FixedClock:
    def __init__(self, instant):
        self.instant = instant

    def now(self):
        return self.instant


def database_snapshot(database, request_id):
    if not database.exists():
        return {'exists': False, 'request': None, 'events': [], 'plans': []}
    events, plans = read_database(database, request_id)
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT input_json FROM requests WHERE request_id=?', (request_id,)).fetchone()
    return {'exists': True, 'request': json.loads(row[0]) if row else None, 'events': events, 'plans': plans}


def provider_attempts(model):
    if hasattr(model, 'http_attempts'):
        return model.http_attempts
    return len(model.decision_requests) + len(model.requests)


class FaultSource:
    """Declared faults at the external model seam or the actual SQLite transaction."""
    def __init__(self, model, fault, database, request_id):
        self.model, self.model_id = model, model.model_id
        self.fault, self.database, self.request_id = fault, database, request_id
        self.log, self.script_calls = [], 0
        self.planner_failed = self.save_armed = self.save_failed = self.injected_last = False

    @property
    def last_usage(self):
        return None if self.injected_last else getattr(self.model, 'last_usage', None)

    def generate_script(self, context):
        self.script_calls += 1
        self.injected_last = self.fault == 'script_always' or (self.fault == 'script_once' and self.script_calls == 1)
        if self.injected_last:
            self.log.append({'kind': 'script_failure', 'attempt': self.script_calls, 'before_http': True})
            raise ModelUnavailable('Declared evaluation script failure before HTTP')
        return self.model.generate_script(context)

    def decide(self, context):
        memory = context['memory']
        observation = memory['last_observation'] or {}
        self.injected_last = False
        if self.fault == 'planner_once' and memory['candidate'] and not self.planner_failed:
            self.planner_failed = self.injected_last = True
            self.log.append({'kind': 'planner_failure', 'before_http': True,
                             'retained_candidate': memory['candidate']['candidate_hash']})
            raise ModelUnavailable('Declared evaluation planner failure before HTTP')
        if self.save_armed and not self.save_failed and (observation.get('error') or {}).get('code') == 'SAVE_FAILED':
            self.save_failed = True
            with sqlite3.connect(self.database) as db:
                count = db.execute('SELECT COUNT(*) FROM plans').fetchone()[0]
                db.execute('DROP TRIGGER evaluation_save_once')
            self.log.append({'kind': 'save_transaction_failure', 'tool_call_id': observation['tool_call_id'],
                             'plan_rows_at_failure': count, 'trigger_removed': True})
        response = self.model.decide(context)
        if self.fault == 'save_once' and not self.save_armed:
            calls = response.get('tool_calls') or []
            if isinstance(calls, list) and any(isinstance(call, dict) and isinstance(call.get('function'), dict)
                    and call['function'].get('name') == 'save_plan' for call in calls):
                with sqlite3.connect(self.database) as db:
                    db.execute("CREATE TRIGGER evaluation_save_once BEFORE INSERT ON plans BEGIN SELECT RAISE(ABORT, 'declared evaluation fault'); END")
                self.save_armed = True
        return response

    def cleanup(self):
        if self.save_armed:
            with sqlite3.connect(self.database) as db:
                db.execute('DROP TRIGGER IF EXISTS evaluation_save_once')


class SuiteObserver(ObservedModel):
    def __init__(self, model, database, request_id, folder):
        super().__init__(model, database, request_id)
        self.folder = folder

    def decide(self, context):
        try:
            return super().decide(context)
        finally:
            if self.decisions:
                self.decisions[-1]['memory']['deadline_at'] = context['memory']['request']['deadline_at']
            write_json(self.folder / 'observations.json', self.decisions)
            write_json(self.folder / 'fault-log.json', self.model.log)


def schema_trace_errors(bundle):
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    schemas = {path.name: json.loads(path.read_text(encoding='utf-8')) for path in (ROOT / 'contracts').glob('*.schema.json')}
    registry = Registry().with_resources((name, Resource.from_contents(value)) for name, value in schemas.items())
    errors = []
    for name, values in [('result', [bundle['output']]), ('trace-event', bundle['trace'])]:
        validator = Draft202012Validator(schemas[name + '.schema.json'], registry=registry, format_checker=FormatChecker())
        if any(list(validator.iter_errors(value)) for value in values):
            errors.append('schema:' + name)
    trace, events, output = bundle['trace'], bundle['events'], bundle['output']
    if len(trace) != len(events):
        errors.append('trace_event_count')
    status = 'running'
    for index, (item, event) in enumerate(zip(trace, events)):
        for field in ('event_id', 'operation_id', 'kind', 'phase', 'name', 'created_at'):
            if item.get(field) != event[field]:
                errors.append('trace_' + field)
        if item['request_id'] != output['request_id'] or item['model'] != output['model'] or item['backend'] != output['backend']:
            errors.append('trace_identity')
        expected_next = next((e['event_id'] for e in events if e['event_id'] > event['event_id']
                              and e['name'] == 'planner' and e['phase'] == 'started'), None)
        if item['next_decision_event_id'] != expected_next:
            errors.append('trace_next_decision')
        observation = event['result'] or {}
        expected_ref = next((f'tool_results:{i}' for i, result in enumerate(output['tool_results'])
                             if result.get('tool_call_id') == observation.get('tool_call_id')), None)
        if item['result_ref'] != expected_ref:
            errors.append('trace_result_ref')
        origin = 'fixture_setup' if event['args'].get('origin') == 'fixture_setup' else (
            'model' if event['kind'] in {'tool', 'control', 'validation'} else 'system')
        if item['origin'] != origin:
            errors.append('trace_origin')
        summary = json.loads(item['observation_summary'])
        if summary['phase'] != event['phase'] or summary.get('error_code') != event['error_code']:
            errors.append('trace_observation_status')
        if 'ok' in observation and (summary.get('ok') != observation['ok'] or summary.get('reused') != observation['reused']):
            errors.append('trace_observation_result')
        if (event['state_patch'] or {}).get('status'):
            status = event['state_patch']['status']
        if index == len(events) - 1:
            status = output['status']
        if item['task_status'] != status:
            errors.append('trace_task_status')
    return errors


def assess_case(case, bundle):
    try:
        return _assess_case(case, bundle)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return {'case_id': case.case_id, 'label': case.label, 'invariants_pass': False, 'behavior_pass': False,
                'passed': False, 'errors': ['MALFORMED_EVIDENCE:' + type(error).__name__], 'behavior_errors': [],
                'status': (bundle.get('output') or {}).get('status'), 'reason': 'EVALUATION_ERROR'}


def _assess_case(case, bundle):
    common = evaluate_evidence(case.case_id, bundle)
    errors = list(common['errors']) + schema_trace_errors(bundle)
    output, events = bundle['output'], bundle['events']
    expected_input = {'request_id': bundle['input']['request_id'], 'topic': case.topic,
                      'budget_units': case.budget, 'deadline_at': (datetime.fromisoformat(
                          bundle['scenario']['clock_at']) + timedelta(minutes=case.deadline_minutes)).isoformat()}
    for field in case.omit:
        expected_input.pop(field)
    if bundle['input'] != expected_input:
        errors.append('scenario_input_mismatch')
    snapshot = bundle['database']
    if snapshot['exists'] and snapshot['request'] != bundle['input']:
        errors.append('database_request_mismatch')
    if snapshot['events'] != events or snapshot['plans'] != bundle['plans']:
        errors.append('database_facts_mismatch')
    attempts = [(e['event_id'], e['operation_id']) for e in events
                if e['kind'] in {'tool', 'control'} and e['phase'] == 'started']
    if [(s['event_id'], s['operation_id']) for s in output['execution_steps']] != attempts:
        errors.append('execution_steps_coverage')
    behavior = []
    if output['status'] != case.expected_status or output['reason'] != case.expected_reason:
        behavior.append('expected_status_or_reason')
    if output['status'] == 'completed':
        if output['total_units'] not in case.allowed_units or output['candidate']['material_id'] != case.material_id:
            behavior.append('expected_cost_or_material')
    if case.expected_status == 'needs_input':
        if output['missing_fields'] != case.omit or bundle['database']['exists'] or events or bundle['decisions']:
            behavior.append('input_guard_zero_business')
    expected_decisions = {e['event_id'] for e in events if e['name'] == 'planner' and e['phase'] == 'started'}
    if {d['event_id'] for d in bundle['decisions']} != expected_decisions:
        errors.append('decision_observation_coverage')
    if any(d['memory']['deadline_at'] != bundle['input']['deadline_at'] for d in bundle['decisions']):
        errors.append('observed_deadline')
    for decision in bundle['decisions']:
        state = {}
        for event in events:
            if event['event_id'] >= decision['event_id']:
                break
            state.update(event['state_patch'] or {})
        candidate = state.get('candidate_history', {}).get(str(state.get('current_revision')))
        artifact = state.get('script_artifacts', {}).get(candidate['script_input_hash']) if candidate else None
        script = {key: artifact[key] for key in ('script_id', 'title', 'source_ids')} if artifact else None
        memory = decision['memory']
        if memory['candidate'] != candidate or memory['script'] != script or memory['seen_material_ids'] != state.get('seen_material_ids', []):
            errors.append('observed_successful_results')
        fields = ('estimate_id', 'revision', 'total_units', 'total_minutes', 'feasible', 'budget_gap_units', 'deadline_gap_minutes')
        expected_quotes = {key: {field: quote[field] for field in fields}
                           for key, quote in state.get('estimate_history', {}).items()}
        actual_quotes = {quote['estimate_id']: quote for quote in memory['evaluated_quotes']}
        if actual_quotes != expected_quotes or len(actual_quotes) != len(memory['evaluated_quotes']):
            errors.append('observed_historical_quotes')
    if case.replan:
        adjusted = False
        for decision in bundle['decisions']:
            quote = decision['memory']['latest_estimate']
            response = decision['response'] or {}
            if not quote or quote['total_units'] != 12 or quote['feasible']:
                continue
            gap = quote['budget_gap_units'] if case.replan == 'budget' else quote['deadline_gap_minutes']
            if gap <= 0:
                continue
            for call in response.get('tool_calls', []):
                arguments = json.loads(call['function']['arguments'])
                if call['function']['name'] == 'revise_plan' and arguments.get('production_mode') == 'basic':
                    adjusted |= any(r['tool_call_id'] == call['id'] and r['tool'] == 'revise_plan' and r['ok']
                                    for r in output['tool_results'])
        if not adjusted or output['status'] != 'completed' or output['total_units'] != 8 or output['current_revision'] < 2:
            behavior.append('observed_gap_then_model_replan_reestimate_save')
    quotes = [r['data'] for r in output['tool_results'] if r['tool'] == 'estimate_cost' and r['ok']]
    if case.budget_gap is not None and common['minimum_budget_gap_units'] != case.budget_gap:
        behavior.append('minimum_budget_gap')
    if case.deadline_gap is not None:
        smallest = min((q['deadline_gap_minutes'] for value in quotes for q in [value, *value['alternatives']]), default=None)
        if smallest != case.deadline_gap:
            behavior.append('minimum_deadline_gap')
    if case.exact_deadline and (output['saved_plan'] or {}).get('estimated_finish_at') != bundle['input']['deadline_at']:
        behavior.append('exact_deadline_boundary')
    if case.fault:
        if not bundle['fault_log']:
            behavior.append('fault_not_injected')
        if case.fault in {'script_once', 'script_always', 'save_once'}:
            tool = 'save_plan' if case.fault == 'save_once' else 'generate_script'
            code = 'SAVE_FAILED' if tool == 'save_plan' else 'SCRIPT_MODEL_UNAVAILABLE'
            failures = [r for r in output['tool_results'] if r['tool'] == tool and not r['ok'] and r['error']['code'] == code]
            failure_ids = {r['tool_call_id'] for r in failures}
            saw_error = any((d['memory']['last_observation'] or {}).get('tool_call_id') in failure_ids
                            and ((d['memory']['last_observation'] or {}).get('error') or {}).get('code') == code
                            for d in bundle['decisions'])
            if not failures or not saw_error:
                behavior.append('failure_not_observed')
            if case.fault != 'script_always' and len(failures) != 1:
                behavior.append('single_failure_expected')
            if not any(r['tool'] == 'search_materials' and r['ok'] and r['data']['materials'] for r in output['tool_results']):
                behavior.append('retained_search_missing')
            if case.fault == 'save_once' and not any(e['kind'] == 'save_transaction_failure'
                    and e['plan_rows_at_failure'] == 0 for e in bundle['fault_log']):
                behavior.append('save_failure_rollback_not_proven')
    if case.followup:
        follow = bundle.get('followup') or {}
        if follow.get('kind') != case.followup:
            behavior.append('followup_missing')
        elif case.followup == 'resume':
            if follow['initial']['status'] != 'incomplete' or follow['initial']['reason'] != 'MODEL_UNAVAILABLE' or follow['before']['plans']:
                behavior.append('initial_interruption_not_proven')
            if not any(e['kind'] == 'planner_failure' for e in bundle['fault_log']):
                behavior.append('planner_fault_missing')
            if not all(e in events for e in follow['before']['events']):
                errors.append('resume_changed_previous_events')
            errors += schema_trace_errors({'output': follow['initial'], 'events': follow['before']['events'],
                                           'trace': follow['trace']})
        else:
            if follow['before'] != follow['after'] or follow['provider_before'] != follow['provider_after']:
                behavior.append('followup_not_read_only')
            if case.followup == 'duplicate' and follow['result'] != follow['initial']:
                behavior.append('duplicate_result_changed')
            if case.followup == 'conflict' and (follow['result']['status'] != 'needs_input'
                    or follow['result']['reason'] != 'REQUEST_CONFLICT' or follow['original_after'] != follow['initial']):
                behavior.append('conflict_changed_original')
    state, retained = {}, {}
    for event in events:
        patch = event['state_patch'] or {}
        if 'seen_material_ids' in patch and not set(state.get('seen_material_ids', [])) <= set(patch['seen_material_ids']):
            errors.append('retained_materials')
        for field in ('candidate_history', 'script_artifacts', 'estimate_history'):
            if field in patch and any(key not in patch[field] or patch[field][key] != value
                                      for key, value in retained.get(field, {}).items()):
                errors.append('retained_' + field)
            if field in patch:
                retained[field] = deepcopy(patch[field])
        state.update(patch)
    starts = sum(e['kind'] == 'model' and e['phase'] == 'started' for e in events)
    actions = sum(e['kind'] in {'tool', 'control'} and e['phase'] == 'started' for e in events)
    if output['usage']['model_requests'] != starts or output['usage']['action_calls'] != actions:
        errors.append('actual_usage_counts')
    if output['limits']['remaining_model_requests'] != max(0, 32 - starts) or output['limits']['remaining_action_calls'] != max(0, 24 - actions):
        errors.append('remaining_quotas')
    return {'case_id': case.case_id, 'label': case.label, 'invariants_pass': not errors,
            'behavior_pass': not behavior, 'errors': errors, 'behavior_errors': behavior,
            'passed': not errors and not behavior, 'status': output['status'], 'reason': output['reason'],
            'total_units': output['total_units'], 'plan_rows': len(bundle['plans']),
            'trace_rows': len(bundle['trace']), 'decision_count': len(bundle['decisions']),
            'content_review': 'NON_BLOCKING: marketing copy outside this core rubric'}


def run_suite_case(case, model, *, folder, clock=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    database = folder / 'runtime.db'
    clock = clock or FixedClock(datetime.now(timezone.utc))
    request = {'request_id': case.case_id + '-' + uuid.uuid4().hex[:12], 'topic': case.topic,
               'budget_units': case.budget, 'deadline_at': (clock.now() + timedelta(minutes=case.deadline_minutes)).isoformat()}
    for field in case.omit:
        request.pop(field)
    scenario = {**case.model_dump(mode='json'), 'clock_at': clock.now().isoformat(),
                'entry': 'given_initial_state' if case.seed_premium else 'service.run_task',
                'fixture_origin': 'fixture_setup' if case.seed_premium else None}
    write_json(folder / 'scenario.json', scenario)
    write_json(folder / 'input.json', request)
    catalog = load_catalog()
    source = FaultSource(model, case.fault, database, request['request_id'])
    observed = SuiteObserver(source, database, request['request_id'], folder)
    followup = None
    try:
        if case.seed_premium:
            output = run_seeded(request, catalog, observed, clock, database)
        else:
            output = run_task(request, database=database, model=observed, clock=clock,
                              backend='mock' if model.model_id == 'mock' else 'deepseek')
        if case.followup:
            before = database_snapshot(database, request['request_id'])
            followup = {'kind': case.followup, 'initial': deepcopy(output), 'before': before,
                        'provider_before': provider_attempts(model)}
            if case.followup == 'resume':
                directory = folder / 'phases/initial'
                export_task(output, database=database, directory=directory)
                followup['trace'] = [json.loads(line) for line in (directory / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
                output = resume_task(request['request_id'], database=database, model=observed, clock=clock)
                followup['result'] = deepcopy(output)
            else:
                repeated = {**request, 'budget_units': 5} if case.followup == 'conflict' else request
                followup['result'] = run_task(repeated, database=database, model=observed, clock=clock,
                                              backend='mock' if model.model_id == 'mock' else 'deepseek')
                followup['original_after'] = show_task(request['request_id'], database=database)
                export_task(followup['result'], database=database, directory=folder / 'phases' / case.followup)
            followup['after'] = database_snapshot(database, request['request_id'])
            followup['provider_after'] = provider_attempts(model)
            write_json(folder / 'followup.json', followup)
    finally:
        source.cleanup()
    output = export_task(output, database=database, directory=folder)
    snapshot = database_snapshot(database, request['request_id'])
    trace = [json.loads(line) for line in (folder / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    bundle = {'input': request, 'scenario': scenario, 'output': output, 'database': snapshot,
              'events': snapshot['events'], 'plans': snapshot['plans'], 'trace': trace,
              'decisions': observed.decisions, 'script_attempts': observed.script_attempts, 'fault_log': source.log,
              'followup': followup,
              'catalog': {'materials': [m.model_dump(mode='json') for m in catalog.materials],
                          'pricing': catalog.pricing.model_dump(mode='json')}}
    write_json(folder / 'evidence.json', bundle)
    verdict = assess_case(case, bundle)
    write_json(folder / 'assessment.json', verdict)
    return bundle, verdict


def reassess_run(folder):
    folder = Path(folder)
    cases = [Case.model_validate(value) for value in json.loads((folder / 'cases.json').read_text(encoding='utf-8'))]
    verdicts = []
    for case in cases:
        path = folder / case.case_id / 'evidence.json'
        verdict = {'case_id': case.case_id, 'passed': False, 'invariants_pass': False,
                   'behavior_pass': False, 'errors': [], 'behavior_errors': []}
        if path.exists():
            try:
                stored = json.loads(path.read_text(encoding='utf-8'))
                verdict = assess_case(case, stored)
                # Re-read real exported files and SQLite rather than trusting the bundle alone.
                actual_output = json.loads((path.parent / 'output.json').read_text(encoding='utf-8'))
                actual_trace = [json.loads(line) for line in (path.parent / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
                actual_database = database_snapshot(path.parent / 'runtime.db', stored['input']['request_id'])
                if actual_output != stored['output'] or actual_trace != stored['trace'] or actual_database != stored['database']:
                    verdict['errors'].append('artifact_sqlite_snapshot_mismatch')
                    verdict['invariants_pass'] = verdict['passed'] = False
            except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as error:
                verdict['errors'].append('ARTIFACT_READ_ERROR:' + type(error).__name__)
                verdict['invariants_pass'] = verdict['passed'] = False
        else:
            verdict['errors'].append('EVIDENCE_MISSING')
        write_json(folder / case.case_id / 'final-assessment.json', verdict)
        verdicts.append(verdict)
    final = {'evaluation_standard': 'core20-rubric-v1', 'assessments': verdicts,
             'passed_cases': sum(v['passed'] for v in verdicts), 'total_cases': len(cases),
             'passed': len(cases) == 20 and all(v['passed'] for v in verdicts),
             'marketing_copy': 'NON_BLOCKING', 'reassessment_http_requests': 0}
    write_json(folder / 'final-assessment.json', final)
    return final


def main(argv=None):
    import argparse
    import getpass
    import subprocess
    from content_planner.deepseek import DeepSeekModelClient
    from content_planner.domain import Fault

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--key-stdin', action='store_true', help='Read credential through a hidden terminal prompt')
    parser.add_argument('--output-root', type=Path, default=Path('examples/live/core20'))
    parser.add_argument('--recheck', type=Path, help='Only recheck existing artifacts; zero HTTP')
    args = parser.parse_args(argv)
    if args.recheck:
        final = reassess_run(args.recheck)
        print(json.dumps({'passed': final['passed'], 'passed_cases': final['passed_cases'], 'http_requests': 0}))
        return 0 if final['passed'] else 3
    if not args.live or not args.key_stdin:
        parser.error('--live and --key-stdin are required; no HTTP calls made')
    cases = load_cases()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    folder = args.output_root.resolve() / run_id
    folder.mkdir(parents=True, exist_ok=False)
    files = [*ROOT.glob('src/content_planner/*.py'),
             *(ROOT / 'src/content_planner/data' / name for name in
               ('materials.json', 'pricing.json', 'aliases.json', 'mock-scenario.json')),
             Path(__file__), ROOT / 'scripts/evaluate_budget.py', CASES, ROOT / 'requirements.lock',
             *(ROOT / 'docs' / name for name in ('01-requirements.md', '02-solution.md', '03-evaluation.md',
                                                  '04-ai-usage.md', '05-retrospective.md')),
             *(ROOT / 'contracts' / name for name in ('common.schema.json', 'request.schema.json',
                  'result.schema.json', 'trace-event.schema.json', 'tools.json', 'fixtures/materials.json',
                  'fixtures/pricing.json', 'fixtures/aliases.json'))]
    source = {'sha256': {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in files}}
    for field, command in [('commit', ['rev-parse', 'HEAD']), ('status', ['status', '--porcelain'])]:
        try:
            result = subprocess.run(['git', '-c', f'safe.directory={ROOT.as_posix()}', *command], cwd=ROOT,
                                    capture_output=True, text=True, encoding='utf-8')
        except OSError as error:
            raise RuntimeError(f'Git {field} unavailable') from error
        if result.returncode != 0 or (field == 'commit' and not result.stdout.strip()):
            raise RuntimeError(f'Git {field} unavailable')
        source[field] = result.stdout.strip()
    write_json(folder / 'source.json', source)
    write_json(folder / 'cases.json', [case.model_dump(mode='json') for case in cases])
    summary = {'run_id': run_id, 'started_at': datetime.now(timezone.utc).isoformat(),
               'evaluation_standard': 'core20-rubric-v1', 'backend': 'deepseek', 'model': 'deepseek-v4-pro',
               'samples_per_case': 1, 'cases': [], 'http_attempts': 0, 'api_cost_usd': None,
               'marketing_copy': 'NON_BLOCKING', 'parameters': {'temperature': 0, 'thinking': 'disabled',
               'planner_max_tokens': 2048, 'script_max_tokens': 1536}}
    write_json(folder / 'summary.json', summary)
    key = getpass.getpass('DeepSeek API key (hidden): ')
    try:
        with DeepSeekModelClient(api_key=key) as model:
            key = None
            for case in cases:
                print(f'{case.case_id} START {case.label}', flush=True)
                tick, before = time.monotonic(), model.http_attempts
                try:
                    bundle, verdict = run_suite_case(case, model, folder=folder / case.case_id)
                    row = {**verdict, 'request_id': bundle['input']['request_id'],
                           'usage': bundle['output']['usage'], 'fault_count': len(bundle['fault_log']),
                           'entry': bundle['scenario']['entry']}
                except Exception as error:
                    row = {'case_id': case.case_id, 'label': case.label, 'passed': False,
                           'invariants_pass': False, 'behavior_pass': False, 'error_type': type(error).__name__}
                    write_json(folder / case.case_id / 'evaluator-error.json', row)
                row.update(http_attempts=model.http_attempts - before, elapsed_seconds=round(time.monotonic() - tick, 3))
                summary['cases'].append(row)
                summary['http_attempts'] = model.http_attempts
                summary['passed_cases'] = sum(item['passed'] for item in summary['cases'])
                summary['passed'] = len(summary['cases']) == 20 and summary['passed_cases'] == 20
                write_json(folder / 'summary.json', summary)
                write_json(folder / case.case_id / 'run.json', row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                if row.get('reason') in {'AUTH_ERROR', 'MODEL_CONFIG_ERROR'}:
                    break
    except Fault as error:
        summary['error'] = {'code': error.code}
    finally:
        key = None
        summary['ended_at'] = datetime.now(timezone.utc).isoformat()
        write_json(folder / 'summary.json', summary)
    final = reassess_run(folder)
    print(json.dumps({'report': str(folder), 'passed_cases': final['passed_cases'], 'total_cases': 20,
                      'http_attempts': summary['http_attempts']}, ensure_ascii=False), flush=True)
    return 0 if final['passed'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
