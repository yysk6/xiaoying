"""One planner decision and one dispatch; the graph owns the loop."""

from copy import deepcopy
from datetime import timezone
import json
from typing_extensions import TypedDict
from pydantic import ValidationError

from .contracts import ACTION_ARGS
from .domain import Fault
from .model import ModelUnavailable
from .prompts import PLANNER
from .tools import LocalTools


class AgentState(TypedDict, total=False):
    request: dict
    manifest: dict
    status: str
    reason: str | None
    message: str
    seen_material_ids: list
    candidate_history: dict
    current_revision: int | None
    script_artifacts: dict
    estimate_history: dict
    current_estimate_id: str | None
    tool_results: list
    last_observation: dict | None
    saved_plan_id: str | None
    planner_messages: list
    decision_seq: int
    consecutive_protocol_errors: int
    pending_call: dict | None
    unresolved_failures: dict


def tool_definitions():
    return [{'type': 'function', 'function': {'name': name, 'description': name,
                                             'parameters': dto.model_json_schema()}}
            for name, dto in ACTION_ARGS.items()]


def build_context(state, pricing, events):
    candidate = state['candidate_history'].get(str(state['current_revision']))
    estimate = state['estimate_history'].get(state['current_estimate_id'])
    counts = {'model': sum(e['phase'] == 'started' and e['kind'] == 'model' for e in events),
              'action': sum(e['phase'] == 'started' and e['kind'] in {'tool', 'control'} for e in events)}
    groups = []
    for message in state['planner_messages']:
        if message['role'] == 'assistant':
            groups.append([message])
        else:
            groups[-1].append(message)
    recent = []
    split = len(groups)
    for index in range(len(groups) - 1, -1, -1):
        proposed = groups[index] + recent
        if len(json.dumps(proposed, ensure_ascii=False)) > 12000:
            break
        recent, split = proposed, index
    summary = []
    for group in groups[:split]:
        for message in group[1:]:
            observation = json.loads(message['content'])
            summary.append({'tool_call_id': message['tool_call_id'], 'tool': observation.get('tool'),
                            'ok': observation.get('ok', False),
                            'error_code': (observation.get('error') or {}).get('code')})
    script = state['script_artifacts'].get(candidate['script_input_hash']) if candidate else None
    context = {'system': PLANNER, 'tools': tool_definitions(), 'messages': deepcopy(recent), 'history_summary': summary,
            'memory': {'request': state['request'], 'pricing': pricing, 'candidate': candidate,
                       'seen_material_ids': state['seen_material_ids'], 'latest_estimate': estimate,
                       'script': {key: script[key] for key in ('script_id', 'title', 'source_ids')} if script else None,
                       'evaluated_quotes': [{key: quote[key] for key in ('estimate_id', 'revision', 'total_units',
                                            'total_minutes', 'feasible', 'budget_gap_units', 'deadline_gap_minutes')}
                                           for quote in state['estimate_history'].values()],
                       'unresolved_failures': state.get('unresolved_failures', {}),
                       'last_observation': state['last_observation']},
            'limits': {'model_remaining': 32 - counts['model'], 'action_remaining': 24 - counts['action']}}
    if len(json.dumps(context, ensure_ascii=False).encode('utf-8')) > 65536:
        raise Fault('CONTEXT_LIMIT_REACHED', 'Required context exceeds the configured byte budget')
    return context


class _ScriptModel:
    def __init__(self, runtime):
        self.runtime = runtime
        self.model_id = runtime.model.model_id
        self.operation_id = ''

    def generate_script(self, context):
        return self.runtime.model_request(self.operation_id + ':script', 'script',
                                          lambda: self.runtime.model.generate_script(context))


class AgentRuntime:
    def __init__(self, request, catalog, model, clock, repository):
        self.request, self.catalog, self.model, self.clock, self.repo = request, catalog, model, clock, repository
        self.script_model = _ScriptModel(self)
        self.tools = LocalTools(request, catalog, self.script_model, clock, repository=repository)

    def fields(self, kind, name, arguments=None, rationale=''):
        return {'kind': kind, 'name': name, 'args': arguments or {}, 'rationale': rationale,
                'created_at': self.clock.now().astimezone(timezone.utc).isoformat()}

    def model_request(self, operation_id, name, execute):
        fields = self.fields('model', name)
        self.repo.start_operation(self.request.request_id, operation_id, limit=32, **fields)
        try:
            response = execute()
        except ModelUnavailable:
            self.repo.record_event(self.request.request_id, operation_id, 'failed',
                                   error_code='SCRIPT_MODEL_UNAVAILABLE' if name == 'script' else 'MODEL_UNAVAILABLE', **fields)
            raise
        if name == 'planner' and isinstance(response, dict):
            response = {key: value for key, value in response.items() if key in {'role', 'content', 'tool_calls'}}
        self.repo.record_event(self.request.request_id, operation_id, 'succeeded', result={'response': response}, **fields)
        return response

    def decide(self, state):
        seq = state['decision_seq'] + 1
        try:
            context = build_context(state, self.catalog.pricing.model_dump(mode='json'), self.repo.events(self.request.request_id))
        except Fault as error:
            return self.halt(error.code)
        if context['limits']['action_remaining'] <= 0:
            return self.halt('ACTION_LIMIT_REACHED')
        try:
            response = self.model_request(f'decide:{seq}', 'planner', lambda: self.model.decide(context))
        except Fault as error:
            if error.code != 'MODEL_CALL_LIMIT_REACHED':
                raise
            return self.halt(error.code)
        except ModelUnavailable:
            return {**self.halt('MODEL_UNAVAILABLE'), 'decision_seq': seq}
        state = {**state, 'decision_seq': seq}
        if (not isinstance(response, dict) or response.get('role') != 'assistant'
                or (response.get('content') is not None and not isinstance(response['content'], str))):
            return {**self.halt('MODEL_PROTOCOL_ERROR'), 'decision_seq': seq}
        response = {key: value for key, value in response.items() if key in {'role', 'content', 'tool_calls'}}
        calls = response.get('tool_calls')
        if calls is None or calls == []:
            if not isinstance(response.get('content'), str) or not response['content'].strip():
                return {**self.halt('MODEL_PROTOCOL_ERROR'), 'decision_seq': seq}
            return {**self.halt('MODEL_STOPPED'), 'decision_seq': seq,
                    'planner_messages': state['planner_messages'] + [response]}
        valid = isinstance(calls, list) and all(
            isinstance(call, dict) and isinstance(call.get('id'), str) and 0 < len(call['id']) <= 200
            and call['id'].strip() and call.get('type') == 'function' and isinstance(call.get('function'), dict)
            and isinstance(call['function'].get('name'), str) and isinstance(call['function'].get('arguments'), str)
            for call in calls)
        old_ids = {call['id'] for message in state['planner_messages'] if message['role'] == 'assistant'
                   for call in message.get('tool_calls', [])}
        if not valid or len({call['id'] for call in calls}) != len(calls) or any(call['id'] in old_ids for call in calls):
            return {**self.halt('MODEL_PROTOCOL_ERROR'), 'decision_seq': seq}
        if len(calls) != 1 or calls[0]['function']['name'] not in ACTION_ARGS:
            return self.protocol_error(state, response)
        function = calls[0]['function']
        try:
            arguments = json.loads(function['arguments'])
            ACTION_ARGS[function['name']].model_validate(arguments)
        except (ValueError, ValidationError):
            return self.protocol_error(state, response, invalid_arguments=True)
        return {'decision_seq': seq, 'pending_call': response['tool_calls'][0],
                'planner_messages': state['planner_messages'] + [response]}

    @staticmethod
    def halt(reason):
        return {'status': 'incomplete', 'reason': reason, 'message': reason, 'pending_call': None}

    def protocol_error(self, state, response, invalid_arguments=False):
        messages = state['planner_messages'] + [response]
        for call in response['tool_calls']:
            result = {'error': {'code': 'MODEL_PROTOCOL_ERROR', 'message': 'Choose exactly one valid action'}}
            if invalid_arguments:
                # Parsing failed parameters must not execute the action or consume its quota.
                try:
                    arguments = json.loads(call['function']['arguments'])
                except ValueError:
                    arguments = None
                result = getattr(self.tools, call['function']['name'])(call['id'], arguments)
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': json.dumps(result, ensure_ascii=False)})
        count = state['consecutive_protocol_errors'] + 1
        fields = self.fields('validation', 'protocol', {'tool_call_ids': [call['id'] for call in response['tool_calls']]})
        self.repo.record_event(self.request.request_id, f"decide:{state['decision_seq']}:validation", 'rejected',
                               error_code='MODEL_PROTOCOL_ERROR', **fields)
        patch = {**self.tools.snapshot(), 'decision_seq': state['decision_seq'], 'pending_call': None,
                 'consecutive_protocol_errors': count, 'planner_messages': messages}
        if count >= 2:
            patch.update(self.halt('MODEL_PROTOCOL_ERROR'))
        return patch

    def dispatch(self, state):
        call = state['pending_call']
        name = call['function']['name']
        arguments = json.loads(call['function']['arguments'])
        operation_id = 'tool:' + call['id']
        key = self.tools.logical_key(name, ACTION_ARGS[name].model_validate(arguments).model_dump(mode='json'))
        fields = self.fields('control' if name in {'revise_plan', 'stop_task'} else 'tool', name,
                             {'arguments': arguments, 'logical_key': key},
                             arguments['rationale'])
        events = self.repo.events(self.request.request_id)
        matching = {event['operation_id'] for event in events if event['phase'] == 'started'
                    and event['args'].get('logical_key') == key}
        outcomes = [event for event in events if event['operation_id'] in matching
                    and event['phase'] in {'succeeded', 'failed'}]
        exhausted = len(outcomes) >= 2 and all(event['phase'] == 'failed' and event['result']
                    and event['result']['error']['retryable'] for event in outcomes[-2:])
        try:
            self.repo.start_operation(self.request.request_id, operation_id, limit=24, **fields)
        except Fault as error:
            if error.code != 'ACTION_LIMIT_REACHED':
                raise
            return self.halt(error.code)
        self.script_model.operation_id = operation_id
        if exhausted:
            result = self.tools.reject_action(name, call['id'], Fault('TOOL_RETRY_LIMIT_REACHED',
                                                                      'Two retryable attempts have already failed'))
        else:
            result = getattr(self.tools, name)(call['id'], arguments)
        after = self.tools.snapshot()
        phase = 'succeeded' if result['ok'] else ('failed' if result['error']['retryable'] else 'rejected')
        self.repo.record_event(self.request.request_id, operation_id, phase,
                               result=result, state_patch=after, error_code=result['error']['code'] if result['error'] else None, **fields)
        messages = state['planner_messages'] + [{'role': 'tool', 'tool_call_id': call['id'],
                                               'content': json.dumps(result, ensure_ascii=False)}]
        patch = {**after, 'pending_call': None, 'planner_messages': messages, 'consecutive_protocol_errors': 0}
        if not result['ok'] and result['error']['code'] == 'MODEL_CALL_LIMIT_REACHED':
            patch.update(self.halt('MODEL_CALL_LIMIT_REACHED'))
        return patch
