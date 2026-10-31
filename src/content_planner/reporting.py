"""Build public results and exports from persisted business facts."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path


def empty_result(request_id=None, *, backend='mock', reason='INVALID_ARGUMENT', message='Invalid input', missing_fields=()):
    return {'schema_version': '1.0', 'request_id': request_id, 'backend': backend,
            'model': 'mock' if backend == 'mock' else 'deepseek-v4-pro',
            'status': 'needs_input', 'reason': reason, 'message': message,
            'missing_fields': list(missing_fields), 'task_plan': [], 'execution_steps': [], 'tool_results': [],
            'current_revision': None, 'candidate': None, 'total_units': None, 'saved_plan': None,
            'usage': {'model_requests': 0, 'action_calls': 0, 'input_tokens': None,
                      'output_tokens': None, 'api_cost_usd': None},
            'limits': {'max_model_requests': 32, 'max_action_calls': 24, 'max_revisions': 4,
                       'remaining_model_requests': 32, 'remaining_action_calls': 24},
            'warnings': [], 'trace_path': None, 'manifest': None}


def task_result(record, state, events, saved):
    result = empty_result(record['request_id'], backend=record['backend'])
    results = deepcopy(state.get('tool_results', []))
    for event in events:
        observation = event['result']
        if isinstance(observation, dict) and 'tool_call_id' in observation and observation not in results:
            results.append(observation)
    indexes = {r['tool_call_id']: index for index, r in enumerate(results)}
    steps, attempts = [], {}
    for event in events:
        if event['kind'] not in {'tool', 'control'} or event['phase'] != 'started':
            continue
        key = event['args'].get('logical_key', event['name'])
        attempts[key] = attempts.get(key, 0) + 1
        end = next((e for e in reversed(events) if e['operation_id'] == event['operation_id']), event)
        call_id = event['operation_id'].removeprefix('tool:')
        observation = end['result'] or {}
        steps.append({'event_id': event['event_id'], 'operation_id': event['operation_id'],
                      'tool_call_id': call_id, 'tool': event['name'], 'attempt': attempts[key],
                      'status': end['phase'], 'reused': observation.get('reused', False),
                      'result_index': indexes.get(call_id), 'error_code': end['error_code']})
    candidate = state.get('candidate_history', {}).get(str(state.get('current_revision')))
    plan = saved['saved_plan'] if saved else None
    if plan:
        candidate = plan['candidate']
    estimate = state.get('estimate_history', {}).get(state.get('current_estimate_id'))
    model_count = sum(e['kind'] == 'model' and e['phase'] == 'started' for e in events)
    action_count = len(steps)
    result.update(model=record['model'], status='completed' if plan else state.get('status', 'running'),
                  reason=None if plan else state.get('reason'),
                  message='方案已保存（活动尚未执行）' if plan else (state.get('message') or '任务尚未完成'),
                  tool_results=results, execution_steps=steps, candidate=candidate,
                  current_revision=candidate['revision'] if candidate else None,
                  saved_plan=plan, task_plan=plan['task_plan'] if plan else [],
                  total_units=plan['total_units'] if plan else (estimate['total_units'] if estimate else None),
                  manifest=record['manifest'])
    result['usage'].update(model_requests=model_count, action_calls=action_count)
    result['limits'].update(remaining_model_requests=max(0, 32 - model_count),
                            remaining_action_calls=max(0, 24 - action_count))
    return result


def trace_events(result, events):
    indexes = {r['tool_call_id']: index for index, r in enumerate(result['tool_results'])}
    status = 'running'
    trace = []
    for event in events:
        status = (event['state_patch'] or {}).get('status', status)
        if event == events[-1]:
            status = result['status']
        observation = event['result'] or {}
        args = event['args'].get('arguments', event['args'])
        index = indexes.get(observation.get('tool_call_id'))
        summary = {'phase': event['phase']}
        if event['error_code']:
            summary['error_code'] = event['error_code']
        if 'ok' in observation:
            summary.update(ok=observation['ok'], reused=observation['reused'])
            data = observation['data'] or {}
            summary.update({key: data[key] for key in ('total_units', 'feasible', 'budget_gap_units',
                            'deadline_gap_minutes') if key in data})
        trace.append({'schema_version': '1.0', 'event_id': event['event_id'], 'request_id': result['request_id'],
                      'backend': result['backend'], 'model': result['model'],
                      'origin': 'fixture_setup' if event['args'].get('origin') == 'fixture_setup' else
                                ('model' if event['kind'] in {'tool', 'control', 'validation'} else 'system'),
                      'kind': event['kind'], 'operation_id': event['operation_id'], 'phase': event['phase'],
                      'name': event['name'], 'args': args or None, 'rationale': event['rationale'] or None,
                      'observation_summary': json.dumps(summary, ensure_ascii=False),
                      'result_ref': f'tool_results:{index}' if index is not None else None,
                      'task_status': status,
                      'next_decision_event_id': next((e['event_id'] for e in events if e['event_id'] > event['event_id']
                          and e['name'] == 'planner' and e['phase'] == 'started'), None),
                      'created_at': event['created_at']})
    return trace


def markdown(result):
    lines = [f"# 内容活动方案：{result['request_id']}", '',
             f"状态：{result['status']}；backend={result['backend']}；model={result['model']}", '', result['message'], '']
    plan = result['saved_plan']
    if plan:
        lines += [f"方案ID：{plan['plan_id']}", f"素材来源：{plan['candidate']['material_id']}",
                  f"总费用：{plan['total_units']} units", '', '## 脚本草稿', '']
        lines += [plan['script'][key] for key in ('title', 'hook', 'body', 'cta')]
        lines += ['', '## 活动计划（planned，尚未执行；北京时间 UTC+08:00）', '',
                  '| 活动 | 费用 units | 分钟 | 开始 | 结束 | 状态 |', '|---|---:|---:|---|---|---|']
        for step in plan['task_plan']:
            start = datetime.fromisoformat(step['starts_at']).astimezone(timezone(timedelta(hours=8))).isoformat()
            finish = datetime.fromisoformat(step['finishes_at']).astimezone(timezone(timedelta(hours=8))).isoformat()
            lines.append(f"| {step['description']} | {step['fee_units']} | {step['duration_minutes']} | "
                         f"{start} | {finish} | {step['status']} |")
    else:
        candidate = result['candidate']
        estimate = next((r['data'] for r in reversed(result['tool_results'])
                         if r['tool'] == 'estimate_cost' and r['ok'] and candidate is not None
                         and r['data']['candidate_hash'] == candidate['candidate_hash']
                         and result['total_units'] is not None), None)
        estimate_summary = {key: estimate[key] for key in ('estimate_id', 'revision', 'total_units', 'total_minutes',
                            'feasible', 'budget_gap_units', 'deadline_gap_minutes')} if estimate else None
        lines += ['方案未保存。', '', '## 当前候选与观察', '',
                  '```json', json.dumps({'candidate': result['candidate'], 'total_units': result['total_units'],
                      'latest_estimate': estimate_summary,
                      'missing_fields': result['missing_fields'],
                      'last_observation': result['tool_results'][-1] if result['tool_results'] else None},
                      ensure_ascii=False, indent=2), '```']
    return '\n'.join(lines) + '\n'


def export_result(result, events, directory):
    result = deepcopy(result)
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        trace = directory / 'trace.jsonl'
        trace.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in trace_events(result, events)),
                         encoding='utf-8')
        result['trace_path'] = str(trace.resolve()) if events else None
        (directory / 'plan.md').write_text(markdown(result), encoding='utf-8')
        (directory / 'output.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except OSError:
        result['trace_path'] = None
        result['warnings'].append({'code': 'EXPORT_FAILED', 'message': '输出文件导出失败，可使用show重新导出'})
    return result
