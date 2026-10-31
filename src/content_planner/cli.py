"""Portable offline command line entry point."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from pydantic import ValidationError

from .contracts import Request
from .domain import Fault
from .reporting import empty_result
from .service import export_task, resume_task, run_task, show_task


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Fault('CONFIG_ERROR', message)


def main(argv=None):
    parser = _Parser(description='内容活动规划（离线版）')
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--input', required=True, type=Path)
    run.add_argument('--backend', choices=('mock', 'deepseek'), default='mock')
    run.add_argument('--mock-scenario', type=Path)
    show = commands.add_parser('show')
    show.add_argument('--request-id', required=True)
    resume = commands.add_parser('resume')
    resume.add_argument('--request-id', required=True)
    resume.add_argument('--mock-scenario', type=Path)
    for command in (run, show, resume):
        command.add_argument('--db', type=Path, default=Path('work/runtime.db'))
        command.add_argument('--output-dir', type=Path)
    args = None
    try:
        args = parser.parse_args(argv)
        if args.command == 'run':
            if args.backend != 'mock':
                raise Fault('CONFIG_ERROR', 'DeepSeek后端尚未开放；真实模型接入归S7')
            try:
                raw = json.loads(args.input.read_text(encoding='utf-8-sig'))
            except (OSError, ValueError) as error:
                raise Fault('INVALID_ARGUMENT', 'Cannot read a valid input JSON file') from error
            result = run_task(raw, database=args.db, mock_scenario=args.mock_scenario)
        else:
            request_id = Request(request_id=args.request_id).request_id
            result = (resume_task(request_id, database=args.db, mock_scenario=args.mock_scenario)
                      if args.command == 'resume' else show_task(request_id, database=args.db))
        directory = args.output_dir or Path('work/runs') / (result['request_id'] or 'invalid-input')
        result = export_task(result, database=args.db, directory=directory)
    except (Fault, sqlite3.Error, OSError, ValueError, ValidationError) as error:
        code = error.code if isinstance(error, Fault) else ('STORAGE_UNAVAILABLE' if isinstance(error, (OSError, sqlite3.Error)) else 'CONFIG_ERROR')
        message = error.message if isinstance(error, Fault) else 'Cannot load task configuration or storage'
        if code in {'STORAGE_UNAVAILABLE', 'SCHEMA_VERSION_MISMATCH'} or isinstance(error, sqlite3.Error):
            print(f'{code}: {message}', file=sys.stderr)
            return 1
        result = empty_result(backend=getattr(args, 'backend', 'mock'), reason=code, message=message)
    for warning in result['warnings']:
        print(f"{warning['code']}: {warning['message']}", file=sys.stderr)
    if result['reason']:
        print(f"{result['reason']}: {result['message']}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False))
    return {'completed': 0, 'needs_input': 2, 'incomplete': 3, 'running': 3}[result['status']]
