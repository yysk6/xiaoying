"""Explicit paid DeepSeek protocol probe and one sample each of L01/L02/L03."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid
import subprocess
import sys

from content_planner.agent import tool_definitions
from content_planner.catalog import load_catalog
from content_planner.contracts import Request, ScriptDraft
from content_planner.deepseek import DeepSeekModelClient
from content_planner.domain import Fault, SystemClock, parse_script
from content_planner.model import ModelUnavailable
from content_planner.service import export_task, run_task
from content_planner.tools import LocalTools


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_snapshot():
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(['git', '-c', f'safe.directory={root.as_posix()}', 'rev-parse', 'HEAD'],
                                cwd=root, capture_output=True, text=True)
        status = subprocess.run(['git', '-c', f'safe.directory={root.as_posix()}', 'status', '--porcelain'],
                                cwd=root, capture_output=True, text=True)
    except OSError:
        return {'commit': None, 'working_tree_modified': None}
    return {'commit': commit.stdout.strip() if commit.returncode == 0 else None,
            'working_tree_modified': bool(status.stdout) if status.returncode == 0 else None}


class FailFirstScript:
    """A declared pre-HTTP fault at the existing external model boundary."""
    def __init__(self, model):
        self.model, self.failed_once, self.observed_failure = model, False, False
        self.model_id = model.model_id

    @property
    def last_usage(self):
        return self.model.last_usage

    def decide(self, context):
        error = (context['memory'].get('last_observation') or {}).get('error') or {}
        self.observed_failure |= error.get('code') == 'SCRIPT_MODEL_UNAVAILABLE'
        return self.model.decide(context)

    def generate_script(self, context):
        if not self.failed_once:
            self.failed_once = True
            raise ModelUnavailable('Declared evaluation fault before script HTTP request')
        return self.model.generate_script(context)


def new_input(request_id, budget=14):
    return {'request_id': request_id, 'topic': '影芽剪辑字幕功能推广', 'budget_units': budget,
            'deadline_at': (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()}


def probe(model, request):
    catalog = load_catalog()
    tools = LocalTools(Request.model_validate(request), catalog, model, SystemClock())
    context = {'system': '这是工具协议探针。请调用search_materials，query为字幕、top_k为1，rationale一句话。',
               'tools': [tool for tool in tool_definitions() if tool['function']['name'] == 'search_materials'],
               'memory': {'request': request}, 'history_summary': [], 'limits': {}, 'messages': []}
    decision = model.decide(context)
    calls = decision.get('tool_calls') or []
    if len(calls) != 1 or calls[0]['function']['name'] != 'search_materials':
        raise Fault('PROBE_FAILED', 'The model did not choose the probe tool')
    call = calls[0]
    result = tools.search_materials(call['id'], json.loads(call['function']['arguments']))
    if not result['ok'] or not result['data']['materials']:
        raise Fault('PROBE_FAILED', 'Probe search returned no usable material')
    usage = [model.last_usage]
    context['messages'] = [decision, {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result, ensure_ascii=False)}]
    context['system'] = '工具协议探针：根据已经返回的真实检索结果用一句话说明素材，不要再次调用工具。'
    followup = model.decide(context)
    usage.append(model.last_usage)
    material = result['data']['materials'][0]
    draft = parse_script(model.generate_script({'topic': request['topic'],
        'material': {'material_id': material['material_id'], 'facts': material['facts']},
        'audience': '新手创作者', 'platform': '短视频平台', 'creative_brief': '展示字幕编辑功能',
        'output_schema': ScriptDraft.model_json_schema()}), material)
    usage.append(model.last_usage)
    return {'status': 'passed', 'decision': decision, 'observation': result, 'followup': followup,
            'script': draft.model_dump(mode='json'), 'usage': usage}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Explicitly allow paid HTTP requests')
    parser.add_argument('--output-dir', type=Path, default=Path('examples/live/S7'))
    parser.add_argument('--db', type=Path, default=Path('work/s7-live.db'))
    args = parser.parse_args(argv)
    if not args.live:
        parser.error('--live is required; no HTTP requests were made')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = args.output_dir / run_id
    summary = {'backend': 'deepseek', 'model': 'deepseek-v4-pro', 'run_id': run_id,
               'started_at': datetime.now(timezone.utc).isoformat(), 'cases': [], 'http_attempts': 0,
               'api_cost_usd': None, 'samples_per_case': 1, 'L04': 'NOT_RUN'}
    summary.update(source=source_snapshot(), entrypoint_argv=list(sys.argv),
                   model_parameters={'thinking': 'disabled', 'temperature': 0, 'stream': False,
                                     'planner_max_tokens': 2048, 'script_max_tokens': 1536})
    try:
        with DeepSeekModelClient() as model:
            try:
                result = probe(model, new_input('probe-' + run_id))
                write_json(output / 'probe.json', result)
                summary['probe'] = 'passed'
                for name in ('L01', 'L02', 'L03'):
                    request = new_input(name + '-' + run_id, 10 if name == 'L03' else 14)
                    folder = output / name
                    write_json(folder / 'input.json', request)
                    fixture = {'clock_source': 'SystemClock', 'fault_injection': None, 'preset_decisions': False}
                    delegate = FailFirstScript(model) if name == 'L02' else model
                    if name == 'L02':
                        fixture['fault_injection'] = {'tool': 'generate_script', 'attempt': 1,
                            'phase': 'before HTTP', 'origin': 'fixture_setup'}
                    write_json(folder / 'scenario.json', fixture)
                    started, before = datetime.now(timezone.utc).isoformat(), model.http_attempts
                    result = run_task(request, database=args.db, model=delegate, backend='deepseek')
                    result = export_task(result, database=args.db, directory=folder)
                    passed = result['status'] == 'completed'
                    if name == 'L02':
                        passed = delegate.failed_once and delegate.observed_failure and (
                            passed or result['reason'] == 'tool_failure')
                    metadata = {'case': name, 'passed': passed, 'status': result['status'], 'reason': result['reason'],
                        'started_at': started, 'ended_at': datetime.now(timezone.utc).isoformat(),
                        'http_attempts': model.http_attempts - before, 'usage': result['usage'],
                        'failure_observed': delegate.observed_failure if name == 'L02' else None,
                        'manifest': result['manifest'], 'output': str(folder / 'output.json'),
                        'backend': 'deepseek', 'model': model.model_id, 'entrypoint_argv': summary['entrypoint_argv'],
                        'source': summary['source'], 'model_parameters': summary['model_parameters']}
                    write_json(folder / 'run.json', metadata)
                    summary['cases'].append(metadata)
                    print(f"{name}: {result['status']} / {result['reason']} / passed={passed}", flush=True)
            finally:
                summary['http_attempts'] = model.http_attempts
    except (Fault, ModelUnavailable) as error:
        summary['error'] = {'code': error.code, 'message': str(error)}
        summary.setdefault('probe', 'failed')
    summary['ended_at'] = datetime.now(timezone.utc).isoformat()
    summary['passed'] = summary.get('probe') == 'passed' and len(summary['cases']) == 3 and all(c['passed'] for c in summary['cases'])
    write_json(output / 'summary.json', summary)
    print(json.dumps({'summary': str(output / 'summary.json'), 'passed': summary['passed'],
                      'http_attempts': summary['http_attempts'], 'error': summary.get('error')}, ensure_ascii=False), flush=True)
    return 0 if summary['passed'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
