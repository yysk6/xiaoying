"""The script-generation boundary and its explicit offline response source."""

from copy import deepcopy
from typing import Iterable, Protocol


class ModelUnavailable(Exception):
    pass


class ModelClient(Protocol):
    model_id: str

    def generate_script(self, context: dict) -> str: ...


class FakeModelClient:
    model_id = 'mock'

    def __init__(self, responses: Iterable[str | ModelUnavailable]):
        self._responses = iter(responses)
        self.requests = []

    def generate_script(self, context: dict) -> str:
        self.requests.append(deepcopy(context))
        try:
            response = next(self._responses)
        except StopIteration as error:
            raise ModelUnavailable('No configured fake response remains') from error
        if isinstance(response, ModelUnavailable):
            raise response
        return response
