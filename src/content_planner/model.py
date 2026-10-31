"""The script-generation boundary and its explicit offline response source."""

from copy import deepcopy
from typing import Iterable, Protocol
import json
from importlib import resources
from pathlib import Path
from pydantic import Field

from .contracts import Deadline, StrictDTO


class ModelUnavailable(Exception):
    def __init__(self, message, *, code='MODEL_UNAVAILABLE', retryable=True, usage=None):
        super().__init__(message)
        self.code, self.retryable, self.usage = code, retryable, usage


class ModelClient(Protocol):
    model_id: str

    def generate_script(self, context: dict) -> str: ...

    def decide(self, context: dict) -> dict: ...


class FakeModelClient:
    model_id = 'mock'

    def __init__(self, responses: Iterable[str | ModelUnavailable], *, decisions: Iterable[dict | ModelUnavailable] = ()):
        self._responses = iter(responses)
        self._decisions = iter(decisions)
        self.requests = []
        self.decision_requests = []

    def decide(self, context: dict) -> dict:
        self.decision_requests.append(deepcopy(context))
        try:
            response = next(self._decisions)
        except StopIteration as error:
            raise ModelUnavailable('No configured fake decision remains') from error
        if isinstance(response, ModelUnavailable):
            raise response
        return deepcopy(response)

    def generate_script(self, context: dict) -> str:
        self.requests.append(deepcopy(context))
        try:
            response = next(self._responses)
        except StopIteration as error:
            raise ModelUnavailable('No configured fake response remains') from error
        if isinstance(response, ModelUnavailable):
            raise response
        return response


class MockScenario(StrictDTO):
    decisions: list[dict] = Field(default_factory=list)
    responses: list[str | dict] = Field(default_factory=list)
    now: Deadline | None = None


def load_mock_scenario(path=None):
    source = Path(path) if path is not None else resources.files('content_planner').joinpath('data/mock-scenario.json')
    scenario = MockScenario.model_validate(json.loads(source.read_text(encoding='utf-8-sig')))

    def responses(values):
        for value in values:
            if value == {'error': 'MODEL_UNAVAILABLE'}:
                yield ModelUnavailable('Configured offline failure')
            elif isinstance(value, dict) and 'error' in value:
                raise ValueError('Unsupported mock error')
            else:
                yield value

    # Materialize to reject malformed fixture configuration before creating a task.
    scripts = list(responses(scenario.responses))
    if any(not isinstance(item, (str, ModelUnavailable)) for item in scripts):
        raise ValueError('Mock script responses must be JSON strings or explicit failures')
    return FakeModelClient(scripts, decisions=list(responses(scenario.decisions))), scenario.now
