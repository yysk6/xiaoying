"""Pure content-planning rules; callers provide validated data and an aware Clock."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Protocol

from pydantic import ValidationError

from .contracts import Request, ScriptDraft, normalize_text


AUDIENCE = "新手创作者"
PLATFORM = "短视频平台"
PERCENTAGE = re.compile(r"\d+(?:\.\d+)?\s*%")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class Fault(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


def require_complete(request: Request, clock: Clock) -> Request:
    if request.missing_fields:
        raise Fault("NEEDS_INPUT", "Required business fields are missing",
                    {"missing_fields": request.missing_fields})
    if datetime.fromisoformat(request.deadline_at) <= clock.now():
        raise Fault("INVALID_ARGUMENT", "deadline_at must be later than the current time",
                    {"field": "deadline_at"})
    return request


def _hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def input_hash(request: Request) -> str:
    return _hash({"topic": request.topic, "budget_units": request.budget_units,
                  "deadline_at": request.deadline_at, "audience": AUDIENCE, "platform": PLATFORM})


def _material_hash(material: dict) -> str:
    return _hash({key: value for key, value in material.items() if key != "score"})


def candidate_hash(request: Request, material: dict, creative_brief: str,
                   production_mode: str, pricing_hash: str) -> str:
    return _hash({"input_hash": input_hash(request), "material_hash": _material_hash(material),
                  "creative_brief": normalize_text(creative_brief), "production_mode": production_mode,
                  "pricing_hash": pricing_hash})


def script_input_hash(request: Request, material: dict, creative_brief: str, *,
                      model_id: str, script_prompt_version: str, thinking: str = "disabled") -> str:
    return _hash({"topic": request.topic, "audience": AUDIENCE, "platform": PLATFORM,
                  "material_hash": _material_hash(material), "creative_brief": normalize_text(creative_brief),
                  "script_prompt_version": script_prompt_version, "model_id": model_id, "thinking": thinking})


def quote(request: Request, material: dict, pricing: dict, production_mode: str, clock: Clock) -> dict:
    """Price the specified mode using complete input and prevalidated catalog data."""
    items = [
        {"step_id": "material_prepare", "catalog_item_id": material["material_id"],
         "fee_units": material["fee_units"], "duration_minutes": material["lead_minutes"]},
        {"step_id": "script_finalize", "catalog_item_id": "script_finalize", **pricing["script_finalize"]},
        {"step_id": "video_edit", "catalog_item_id": f"video_edit:{production_mode}",
         **pricing["video_edit"][production_mode]},
        {"step_id": "review", "catalog_item_id": "review", **pricing["review"]},
    ]
    total_units = sum(item["fee_units"] for item in items)
    total_minutes = sum(item["duration_minutes"] for item in items)
    quoted_at = clock.now().astimezone(timezone.utc)
    finish = quoted_at + timedelta(minutes=total_minutes)
    deadline = datetime.fromisoformat(request.deadline_at)
    within_budget = total_units <= request.budget_units
    within_deadline = finish <= deadline
    return {"line_items": items, "quoted_at": quoted_at.isoformat(),
            "total_units": total_units, "total_minutes": total_minutes,
            "estimated_finish_at": finish.isoformat(), "within_budget": within_budget,
            "within_deadline": within_deadline, "feasible": within_budget and within_deadline,
            "budget_gap_units": max(total_units - request.budget_units, 0),
            # Negated floor division is exact ceiling, including a one-microsecond overrun.
            "deadline_gap_minutes": max(0, -((deadline - finish) // timedelta(minutes=1)))}


def validate_script(draft: ScriptDraft, material: dict) -> None:
    if draft.source_ids != [material["material_id"]]:
        raise Fault("SCRIPT_INVALID", "Script source must equal the selected material")
    allowed_percentages = {re.sub(r"\s+", "", token) for fact in material["facts"]
                           for token in PERCENTAGE.findall(fact)}
    for text in (draft.title, draft.hook, draft.body, draft.cta):
        compact = re.sub(r"\s+", "", text)
        if "行业第一" in compact or "100%准确" in compact:
            raise Fault("SCRIPT_INVALID", "Script contains a prohibited claim")
        percentages = {re.sub(r"\s+", "", token) for token in PERCENTAGE.findall(text)}
        if not percentages <= allowed_percentages:
            raise Fault("SCRIPT_INVALID", "Script percentage is unsupported by selected material facts")


def parse_script(raw_json: str, material: dict) -> ScriptDraft:
    try:
        draft = ScriptDraft.model_validate_json(raw_json)
    except ValidationError as error:
        raise Fault("SCRIPT_INVALID", "Script JSON or fields are invalid") from error
    validate_script(draft, material)
    return draft


def build_saved_plan(request: Request, candidate: dict, script: dict, pricing_hash: str,
                     quotation: dict) -> dict:
    """Build the immutable deliverable from a freshly checked quotation."""
    digest = _hash({'request': request.model_dump(mode='json'), 'candidate': candidate,
                    'script': script, 'pricing_hash': pricing_hash, 'line_items': quotation['line_items']})
    start = datetime.fromisoformat(quotation['quoted_at'])
    cursor = start
    steps = []
    descriptions = ['准备选中素材', '定稿当前脚本', '按选中档位剪辑制作', '审核内容与来源']
    for item, description in zip(quotation['line_items'], descriptions):
        finish = cursor + timedelta(minutes=item['duration_minutes'])
        steps.append({'step_id': item['step_id'], 'description': description,
                      'depends_on': [steps[-1]['step_id']] if steps else [],
                      'fee_units': item['fee_units'], 'duration_minutes': item['duration_minutes'],
                      'status': 'planned', 'starts_at': cursor.isoformat(), 'finishes_at': finish.isoformat()})
        cursor = finish
    return {'plan_id': 'plan_' + hashlib.sha256(request.request_id.encode('utf-8')).hexdigest(),
            'request_id': request.request_id, 'topic': request.topic, 'candidate': candidate, 'script': script,
            'task_plan': steps, 'line_items': quotation['line_items'], 'total_units': quotation['total_units'],
            'total_minutes': quotation['total_minutes'], 'estimated_start_at': start.isoformat(),
            'estimated_finish_at': cursor.isoformat(), 'deadline_at': request.deadline_at,
            'budget_units': request.budget_units, 'saved_at': start.isoformat(), 'content_hash': digest,
            'source_ids': script['source_ids']}
