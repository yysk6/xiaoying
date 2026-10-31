from pathlib import Path
import pytest


def test_twenty_cases_have_fixed_distinct_ids_and_cover_the_reference_and_guards():
    from scripts.evaluate_core20 import load_cases
    cases = load_cases()
    assert [c.case_id for c in cases] == [f'E{i:02}' for i in range(1, 21)]
    assert cases[3].budget == 10 and cases[3].seed_premium and cases[3].replan == 'budget'
    assert sum(c.expected_status == 'needs_input' for c in cases) == 4
    assert sum(c.seed_premium for c in cases) == 6


def test_normal_case_audits_actual_trace_and_rejects_a_changed_phase(tmp_path):
    from scripts.evaluate_core20 import load_cases, run_suite_case, assess_case, FixedClock
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock as TestClock
    from content_planner.model import FakeModelClient
    case = load_cases()[0]
    bundle, verdict = run_suite_case(case, FakeModelClient([DRAFT], decisions=NORMAL),
                                    folder=tmp_path / 'E01', clock=FixedClock(TestClock().now()))
    assert verdict['passed'], verdict
    bundle['trace'][0]['phase'] = 'succeeded'
    assert not assess_case(case, bundle)['invariants_pass']


def test_reference_case_requires_an_observed_initial_quote_before_model_replanning(tmp_path):
    from scripts.evaluate_core20 import load_cases, run_suite_case, assess_case, FixedClock
    from tests.acceptance.test_cli import DRAFT, FixedClock as TestClock, call
    from tests.unit.test_evaluation import finish
    from content_planner.model import FakeModelClient
    model = FakeModelClient([DRAFT], decisions=[call('revise_plan', 'basic', material_id='M01',
        creative_brief='展示字幕编辑', production_mode='basic'), *finish(2)])
    case = load_cases()[3]
    bundle, verdict = run_suite_case(case, model, folder=tmp_path / 'E04', clock=FixedClock(TestClock().now()))
    assert verdict['passed'], verdict
    bundle['decisions'] = []
    verdict = assess_case(case, bundle)
    assert not verdict['passed']


def test_once_failed_script_is_observed_and_retried_without_losing_success(tmp_path):
    from scripts.evaluate_core20 import load_cases, run_suite_case, assess_case
    from tests.acceptance.test_cli import DRAFT, SEARCH, REVISE, FixedClock, call
    from tests.unit.test_evaluation import finish
    from content_planner.model import FakeModelClient
    model = FakeModelClient([DRAFT], decisions=[SEARCH, REVISE,
        call('generate_script', 'first', plan_revision=1), call('generate_script', 'second', plan_revision=1), *finish()])
    case = load_cases()[14]
    bundle, verdict = run_suite_case(case, model, folder=tmp_path / 'E15', clock=FixedClock())
    assert verdict['passed'], verdict
    steps = [step for step in bundle['output']['execution_steps'] if step['tool'] == 'generate_script']
    assert [s['status'] for s in steps] == ['failed', 'succeeded']
    assert len(model.requests) == 1 and len(bundle['fault_log']) == 1
    bundle['fault_log'] = []
    assert not assess_case(case, bundle)['behavior_pass']


def test_interrupted_model_can_resume_with_the_same_successful_prefix(tmp_path):
    from scripts.evaluate_core20 import load_cases, run_suite_case, assess_case
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock
    from content_planner.model import FakeModelClient
    case = load_cases()[17]
    bundle, verdict = run_suite_case(case, FakeModelClient([DRAFT], decisions=NORMAL),
                                    folder=tmp_path / 'E18', clock=FixedClock())
    assert verdict['passed'], verdict
    assert bundle['followup']['initial']['reason'] == 'MODEL_UNAVAILABLE'
    assert bundle['output']['usage']['model_requests'] == 7
    assert len([s for s in bundle['output']['execution_steps'] if s['tool'] == 'search_materials']) == 1
    bundle['followup']['initial']['status'] = 'completed'
    assert not assess_case(case, bundle)['passed']


def test_real_save_transaction_fails_once_then_commits_once(tmp_path):
    from scripts.evaluate_core20 import load_cases, run_suite_case, assess_case
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock, call
    from content_planner.model import FakeModelClient
    import hashlib
    again = call('save_plan', 'save-again', plan_revision=1,
                 estimate_id='estimate_' + hashlib.sha256(b'estimate').hexdigest())
    bundle, verdict = run_suite_case(load_cases()[16], FakeModelClient([DRAFT], decisions=[*NORMAL, again]),
                                    folder=tmp_path / 'E17', clock=FixedClock())
    assert verdict['passed'], verdict
    saves = [s for s in bundle['output']['execution_steps'] if s['tool'] == 'save_plan']
    assert [s['status'] for s in saves] == ['failed', 'succeeded']
    assert bundle['fault_log'] == [{'kind': 'save_transaction_failure', 'tool_call_id': 'save',
                                   'plan_rows_at_failure': 0, 'trigger_removed': True}]
    observed_error = next(d for d in bundle['decisions'] if (d['memory']['last_observation'].get('error') or {}).get('code') == 'SAVE_FAILED')
    observed_error['memory']['last_observation']['ok'] = True
    assert not assess_case(load_cases()[16], bundle)['invariants_pass']


def test_persistent_script_fault_stops_without_erasing_success(tmp_path):
    from scripts.evaluate_core20 import load_cases, run_suite_case
    from tests.acceptance.test_cli import SEARCH, REVISE, FixedClock, call
    from content_planner.model import FakeModelClient
    decisions = [SEARCH, REVISE, call('generate_script', 'first', plan_revision=1),
        call('generate_script', 'retry', plan_revision=1), call('stop_task', 'stop', reason='tool_failure', message='脚本服务持续不可用')]
    bundle, verdict = run_suite_case(load_cases()[15], FakeModelClient([], decisions=decisions),
                                    folder=tmp_path / 'E16', clock=FixedClock())
    assert verdict['passed'], verdict
    assert len(bundle['plans']) == 0 and len(bundle['fault_log']) == 2


@pytest.mark.parametrize('index', [10, 11, 12, 13])
def test_missing_or_expired_inputs_do_not_create_a_business_database(tmp_path, index):
    from scripts.evaluate_core20 import load_cases, run_suite_case
    from tests.acceptance.test_cli import FixedClock
    from content_planner.model import FakeModelClient
    model = FakeModelClient([])
    _, verdict = run_suite_case(load_cases()[index], model, folder=tmp_path / 'guard', clock=FixedClock())
    assert verdict['passed'], verdict
    assert not model.requests and not model.decision_requests


@pytest.mark.parametrize('index', [18, 19])
def test_duplicate_or_conflicting_followup_preserves_database_and_api_counts(tmp_path, index):
    from scripts.evaluate_core20 import load_cases, run_suite_case, assess_case
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock
    from content_planner.model import FakeModelClient
    case = load_cases()[index]
    bundle, verdict = run_suite_case(case, FakeModelClient([DRAFT], decisions=NORMAL),
                                    folder=tmp_path / case.case_id, clock=FixedClock())
    assert verdict['passed'], verdict
    bundle['followup']['provider_after'] += 1
    assert not assess_case(case, bundle)['behavior_pass']


def test_malformed_trace_is_a_failed_verdict_instead_of_an_exception(tmp_path):
    from scripts.evaluate_core20 import load_cases, run_suite_case, assess_case
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock
    from content_planner.model import FakeModelClient
    case = load_cases()[0]
    bundle, _ = run_suite_case(case, FakeModelClient([DRAFT], decisions=NORMAL), folder=tmp_path / 'E01', clock=FixedClock())
    bundle['trace'][0]['observation_summary'] = 'malformed'
    assert not assess_case(case, bundle)['passed']


def test_recheck_reports_a_corrupted_physical_trace_without_crashing(tmp_path):
    from scripts.evaluate_core20 import load_cases, run_suite_case, reassess_run
    from scripts.evaluate_budget import write_json
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock
    from content_planner.model import FakeModelClient
    case = load_cases()[0]
    run_suite_case(case, FakeModelClient([DRAFT], decisions=NORMAL), folder=tmp_path / 'E01', clock=FixedClock())
    write_json(tmp_path / 'cases.json', [case.model_dump(mode='json')])
    (tmp_path / 'E01/trace.jsonl').write_text('corrupted\n', encoding='utf-8')
    result = reassess_run(tmp_path)
    assert not result['assessments'][0]['invariants_pass']


def test_paid_runner_requires_both_explicit_flags_before_reading_credentials(tmp_path, monkeypatch):
    from scripts.evaluate_core20 import main
    import getpass
    def forbidden(prompt):
        raise AssertionError('Credential prompt must not run')
    monkeypatch.setattr(getpass, 'getpass', forbidden)
    with pytest.raises(SystemExit) as error:
        main(['--output-root', str(tmp_path / 'results')])
    assert error.value.code == 2 and not (tmp_path / 'results').exists()


def test_live_runner_records_current_sources_before_credential_prompt(tmp_path, monkeypatch):
    import getpass
    import hashlib
    import json
    from pathlib import Path
    from scripts.evaluate_core20 import main

    class PromptReached(Exception):
        pass

    def stop_at_prompt(prompt):
        raise PromptReached

    monkeypatch.setattr(getpass, 'getpass', stop_at_prompt)
    with pytest.raises(PromptReached):
        main(['--live', '--key-stdin', '--output-root', str(tmp_path)])

    source = json.loads(next(tmp_path.glob('*/source.json')).read_text(encoding='utf-8'))
    hashes = {name.replace('\\', '/'): value for name, value in source['sha256'].items()}
    root = Path(__file__).resolve().parents[2]
    required = ['docs/01-requirements.md', 'docs/02-solution.md', 'docs/03-evaluation.md',
                'docs/04-ai-usage.md', 'docs/05-retrospective.md',
                'contracts/request.schema.json', 'contracts/result.schema.json',
                'contracts/trace-event.schema.json', 'contracts/common.schema.json',
                'contracts/tools.json', 'contracts/fixtures/materials.json',
                'contracts/fixtures/pricing.json', 'contracts/fixtures/aliases.json',
                'src/content_planner/data/materials.json', 'src/content_planner/data/pricing.json',
                'src/content_planner/data/aliases.json']
    for name in required:
        assert hashes[name] == hashlib.sha256((root / name).read_bytes()).hexdigest()
    assert 'docs/12-core20-evaluation.md' not in hashes
    assert source['commit'] and source['status'] is not None


def test_live_runner_missing_required_source_fails_before_credential_prompt(tmp_path, monkeypatch):
    import getpass
    from pathlib import Path
    from scripts.evaluate_core20 import main

    original_read = Path.read_bytes

    def read_bytes(path):
        if path.name == '03-evaluation.md':
            raise FileNotFoundError(str(path))
        return original_read(path)

    def forbidden_prompt(prompt):
        raise AssertionError('Credential prompt must not run')

    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    monkeypatch.setattr(getpass, 'getpass', forbidden_prompt)
    with pytest.raises(FileNotFoundError, match='03-evaluation.md'):
        main(['--live', '--key-stdin', '--output-root', str(tmp_path)])


def test_live_runner_missing_packaged_data_fails_before_credential_prompt(tmp_path, monkeypatch):
    import getpass
    from pathlib import Path
    from scripts.evaluate_core20 import main

    original_glob, original_read = Path.glob, Path.read_bytes

    def glob(path, pattern):
        return (item for item in original_glob(path, pattern) if item.as_posix().endswith('/data/materials.json') is False)

    def read_bytes(path):
        if path.as_posix().endswith('/data/materials.json'):
            raise FileNotFoundError(str(path))
        return original_read(path)

    def forbidden_prompt(prompt):
        raise AssertionError('Credential prompt must not run')

    monkeypatch.setattr(Path, 'glob', glob)
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    monkeypatch.setattr(getpass, 'getpass', forbidden_prompt)
    with pytest.raises(FileNotFoundError, match='materials.json'):
        main(['--live', '--key-stdin', '--output-root', str(tmp_path)])


def test_live_runner_requires_git_source_before_credential_prompt(tmp_path, monkeypatch):
    import getpass
    import subprocess
    from scripts.evaluate_core20 import main

    def failed_git(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, '', 'git unavailable')

    def forbidden_prompt(prompt):
        raise AssertionError('Credential prompt must not run')

    monkeypatch.setattr(subprocess, 'run', failed_git)
    monkeypatch.setattr(getpass, 'getpass', forbidden_prompt)
    with pytest.raises(RuntimeError, match='Git'):
        main(['--live', '--key-stdin', '--output-root', str(tmp_path)])


@pytest.mark.parametrize('damage', ['steps', 'request', 'memory'])
def test_rejects_missing_steps_mismatched_database_input_or_lost_observation(tmp_path, damage):
    from scripts.evaluate_core20 import load_cases, run_suite_case, assess_case
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock
    from content_planner.model import FakeModelClient
    case = load_cases()[0]
    bundle, verdict = run_suite_case(case, FakeModelClient([DRAFT], decisions=NORMAL),
                                    folder=tmp_path / 'E01', clock=FixedClock())
    assert verdict['passed'], verdict
    if damage == 'steps':
        bundle['output']['execution_steps'] = []
    elif damage == 'request':
        bundle['database']['request']['budget_units'] = 999
    else:
        for decision in bundle['decisions']:
            decision['memory'].update(candidate=None, script=None, seen_material_ids=[])
    assert not assess_case(case, bundle)['invariants_pass']
