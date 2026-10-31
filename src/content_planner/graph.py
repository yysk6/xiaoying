"""The two-node LangGraph entry point for offline planning."""

import json

from langgraph.graph import END, START, StateGraph
from langgraph.errors import GraphRecursionError

from .agent import AgentRuntime, AgentState
from .domain import Fault


class PlanningAgent:
    def __init__(self, request, catalog, model, clock, repository, checkpointer):
        self.runtime = AgentRuntime(request, catalog, model, clock, repository)
        self.config = {'configurable': {'thread_id': request.request_id}}
        builder = StateGraph(AgentState)
        builder.add_node('decide', self.runtime.decide)
        builder.add_node('dispatch', self.runtime.dispatch)
        builder.add_edge(START, 'decide')
        builder.add_conditional_edges('decide', lambda state: END if state['status'] != 'running' else
                                      ('dispatch' if state['pending_call'] is not None else 'decide'))
        builder.add_conditional_edges('dispatch', lambda state: END if state['status'] != 'running' else 'decide')
        self.graph = builder.compile(checkpointer=checkpointer)

    def run(self, *, recursion_limit=80):
        previous = self.graph.get_state(self.config)
        initial = {**self.runtime.tools.snapshot(), 'planner_messages': [], 'decision_seq': 0,
                   'consecutive_protocol_errors': 0, 'pending_call': None, 'message': ''}
        saved = self.runtime.repo.get_plan(self.runtime.request.request_id)
        if saved is not None:
            state = {**(previous.values or initial), 'status': 'completed', 'reason': None,
                     'pending_call': None, 'saved_plan_id': saved['plan_id']}
            if previous.values:
                self.graph.update_state(self.config, state, as_node='dispatch')
            return state
        if previous.values:
            return previous.values
        return self._invoke(initial, recursion_limit)

    def resume(self, *, recursion_limit=80):
        previous = self.graph.get_state(self.config)
        if not previous.values:
            raise Fault('CHECKPOINT_NOT_FOUND', 'No task checkpoint is available')
        interrupted = bool(previous.next or previous.tasks)
        if not interrupted:
            state = previous.values
            retryable_ids = {r['tool_call_id'] for r in state['tool_results']
                             if not r['ok'] and r['error']['retryable']}
            retryable = state['reason'] == 'MODEL_UNAVAILABLE' or (
                state['reason'] == 'tool_failure' and any(ref['tool_call_id'] in retryable_ids
                    for ref in state.get('unresolved_failures', {}).values()))
            if not retryable:
                raise Fault('RESUME_NOT_ALLOWED', 'Task stopped for a nonrecoverable reason')
        state = {**previous.values, 'status': 'running', 'reason': None, 'message': ''}
        self.runtime.tools.restore(state)
        return self._invoke(None if interrupted else state, recursion_limit)

    def _invoke(self, state, recursion_limit):
        try:
            return self.graph.invoke(state, {**self.config, 'recursion_limit': recursion_limit})
        except GraphRecursionError:
            state = dict(self.graph.get_state(self.config).values)
            call = state.get('pending_call')
            if call is not None:
                name = call['function']['name']
                result = self.runtime.tools.reject_action(name, call['id'],
                                                          Fault('GRAPH_LIMIT_REACHED', 'Graph stopped before dispatch'))
                state.update(self.runtime.tools.snapshot())
                state['planner_messages'] = state['planner_messages'] + [
                    {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result, ensure_ascii=False)}]
                self.runtime.repo.record_event(self.runtime.request.request_id, 'tool:' + call['id'], 'rejected',
                    result=result, error_code='GRAPH_LIMIT_REACHED',
                    **self.runtime.fields('validation', name, {'arguments': json.loads(call['function']['arguments'])}))
            state.update(self.runtime.halt('GRAPH_LIMIT_REACHED'))
            self.graph.update_state(self.config, state, as_node='dispatch')
            return state
