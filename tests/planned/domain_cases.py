from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError
from content_planner.contracts import Request, ScriptDraft
from content_planner.domain import input_hash, quote, validate_script, Fault


NOW = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)


def request(**overrides):
    return Request.model_validate({"request_id": "a", "topic": "字幕推广", "budget_units": 10,
        "deadline_at": "2026-10-29T05:00:00Z", **overrides})


@pytest.mark.parametrize("budget", [True, 0, -1, 10.5, "10", 10.0])
def test_budget_is_strict_positive_integer(budget):
    with pytest.raises(ValidationError):
        request(budget_units=budget)


@pytest.mark.parametrize("deadline", ["2026-10-29T05:00:00", "2026-13-99T00:00:00Z"])
def test_deadline_requires_valid_offset(deadline):
    with pytest.raises(ValidationError):
        request(deadline_at=deadline)


def test_equivalent_time_and_different_request_id_have_same_input_hash():
    assert input_hash(request()) == input_hash(request(request_id="b", deadline_at="2026-10-29T13:00:00+08:00"))


def test_quote_and_exact_boundary():
    pricing = {"script_finalize": {"fee_units": 2, "duration_minutes": 20},
        "video_edit": {"basic": {"fee_units": 4, "duration_minutes": 45},
                       "premium": {"fee_units": 8, "duration_minutes": 90}},
        "review": {"fee_units": 1, "duration_minutes": 15}}
    material = {"material_id": "M01", "fee_units": 1, "lead_minutes": 10}
    req = request(budget_units=8, deadline_at=(NOW + timedelta(minutes=90)).isoformat()).model_dump(mode="json")
    result = quote(req, material, pricing, "basic", NOW)
    assert result["total_units"] == 8 and result["total_minutes"] == 90
    assert result["feasible"]
    late = quote(req, material, pricing, "premium", NOW)
    assert not late["feasible"]
    assert late["budget_gap_units"] == 4 and late["deadline_gap_minutes"] == 45


def test_script_rejects_unsupported_percentage_and_source():
    draft = ScriptDraft(title="标题", hook="开头", body="效率提升80%", cta="试用", source_ids=["M01"])
    with pytest.raises(Fault, match="SCRIPT_INVALID"):
        validate_script(draft, {"material_id": "M01", "facts": ["支持字幕"]})
    draft.body = "支持字幕"
    draft.source_ids = ["M02"]
    with pytest.raises(Fault, match="SCRIPT_INVALID"):
        validate_script(draft, {"material_id": "M01", "facts": ["支持字幕"]})
