import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from content_planner.contracts import Request, ScriptDraft


ROOT = Path(__file__).resolve().parents[2]
VALID = {"request_id": "a", "topic": "字幕推广", "budget_units": 10,
         "deadline_at": "2026-10-29T05:00:00Z"}
DRAFT = {"title": "标题", "hook": "开头", "body": "支持字幕", "cta": "试用",
         "source_ids": ["M01"]}


def test_valid_request_and_optional_business_fields():
    assert Request.model_validate(VALID).budget_units == 10
    request = Request(request_id="a")
    assert request.topic is request.budget_units is request.deadline_at is None


@pytest.mark.parametrize("budget", [True, False, 0, -1, 10.5, "10", 10.0, 100001])
def test_budget_is_strict_positive_integer(budget):
    with pytest.raises(ValidationError) as error:
        Request.model_validate({**VALID, "budget_units": budget})
    assert error.value.errors()[0]["loc"] == ("budget_units",)


@pytest.mark.parametrize("budget", [1, 100000])
def test_budget_endpoints_are_valid(budget):
    assert Request.model_validate({**VALID, "budget_units": budget}).budget_units == budget


@pytest.mark.parametrize("deadline", [
    "2026-10-29T05:00:00", "2026-13-99T00:00:00Z", "2026-02-29T00:00:00Z",
    "2026-10-29", "2026-10-29 05:00:00Z", "2026-10-29T05:00:00+24:00",
    "2026-10-29T05:00:00+01:99", 1793250000,
])
def test_deadline_requires_real_date_and_explicit_offset(deadline):
    with pytest.raises(ValidationError):
        Request.model_validate({**VALID, "deadline_at": deadline})


@pytest.mark.parametrize("field,value", [
    ("request_id", ""), ("request_id", "bad/id"), ("request_id", "a" * 65),
    ("request_id", None), ("topic", "  "), ("topic", "a" * 201), ("topic", 1),
    ("extra", "ignored?"),
])
def test_invalid_fields_are_identified(field, value):
    with pytest.raises(ValidationError) as error:
        Request.model_validate({**VALID, field: value})
    assert error.value.errors()[0]["loc"] == (field,)


def test_missing_id_is_a_structural_error():
    with pytest.raises(ValidationError) as error:
        Request.model_validate({"topic": "字幕推广"})
    assert error.value.errors()[0]["loc"] == ("request_id",)


def test_request_hard_constraints_cannot_be_assigned():
    request = Request.model_validate(VALID)
    with pytest.raises(ValidationError):
        request.budget_units = 100
    assert request.budget_units == 10


def test_text_is_trimmed_nfc_and_deadline_is_utc():
    request = Request.model_validate({**VALID, "request_id": " A ", "topic": " Cafe\u0301 ",
                                      "deadline_at": "2026-10-29T13:00:00.000+08:00"})
    assert request.request_id == "A"
    assert request.topic == "Café"
    assert request.deadline_at == "2026-10-29T05:00:00+00:00"
    draft = ScriptDraft.model_validate({**DRAFT, "title": " Cafe\u0301 ", "source_ids": [" M01 "]})
    assert draft.title == "Café" and draft.source_ids == ["M01"]


@pytest.mark.parametrize("field,maximum", [("title", 100), ("hook", 200), ("body", 2000), ("cta", 200)])
def test_script_text_required_and_bounded(field, maximum):
    assert len(getattr(ScriptDraft.model_validate({**DRAFT, field: "字" * maximum}), field)) == maximum
    for value in (" ", "字" * (maximum + 1), None, 123):
        with pytest.raises(ValidationError):
            ScriptDraft.model_validate({**DRAFT, field: value})
    with pytest.raises(ValidationError):
        ScriptDraft.model_validate({key: value for key, value in DRAFT.items() if key != field})


@pytest.mark.parametrize("sources", [[], ["M01", "M02"], ["M01", "M01"], ["bad"], [1], "M01"])
def test_script_has_exactly_one_well_formed_source(sources):
    with pytest.raises(ValidationError):
        ScriptDraft.model_validate({**DRAFT, "source_ids": sources})


@pytest.mark.parametrize("extra", ["price", "script_id", "script_input_hash"])
def test_script_rejects_model_supplied_extra_fields(extra):
    with pytest.raises(ValidationError):
        ScriptDraft.model_validate({**DRAFT, extra: "untrusted"})


def schema_semantics(value):
    if isinstance(value, dict):
        return {key: ({name: schema_semantics(prop) for name, prop in item.items()}
                      if key == "properties" else schema_semantics(item)) for key, item in value.items()
                if key not in {"title", "description", "default", "$schema"}}
    if isinstance(value, list):
        return [schema_semantics(item) for item in value]
    return value


def test_generated_request_schema_matches_contract():
    expected = json.loads((ROOT / "contracts/request.schema.json").read_text(encoding="utf-8"))
    assert schema_semantics(Request.model_json_schema()) == schema_semantics(expected)


def test_generated_script_draft_schema_matches_generation_fields():
    common = json.loads((ROOT / "contracts/common.schema.json").read_text(encoding="utf-8"))
    expected = common["$defs"]["Script"]
    derived = {"script_id", "script_input_hash"}
    expected["properties"] = {key: value for key, value in expected["properties"].items() if key not in derived}
    expected["required"] = [key for key in expected["required"] if key not in derived]
    assert schema_semantics(ScriptDraft.model_json_schema()) == schema_semantics(expected)
