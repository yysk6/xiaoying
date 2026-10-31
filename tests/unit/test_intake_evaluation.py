from scripts.evaluate_intake import assess_dialog


def test_dialog_assessment_requires_exact_fields_and_no_business_before_confirmation():
    expected = [{'state': 'ready', 'draft': {'topic': '字幕推广', 'budget_units': 10,
                                           'deadline_at': '2026-11-01T10:00:00+00:00'}}]
    records = [{'reply': expected[0], 'database': {'requests': 0, 'events': 0, 'plans': 0}}]
    assert assess_dialog(records, expected)['passed']
    records[0]['database']['requests'] = 1
    assert not assess_dialog(records, expected)['passed']
    records[0]['database']['requests'] = 0
    records[0]['reply'] = {'state': 'ready', 'draft': {**expected[0]['draft'], 'budget_units': 15}}
    assert not assess_dialog(records, expected)['passed']


def test_terminal_evaluation_can_audit_actual_business_exports_and_packaged_catalog(tmp_path):
    from scripts.evaluate_intake import assess_business
    from content_planner.model import FakeModelClient
    from content_planner.service import run_task, export_task
    from tests.acceptance.test_cli import DRAFT, NORMAL, FixedClock, request
    database = tmp_path / 'runtime.db'
    result = run_task(request(), database=database, model=FakeModelClient([DRAFT], decisions=NORMAL), clock=FixedClock())
    export_task(result, database=database, directory=tmp_path / 'runs/nl-test')
    verdict = assess_business(tmp_path, 'N-A01', request())
    assert verdict['invariants_pass'] and verdict['behavior_pass']
    assert verdict['plan_rows'] == 1
    for changed in ({'budget_units': 8}, {'request_id': 'wrong-id'}):
        verdict = assess_business(tmp_path, 'N-A01', confirmed_request={**request(), **changed})
        assert not verdict['invariants_pass'] and 'confirmed_request_mismatch' in verdict['errors']
