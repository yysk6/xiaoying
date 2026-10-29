import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys

import pytest

from content_planner.contracts import Request, ScriptDraft
from content_planner import domain


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)


class FixedClock:
    def __init__(self, value=NOW):
        self.value = value

    def now(self):
        return self.value


def request(**overrides):
    return Request.model_validate({"request_id": "a", "topic": "字幕推广", "budget_units": 10,
                                   "deadline_at": "2026-10-29T05:00:00Z", **overrides})


@pytest.fixture
def materials():
    return json.loads((ROOT / "contracts/fixtures/materials.json").read_text(encoding="utf-8"))["materials"]


@pytest.fixture
def pricing():
    return json.loads((ROOT / "contracts/fixtures/pricing.json").read_text(encoding="utf-8"))


def test_complete_request_is_returned():
    req = request()
    assert domain.require_complete(req, FixedClock()) is req


def test_equivalent_time_and_different_id_have_same_input_hash():
    assert domain.input_hash(request()) == domain.input_hash(
        request(request_id="b", deadline_at="2026-10-29T13:00:00+08:00"))


@pytest.mark.parametrize("mode,units,minutes", [("basic", 8, 90), ("premium", 12, 135)])
def test_quote_totals_from_fixture(materials, pricing, mode, units, minutes):
    for material in materials:
        result = domain.quote(request(), material, pricing, mode, FixedClock())
        assert result["total_units"] == units
        assert result["total_minutes"] == minutes


def test_script_rejects_wrong_source(materials):
    draft = ScriptDraft(title="标题", hook="开头", body="支持字幕", cta="试用", source_ids=["M01"])
    assert domain.validate_script(draft, materials[0]) is None
    draft.source_ids = ["M02"]
    with pytest.raises(domain.Fault, match="SCRIPT_INVALID"):
        domain.validate_script(draft, materials[0])


@pytest.mark.parametrize("fields", [
    ("topic",), ("budget_units",), ("deadline_at",), ("topic", "deadline_at"),
    ("topic", "budget_units", "deadline_at"),
])
@pytest.mark.parametrize("explicit_null", [False, True])
def test_missing_fields_are_reported_in_contract_order(fields, explicit_null):
    payload = request().model_dump()
    for field in fields:
        if explicit_null:
            payload[field] = None
        else:
            del payload[field]
    req = Request.model_validate(payload)
    assert req.missing_fields == list(fields)
    with pytest.raises(domain.Fault) as error:
        domain.require_complete(req, FixedClock())
    assert error.value.code == "NEEDS_INPUT"
    assert error.value.details == {"missing_fields": list(fields)}


@pytest.mark.parametrize("delta", [timedelta(microseconds=-1), timedelta(0), timedelta(days=-1)])
def test_new_request_deadline_must_be_after_clock(delta):
    req = request(deadline_at=(NOW + delta).isoformat())
    with pytest.raises(domain.Fault) as error:
        domain.require_complete(req, FixedClock())
    assert error.value.code == "INVALID_ARGUMENT"
    assert error.value.details["field"] == "deadline_at"


def test_structure_and_hash_do_not_depend_on_current_time():
    req = request(deadline_at=NOW.isoformat())
    assert len(domain.input_hash(req)) == 64
    future = request(deadline_at=(NOW + timedelta(microseconds=1)).isoformat())
    assert domain.require_complete(future, FixedClock()) is future


def test_system_clock_returns_current_aware_utc():
    before = datetime.now(timezone.utc)
    actual = domain.SystemClock().now()
    after = datetime.now(timezone.utc)
    assert actual.utcoffset() == timedelta(0)
    assert before <= actual <= after


def test_input_hash_known_vector_and_unicode_normalization():
    assert domain.input_hash(request()) == "b4e45a05cdab6abbf2626a053891a690c1b3f99d3ab080672b276ff8fc80c02e"
    assert domain.input_hash(request(topic=" Cafe\u0301 ")) == domain.input_hash(request(topic="Café"))


@pytest.mark.parametrize("change", [
    {"topic": "裁剪推广"}, {"budget_units": 11}, {"deadline_at": "2026-10-29T06:00:00Z"},
])
def test_input_hash_changes_with_business_input(change):
    assert domain.input_hash(request(**change)) != domain.input_hash(request())


def test_hash_is_stable_in_another_process_and_cwd(tmp_path):
    code = ("import sys; sys.path.insert(0, sys.argv[1]); "
            "from content_planner.contracts import Request; "
            "from content_planner.domain import input_hash; "
            "print(input_hash(Request.model_validate_json(sys.argv[2])))")
    package_parent = Path(domain.__file__).resolve().parent.parent
    result = subprocess.run([sys.executable, "-c", code, str(package_parent), request().model_dump_json()],
                            cwd=tmp_path, env={**os.environ, "PYTHONHASHSEED": "91"},
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == domain.input_hash(request())


def candidate_hash(req, material, mode="basic", pricing_hash="a" * 64, brief="字幕演示"):
    return domain.candidate_hash(req, material, brief, mode, pricing_hash)


def script_hash(req, material, brief="字幕演示", model="mock", version="script-v1"):
    return domain.script_input_hash(req, material, brief, model_id=model, script_prompt_version=version)


def test_candidate_and_script_dependencies(materials):
    req, material = request(), materials[0]
    candidate, script = candidate_hash(req, material), script_hash(req, material)
    assert len(candidate) == len(script) == 64
    assert candidate_hash(req, material, mode="premium") != candidate
    assert candidate_hash(req, material, pricing_hash="b" * 64) != candidate
    assert candidate_hash(req, material, brief="片段演示") != candidate
    assert script_hash(req, material, brief="片段演示") != script
    assert script_hash(req, material, model="deepseek-v4-pro") != script
    assert script_hash(req, material, version="script-v2") != script
    assert script_hash(request(topic="新主题"), material) != script
    changed = deepcopy(material)
    changed["facts"].append("新事实")
    assert candidate_hash(req, changed) != candidate
    assert script_hash(req, changed) != script
    assert candidate_hash(req, materials[1]) != candidate
    assert script_hash(req, materials[1]) != script


def test_non_content_metadata_does_not_enter_fingerprints(materials):
    material = materials[0]
    observed = {**dict(reversed(list(material.items()))), "score": 5}
    req = request(request_id="another")
    assert candidate_hash(req, observed, brief=" 字幕演示 ") == candidate_hash(request(), material)
    assert script_hash(req, observed, brief=" 字幕演示 ") == script_hash(request(), material)
    # Script content does not consume budget/deadline/mode; candidates still do.
    assert script_hash(request(budget_units=20), material) == script_hash(request(), material)
    assert candidate_hash(request(budget_units=20), material) != candidate_hash(request(), material)
    assert script_hash(request(deadline_at="2026-10-30T05:00:00Z"), material) == script_hash(request(), material)


def test_quote_line_items_and_exact_boundaries(materials, pricing):
    result = domain.quote(request(budget_units=8, deadline_at=(NOW + timedelta(minutes=90)).isoformat()),
                          materials[0], pricing, "basic", FixedClock())
    assert result["line_items"] == [
        {"step_id": "material_prepare", "catalog_item_id": "M01", "fee_units": 1, "duration_minutes": 10},
        {"step_id": "script_finalize", "catalog_item_id": "script_finalize", "fee_units": 2, "duration_minutes": 20},
        {"step_id": "video_edit", "catalog_item_id": "video_edit:basic", "fee_units": 4, "duration_minutes": 45},
        {"step_id": "review", "catalog_item_id": "review", "fee_units": 1, "duration_minutes": 15},
    ]
    assert result["within_budget"] and result["within_deadline"] and result["feasible"]
    assert result["budget_gap_units"] == result["deadline_gap_minutes"] == 0
    assert result["quoted_at"] == NOW.isoformat()
    assert result["estimated_finish_at"] == (NOW + timedelta(minutes=90)).isoformat()


@pytest.mark.parametrize("budget,remaining,mode,gap,minutes", [
    (8, 90, "premium", 4, 45), (5, 180, "basic", 3, 0), (14, 100, "premium", 0, 35),
])
def test_quote_reports_constraint_gaps_without_changing_mode(materials, pricing, budget, remaining, mode, gap, minutes):
    result = domain.quote(request(budget_units=budget, deadline_at=(NOW + timedelta(minutes=remaining)).isoformat()),
                          materials[0], pricing, mode, FixedClock())
    assert result["budget_gap_units"] == gap
    assert result["deadline_gap_minutes"] == minutes
    assert result["within_budget"] == (gap == 0)
    assert result["within_deadline"] == (minutes == 0)
    assert result["feasible"] is False
    assert result["line_items"][2]["catalog_item_id"] == f"video_edit:{mode}"


@pytest.mark.parametrize("lateness,expected", [
    (timedelta(microseconds=1), 1), (timedelta(seconds=60), 1),
    (timedelta(seconds=60, microseconds=1), 2),
])
def test_deadline_gap_rounds_up(materials, pricing, lateness, expected):
    req = request(deadline_at=(NOW + timedelta(minutes=90) - lateness).isoformat())
    assert domain.quote(req, materials[0], pricing, "basic", FixedClock())["deadline_gap_minutes"] == expected


def test_quote_reads_clock_each_time_and_does_not_modify_inputs(materials, pricing):
    req = request(budget_units=8, deadline_at=(NOW + timedelta(minutes=90)).isoformat())
    original = deepcopy((req.model_dump(), materials[0], pricing))
    clock = FixedClock()
    assert domain.quote(req, materials[0], pricing, "basic", clock)["feasible"]
    clock.value += timedelta(seconds=1)
    later = domain.quote(req, materials[0], pricing, "basic", clock)
    assert not later["feasible"] and later["deadline_gap_minutes"] == 1
    assert original == (req.model_dump(), materials[0], pricing)


def test_quote_uses_supplied_data_instead_of_fixed_8_and_12(materials, pricing):
    material = {**materials[0], "fee_units": 3, "lead_minutes": 11}
    pricing["video_edit"]["basic"] = {"fee_units": 6, "duration_minutes": 50}
    result = domain.quote(request(), material, pricing, "basic", FixedClock())
    assert result["total_units"] == 12 and result["total_minutes"] == 96


def test_clock_offset_is_normalized_to_utc(materials, pricing):
    offset_clock = FixedClock(NOW.astimezone(timezone(timedelta(hours=8))))
    assert domain.quote(request(), materials[0], pricing, "basic", offset_clock) == domain.quote(
        request(), materials[0], pricing, "basic", FixedClock())


def draft(**overrides):
    return ScriptDraft.model_validate({"title": "标题", "hook": "开头", "body": "支持字幕",
                                      "cta": "试用", "source_ids": ["M01"], **overrides})


@pytest.mark.parametrize("field", ["title", "hook", "body", "cta"])
@pytest.mark.parametrize("text", ["效率提升80%", "效率提升80.5 %", "行业第一", "100%准确", "100 % 准确"])
def test_script_rejects_unsupported_percentages_and_banned_claims(materials, field, text):
    with pytest.raises(domain.Fault, match="SCRIPT_INVALID"):
        domain.validate_script(draft(**{field: text}), materials[0])


def test_percentage_comparison_uses_whole_number_tokens(materials):
    material = {**materials[0], "facts": ["测试数据包含180%及80.5 %。"]}
    assert domain.validate_script(draft(body="测试数据80.5%"), material) is None
    with pytest.raises(domain.Fault, match="SCRIPT_INVALID"):
        domain.validate_script(draft(body="测试数据80%"), material)
    with pytest.raises(domain.Fault, match="SCRIPT_INVALID"):
        domain.validate_script(draft(body="100%准确"), {**material, "facts": ["100%准确"]})


@pytest.mark.parametrize("raw", [
    "not JSON", "{}", "[]", '{"title": true}',
    '{"title":"t","hook":"h","body":"b","cta":"c","source_ids":["M02"]}',
    '{"title":"t","hook":"h","body":"80%","cta":"c","source_ids":["M01"]}',
    '{"title":"t","hook":"h","body":"b","cta":"c","source_ids":["M01"],"price":1}',
])
def test_parse_script_maps_json_structure_and_fact_errors(materials, raw):
    with pytest.raises(domain.Fault) as error:
        domain.parse_script(raw, materials[0])
    assert error.value.code == "SCRIPT_INVALID"


def test_parse_script_returns_valid_normalized_draft(materials):
    raw = draft(title=" Cafe\u0301 ").model_dump_json()
    result = domain.parse_script(raw, materials[0])
    assert result.title == "Café" and result.source_ids == ["M01"]
