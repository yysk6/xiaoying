"""Versioned synthetic resources loaded independently of the working directory."""

from dataclasses import dataclass
import hashlib
from importlib import resources
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, ValidationError, field_validator, model_validator

from .contracts import MaterialId, StrictDTO, normalize_text
from .domain import Fault


class Price(StrictDTO):
    fee_units: Annotated[int, Field(ge=0)]
    duration_minutes: Annotated[int, Field(ge=0)]


class ProductionPrices(StrictDTO):
    basic: Price
    premium: Price


class Pricing(StrictDTO):
    version: Annotated[str, Field(min_length=1, max_length=40)]
    currency: Literal['simulated_unit']
    execution: Literal['sequential']
    script_finalize: Price
    video_edit: ProductionPrices
    review: Price


Text = Annotated[str, Field(min_length=1), BeforeValidator(normalize_text)]


class MaterialRecord(StrictDTO):
    material_id: MaterialId
    version: Annotated[str, Field(min_length=1, max_length=40)]
    title: Annotated[str, Field(min_length=1, max_length=100)]
    tags: Annotated[list[Annotated[Text, Field(max_length=40)]], Field(min_length=1)]
    facts: Annotated[list[Annotated[Text, Field(max_length=300)]], Field(min_length=1)]
    fee_units: Annotated[int, Field(ge=0)]
    lead_minutes: Annotated[int, Field(ge=0)]


class Materials(StrictDTO):
    version: Text
    synthetic: Literal[True]
    materials: Annotated[list[MaterialRecord], Field(min_length=1)]

    @field_validator('synthetic', mode='before')
    @classmethod
    def boolean_true(cls, value):
        if value is not True:
            raise ValueError('Synthetic data must be marked with boolean true')
        return value

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [material.material_id for material in self.materials]
        if len(ids) != len(set(ids)):
            raise ValueError('Material IDs must be unique')
        return self


class Aliases(StrictDTO):
    version: Text
    aliases: dict[Text, Text]


@dataclass(frozen=True)
class Catalog:
    materials: tuple[MaterialRecord, ...]
    pricing: Pricing
    aliases: dict
    catalog_hash: str
    pricing_hash: str
    aliases_hash: str

    def normalize_query(self, query: str) -> str:
        text = normalize_text(query).lower()
        aliases = {alias.lower(): target.lower() for alias, target in self.aliases.items()}
        for alias in sorted(aliases, key=lambda item: (-len(item), item)):
            text = text.replace(alias, aliases[alias])
        return text

    def search(self, query: str, top_k: int) -> list[dict]:
        text = self.normalize_query(query)
        matches = []
        for material in self.materials:
            score = sum(tag in text for tag in {item.lower() for item in material.tags})
            if score:
                matches.append({**material.model_dump(mode='json'), 'score': score})
        return sorted(matches, key=lambda item: (-item['score'], item['material_id']))[:top_k]


def load_catalog(directory: Path | None = None) -> Catalog:
    location = resources.files('content_planner').joinpath('data') if directory is None else directory
    raw = {}
    for name in ('materials', 'pricing', 'aliases'):
        try:
            raw[name] = location.joinpath(name + '.json').read_bytes()
        except OSError as error:
            code = 'ESTIMATOR_UNAVAILABLE' if name == 'pricing' else 'CATALOG_UNAVAILABLE'
            raise Fault(code, f'Cannot read {name}.json') from error
    parsed = {}
    for name, data in raw.items():
        try:
            parsed[name] = json.loads(data)
        except (ValueError, UnicodeError) as error:
            code = 'PRICING_INVALID' if name == 'pricing' else 'CATALOG_UNAVAILABLE'
            raise Fault(code, f'Invalid JSON in {name}.json') from error
    try:
        pricing = Pricing.model_validate(parsed['pricing'])
    except ValidationError as error:
        raise Fault('PRICING_INVALID', 'Invalid pricing data') from error
    try:
        materials = Materials.model_validate(parsed['materials'])
        aliases = Aliases.model_validate(parsed['aliases'])
    except ValidationError as error:
        raise Fault('CATALOG_UNAVAILABLE', 'Invalid material data') from error
    return Catalog(tuple(materials.materials),
                   pricing, aliases.aliases,
                   *(hashlib.sha256(raw[name]).hexdigest() for name in ('materials', 'pricing', 'aliases')))
