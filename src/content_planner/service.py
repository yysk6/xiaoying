"""Task entry points; model decisions remain inside the planning graph."""

from pydantic import ValidationError
from pathlib import Path
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from contextlib import ExitStack

from langgraph.checkpoint.sqlite import SqliteSaver

from .catalog import load_catalog
from .contracts import Request
from .deepseek import DeepSeekModelClient
from .domain import Fault, SystemClock, input_hash, require_complete
from .graph import PlanningAgent
from .model import load_mock_scenario
from .reporting import empty_result, export_result, task_result
from .storage import Repository
from .tools import manifest_for


@dataclass(frozen=True)
class _ScenarioClock:
    instant: datetime

    def now(self):
        return self.instant


def _configured_model(backend, mock_scenario, clock, stack):
    if backend == 'deepseek':
        if mock_scenario is not None:
            raise Fault('CONFIG_ERROR', 'Live backend cannot use a mock scenario', {'backend': backend})
        return stack.enter_context(DeepSeekModelClient()), clock or SystemClock()
    if backend != 'mock':
        raise Fault('CONFIG_ERROR', 'Unknown backend')
    try:
        model, now = load_mock_scenario(mock_scenario)
    except (OSError, ValueError, ValidationError) as error:
        raise Fault('CONFIG_ERROR', 'Cannot load the explicit mock scenario') from error
    if now is not None and clock is None:
        clock = _ScenarioClock(datetime.fromisoformat(now))
    return model, clock or SystemClock()


def run_task(raw_input, *, database, model=None, clock=None, mock_scenario=None, backend='mock'):
    try:
        request = Request.model_validate(raw_input)
    except ValidationError as error:
        try:
            request_id = Request(request_id=raw_input.get('request_id')).request_id if isinstance(raw_input, dict) else None
        except ValidationError:
            request_id = None
        return empty_result(request_id, backend=backend, message='; '.join('.'.join(map(str, e['loc'])) + ': ' + e['msg']
                                                         for e in error.errors())[:1000])
    if request.missing_fields:
        return empty_result(request.request_id, backend=backend, reason='NEEDS_INPUT', message='请补齐必填字段',
                            missing_fields=request.missing_fields)
    database = Path(database)
    if database.is_file():
        with Repository(database) as repo:
            try:
                record = repo.get_request(request.request_id)
            except Fault as error:
                if error.code != 'REQUEST_NOT_FOUND':
                    raise
            else:
                if record['input_hash'] != input_hash(request):
                    return empty_result(request.request_id, backend=backend, reason='REQUEST_CONFLICT', message='该ID已用于不同业务输入')
                return _read_result(repo, database, record)
    with ExitStack() as stack:
        if model is None:
            model, clock = _configured_model(backend, mock_scenario, clock, stack)
        clock = clock or SystemClock()
        try:
            require_complete(request, clock)
        except Fault as error:
            return empty_result(request.request_id, backend=backend, reason=error.code, message=error.message)
        database.parent.mkdir(parents=True, exist_ok=True)
        with Repository(database) as repo:
            with SqliteSaver.from_conn_string(str(database)) as saver:
                state = PlanningAgent(request, load_catalog(), model, clock, repo, saver).run()
            return task_result(repo.get_request(request.request_id), state, repo.events(request.request_id),
                               repo.get_plan(request.request_id))


def _read_result(repo, database, record):
    events = repo.events(record['request_id'])
    saved = repo.get_plan(record['request_id'])
    warnings = []
    state = {}
    for event in events:
        state.update(event['state_patch'] or {})
    try:
        with SqliteSaver.from_conn_string(str(database)) as saver:
            checkpoint = saver.get_tuple({'configurable': {'thread_id': record['request_id']}})
        if checkpoint:
            state.update(checkpoint.checkpoint['channel_values'])
    except sqlite3.Error as error:
        if saved is None:
            raise Fault('STORAGE_UNAVAILABLE', 'Cannot read checkpoint') from error
        warnings.append({'code': 'CHECKPOINT_UNAVAILABLE', 'message': 'Checkpoint不可读，已按提交方案返回'})
    result = task_result(record, state, events, saved)
    result['warnings'].extend(warnings)
    return result


def show_task(request_id, *, database):
    database = Path(database)
    if not database.is_file():
        raise Fault('REQUEST_NOT_FOUND', 'Request does not exist')
    with Repository(database) as repo:
        return _read_result(repo, database, repo.get_request(request_id))


def resume_task(request_id, *, database, model=None, clock=None, mock_scenario=None, catalog=None):
    database = Path(database)
    if not database.is_file():
        raise Fault('REQUEST_NOT_FOUND', 'Request does not exist')
    with Repository(database) as repo, ExitStack() as stack:
        record = repo.get_request(request_id)
        current = _read_result(repo, database, record)
        if current['status'] == 'completed':
            return current
        for field, code in (('remaining_model_requests', 'MODEL_CALL_LIMIT_REACHED'),
                            ('remaining_action_calls', 'ACTION_LIMIT_REACHED')):
            if current['limits'][field] == 0:
                return {**current, 'status': 'incomplete', 'reason': code, 'message': code}
        if model is None:
            if record['backend'] == 'mock' and mock_scenario is None:
                raise Fault('CONFIG_ERROR', 'Mock resume requires an explicit continuation scenario')
            model, clock = _configured_model(record['backend'], mock_scenario, clock, stack)
        clock = clock or SystemClock()
        catalog = catalog or load_catalog()
        if (manifest_for(catalog, model.model_id) != record['manifest']
                or ('mock' if model.model_id == 'mock' else 'deepseek') != record['backend']):
            return {**current, 'status': 'incomplete', 'reason': 'MANIFEST_MISMATCH', 'message': 'Task configuration has changed'}
        with SqliteSaver.from_conn_string(str(database)) as saver:
            try:
                state = PlanningAgent(Request.model_validate(record['input']), catalog,
                                      model, clock, repo, saver).resume()
            except Fault as error:
                if error.code not in {'CHECKPOINT_NOT_FOUND', 'RESUME_NOT_ALLOWED'}:
                    raise
                return {**current, 'status': 'incomplete', 'reason': error.code, 'message': error.message}
        return task_result(record, state, repo.events(request_id), repo.get_plan(request_id))


def export_task(result, *, database, directory):
    events = []
    if result['manifest'] is not None:
        with Repository(database) as repo:
            events = repo.events(result['request_id'])
    return export_result(result, events, directory)
