"""Additional read-only audit of frozen Core20 artifacts; makes no HTTP calls."""
import hashlib
import json
from pathlib import Path
import re
import sys

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from content_planner.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[3]
run = Path(sys.argv[1]).resolve()
schemas = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in (ROOT / 'contracts').glob('*.schema.json')}
registry = Registry().with_resources((name, Resource.from_contents(value)) for name, value in schemas.items())
errors, counts = [], {'outputs': 0, 'trace_files': 0, 'trace_rows': 0, 'primary_trace_rows': 0}
for name, pattern in [('result', '**/output.json'), ('trace-event', '**/trace.jsonl')]:
    validator = Draft202012Validator(schemas[name + '.schema.json'], registry=registry, format_checker=FormatChecker())
    for path in sorted(run.glob(pattern)):
        values = [json.loads(path.read_text(encoding='utf-8'))] if name == 'result' else [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        counts['outputs' if name == 'result' else 'trace_files'] += 1
        if name == 'trace-event':
            counts['trace_rows'] += len(values)
        if any(list(validator.iter_errors(value)) for value in values):
            errors.append('schema:' + str(path.relative_to(run)))
details = []
catalog = load_catalog()
expected_catalog = {'materials': [m.model_dump(mode='json') for m in catalog.materials],
                    'pricing': catalog.pricing.model_dump(mode='json')}
for path in sorted(run.glob('E*/evidence.json')):
    bundle = json.loads(path.read_text(encoding='utf-8'))
    output, events, trace = bundle['output'], bundle['events'], bundle['trace']
    if bundle['catalog'] != expected_catalog:
        errors.append(path.parent.name + ':catalog_source_mismatch')
    counts['primary_trace_rows'] += len(trace)
    for item, event in zip(trace, events):
        arguments = event['args'].get('arguments', {key: value for key, value in event['args'].items() if key != 'recovery_of'})
        if item['args'] != (arguments or None) or item['rationale'] != (event['rationale'] or None):
            errors.append(path.parent.name + ':trace_args_or_rationale')
        summary, data = json.loads(item['observation_summary']), (event['result'] or {}).get('data') or {}
        for field in ('total_units', 'feasible', 'budget_gap_units', 'deadline_gap_minutes'):
            if field in data and summary.get(field) != data[field]:
                errors.append(path.parent.name + ':trace_quote_summary')
    results = [e['result'] for e in events if isinstance(e['result'], dict) and 'tool_call_id' in e['result']]
    if len({r['tool_call_id'] for r in output['tool_results']}) != len(output['tool_results']) or sorted(results, key=lambda r: r['tool_call_id']) != sorted(output['tool_results'], key=lambda r: r['tool_call_id']):
        errors.append(path.parent.name + ':tool_result_completeness')
    details.append({'case_id': path.parent.name, 'steps': output['execution_steps'],
                    'non_success_events': [{'event_id': e['event_id'], 'name': e['name'], 'phase': e['phase'], 'error_code': e['error_code']}
                                           for e in events if e['phase'] in {'failed', 'rejected', 'interrupted'}],
                    'fault_log': bundle['fault_log'], 'message': output['message']})
source = json.loads((run / 'source.json').read_text(encoding='utf-8'))
for relative, expected in source['sha256'].items():
    if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
        errors.append('source_hash_changed:' + relative)
secret_files = []
for path in run.rglob('*'):
    if path.is_file() and path.suffix in {'.json', '.jsonl', '.md', '.txt'}:
        if re.search(r'sk-[A-Za-z0-9]{20,}', path.read_text(encoding='utf-8')):
            secret_files.append(str(path.relative_to(run)))
result = {'passed': not errors and not secret_files, 'http_requests': 0, 'counts': counts,
          'source_hashes_verified': len(source['sha256']), 'errors': errors, 'secret_pattern_files': secret_files,
          'cases': details}
(ROOT / 'examples/tests/core20/artifact-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if key != 'cases'}, ensure_ascii=False))
raise SystemExit(0 if result['passed'] else 1)
