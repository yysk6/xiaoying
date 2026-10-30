"""Strict input DTOs; time-dependent and cross-field rules live in domain."""

from datetime import datetime, timezone
from typing import Annotated, Literal
import unicodedata

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_validator


DEADLINE_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"


def normalize_text(value):
    return unicodedata.normalize("NFC", value).strip() if isinstance(value, str) else value


def utc_deadline(value: str) -> str:
    # fromisoformat normalizes out-of-range offset minutes instead of rejecting them.
    if not value.endswith("Z") and int(value[-2:]) >= 60:
        raise ValueError("UTC offset minutes must be below 60")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()


Deadline = Annotated[str, Field(pattern=DEADLINE_PATTERN, json_schema_extra={"format": "date-time"}),
                     AfterValidator(utc_deadline)]
MaterialId = Annotated[str, Field(pattern=r"^M[0-9]{2}$"), BeforeValidator(normalize_text)]


class StrictDTO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def normalize_strings(cls, value):
        return normalize_text(value)


class Request(StrictDTO):
    model_config = ConfigDict(frozen=True)

    request_id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
    topic: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    budget_units: Annotated[int, Field(ge=1, le=100000)] | None = None
    deadline_at: Deadline | None = None

    @property
    def missing_fields(self) -> list[str]:
        return [field for field in ("topic", "budget_units", "deadline_at") if getattr(self, field) is None]


class ScriptDraft(StrictDTO):
    title: Annotated[str, Field(min_length=1, max_length=100)]
    hook: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=2000)]
    cta: Annotated[str, Field(min_length=1, max_length=200)]
    source_ids: Annotated[list[MaterialId], Field(min_length=1, max_length=1,
                                               json_schema_extra={"uniqueItems": True})]


class ActionArgs(StrictDTO):
    rationale: Annotated[str, Field(min_length=1, max_length=200,
                                   description='可公开的一句话动作依据，不包含内部思维过程')]


class SearchMaterialsArgs(ActionArgs):
    query: Annotated[str, Field(min_length=1, max_length=200)]
    top_k: Annotated[int, Field(ge=1, le=5)]


class RevisePlanArgs(ActionArgs):
    material_id: MaterialId
    creative_brief: Annotated[str, Field(min_length=1, max_length=500)]
    production_mode: Literal['basic', 'premium']


class RevisionArgs(ActionArgs):
    plan_revision: Annotated[int, Field(ge=1, le=4)]


class SavePlanArgs(RevisionArgs):
    estimate_id: Annotated[str, Field(min_length=1, max_length=100)]
