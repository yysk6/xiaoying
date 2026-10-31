"""Opt-in real terminal evaluation; credentials cross only an anonymous stdin pipe."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from content_planner.catalog import load_catalog
from scripts.evaluate_budget import evaluate_evidence, read_database, write_json


ROOT = Path(__file__).resolve().parents[1]


def assess_dialog(records, expected):
    errors, confirmed, request_ids = [], False, []
    if len(records) != len(expected):
        errors.append('turn_count')
    for index, (record, wanted) in enumerate(zip(records, expected)):
        reply = record.get('reply') or {}
        if reply.get('state') != wanted['state']:
            errors.append(f'turn_{index}:state')
        if reply.get('draft') != wanted['draft']:
            errors.append(f'turn_{index}:fields')
        if wanted['state'] != 'submitted' and not confirmed and any(record['database'].values()):
            errors.append(f'turn_{index}:business_before_confirmation')
        if wanted['state'] == 'submitted':
            confirmed = True
            request_ids.append(reply.get('request_id'))
    if request_ids and (not all(request_ids) or len(set(request_ids)) != 1):
        errors.append('confirmation_identity')
    submitted = [r for r, e in zip(records, expected) if e['state'] == 'submitted']
    if len(submitted) > 1 and submitted[-1]['database'] != submitted[0]['database']:
        errors.append('repeat_confirmation_wrote_business_state')
    return {'passed': not errors, 'errors': errors, 'turns': len(records),
            'extraction_turns': sum(e['state'] != 'submitted' for e in expected),
            'request_id': request_ids[0] if request_ids else None}


def database_counts(path):
    if not path.exists():
        return dict(requests=0, events=0, plans=0)
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        return {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                for table in ('requests', 'events', 'plans')}


def assess_business(folder, case, confirmed_request):
    paths = list((folder / 'runs').glob('nl-*/output.json'))
    if len(paths) != 1:
        return None
    output = json.loads(paths[0].read_text(encoding='utf-8'))
    request_id = output['request_id']
    with sqlite3.connect((folder / 'runtime.db').resolve().as_uri() + '?mode=ro', uri=True) as db:
        request = json.loads(db.execute('SELECT input_json FROM requests WHERE request_id=?', (request_id,)).fetchone()[0])
    events, plans = read_database(folder / 'runtime.db', request_id)
    catalog = load_catalog()
    bundle = dict(input=request, confirmed_request=confirmed_request, output=output, events=events, plans=plans, decisions=[],
                  catalog={'materials': [m.model_dump(mode='json') for m in catalog.materials],
                           'pricing': catalog.pricing.model_dump(mode='json')})
    write_json(folder / 'evidence.json', bundle)
    business = evaluate_evidence('L05' if case == 'N-A05-09' else case, bundle)
    business['confirmed_request_match'] = request == confirmed_request
    if not business['confirmed_request_match']:
        business['errors'].append('confirmed_request_mismatch')
        business['invariants_pass'] = False
    business['case'] = case
    business['decision_observation_audit'] = 'NOT_RUN; no live ModelClient observer; persisted events retained'
    return business


class Terminal:
    """Drive the same CLI and prompts used by a human; never echo credential input."""
    def __init__(self, key, folder):
        self.folder, self.output = folder, ''
        self.characters = queue.Queue()
        self.process = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/interactive_planner.py'),
            '--key-stdin', '--db', str(folder / 'runtime.db'), '--output-root', str(folder / 'runs'),
            '--ready-file', str(folder / 'session.json')], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding='utf-8', bufsize=1)

        def read():
            for char in iter(lambda: self.process.stdout.read(1), ''):
                self.characters.put(char)
            self.characters.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        self.process.stdin.write(key + '\n')
        self.process.stdin.flush()

    def wait_prompt(self, timeout=480):
        deadline = time.monotonic() + timeout
        current = ''
        while time.monotonic() < deadline:
            try:
                char = self.characters.get(timeout=min(0.5, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if char is None:
                raise RuntimeError('TERMINAL_EXITED')
            self.output += char
            current += char
            if current.endswith('需求 > '):
                return
        raise RuntimeError('TERMINAL_TIMEOUT')

    def turn(self, text):
        self.process.stdin.write(text + '\n')
        self.process.stdin.flush()
        self.wait_prompt()

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write('exit\n')
                self.process.stdin.close()
                self.process.wait(timeout=50)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=10)
        self.reader.join(timeout=2)
        while not self.characters.empty():
            char = self.characters.get_nowait()
            if char is not None:
                self.output += char
        (self.folder / 'terminal.txt').write_text(self.output, encoding='utf-8')


def cases(now):
    local = timezone(timedelta(hours=8))
    date = (now.astimezone(local) + timedelta(days=1)).date()
    deadline = datetime(date.year, date.month, date.day, 18, tzinfo=local).astimezone(timezone.utc).isoformat()
    topic = '影芽剪辑字幕功能推广'
    complete = dict(topic=topic, budget_units=10, deadline_at=deadline)
    def want(state, draft):
        return dict(state=state, draft=draft)
    return [
        ('N-A01', ['主题是影芽剪辑字幕功能推广，预算10个模拟单位，明天下午六点前完成。', '确认'],
         [want('ready', complete), want('submitted', complete)]),
        ('N-A02-03', ['主题是影芽剪辑字幕功能推广。', '预算10个模拟单位。', '明天下午六点前完成。',
                     '预算改成8，其他不变。', '确认', '确认'],
         [want('collecting', dict(topic=topic, budget_units=None, deadline_at=None)),
          want('collecting', dict(topic=topic, budget_units=10, deadline_at=None)), want('ready', complete),
          *[want(state, {**complete, 'budget_units': 8}) for state in ('ready', 'submitted', 'submitted')]]),
        ('N-A05-09', ['主题是影芽剪辑字幕功能推广，预算5个模拟单位，尽快完成。',
                     '截止时间改为明天下午六点。', '确认'],
         [want('collecting', dict(topic=topic, budget_units=5, deadline_at=None)),
          *[want(state, {**complete, 'budget_units': 5}) for state in ('ready', 'submitted')]]),
    ]


def run_case(case, turns, expected, key, folder):
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / 'scenario.json', {'case': case, 'turns': turns, 'expected': expected,
        'fixture': 'synthetic evaluation inputs only', 'fault_injection': None,
        'entrypoint': 'scripts/interactive_planner.py (ordinary subprocess stdin/stdout)'})
    terminal, records, error = None, [], None
    started = time.monotonic()
    try:
        terminal = Terminal(key, folder)
        terminal.wait_prompt(timeout=30)
        write_json(folder / 'startup.json', {'session': json.loads((folder / 'session.json').read_text(encoding='utf-8')),
                                            'database': database_counts(folder / 'runtime.db')})
        for text in turns:
            before = database_counts(folder / 'runtime.db')
            at = datetime.now(timezone.utc).isoformat()
            tick = time.monotonic()
            terminal.turn(text)
            events = [json.loads(line) for line in (folder / 'runs/intake.jsonl').read_text(encoding='utf-8').splitlines()]
            reply = next((e for e in reversed(events) if e['kind'] == 'reply'), None)
            records.append({'sent_at': at, 'elapsed_seconds': round(time.monotonic() - tick, 3),
                            'reply': reply, 'database_before': before, 'database': database_counts(folder / 'runtime.db')})
            write_json(folder / 'turns.json', records)
            print(json.dumps({'case': case, 'turn': len(records), 'state': reply['state'] if reply else None,
                              'database': records[-1]['database']}, ensure_ascii=False), flush=True)
    except (RuntimeError, OSError, ValueError) as failure:
        error = type(failure).__name__ + ':' + (str(failure) if isinstance(failure, RuntimeError) else 'EVIDENCE_IO_ERROR')
    finally:
        if terminal:
            terminal.close()
    dialog = assess_dialog(records, expected)
    business = assess_business(folder, case, {**expected[-1]['draft'], 'request_id': dialog['request_id']})
    session = json.loads((folder / 'session.json').read_text(encoding='utf-8')) if (folder / 'session.json').exists() else None
    result = dict(case=case, dialog=dialog, business=business, error=error,
        elapsed_seconds=round(time.monotonic() - started, 3), session=session,
        technical_pass=not error and dialog['passed'] and business is not None
                       and business['invariants_pass'] and business['behavior_pass'],
        content_pass=None, passed=None, content_review='PENDING')
    write_json(folder / 'assessment.json', result)
    return result


def main(argv=None):
    import argparse
    import getpass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output-root', type=Path, default=Path('examples/live/intake'))
    parser.add_argument('--cases', nargs='+', choices=['N-A01', 'N-A02-03', 'N-A05-09'],
                        help='Explicit diagnostic subset; default all three, no automatic retries')
    args = parser.parse_args(argv)
    if not args.live:
        parser.error('--live is required; this evaluation makes paid model calls')
    key = getpass.getpass('DeepSeek API key (hidden): ')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    folder = args.output_root.resolve() / run_id
    folder.mkdir(parents=True, exist_ok=False)
    files = ['src/content_planner/intake.py', 'src/content_planner/deepseek.py', 'src/content_planner/prompts.py',
             'scripts/interactive_planner.py', 'scripts/evaluate_intake.py', 'scripts/evaluate_budget.py', 'requirements.lock']
    write_json(folder / 'source.json', {'baseline_commit': '6885d85e6da9a6b4e8e4fe2af5b39ad6cb429711',
        'working_tree': 'uncommitted development; see source hashes', 'python': sys.version,
        'platform': platform.platform(), 'model': 'deepseek-v4-pro',
        'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}})
    results = []
    try:
        for case, turns, expected in cases(datetime.now(timezone.utc)):
            if args.cases and case not in args.cases:
                continue
            result = run_case(case, turns, expected, key, folder / case)
            results.append(result)
            write_json(folder / 'summary.json', {'run_id': run_id, 'cases': results,
                'technical_pass': all(r['technical_pass'] for r in results), 'content_pass': None, 'passed': None})
            print(json.dumps({'case': case, 'technical_pass': result['technical_pass'], 'error': result['error']}, ensure_ascii=False), flush=True)
    finally:
        key = None
    print(str(folder), flush=True)
    return 0 if all(r['technical_pass'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
