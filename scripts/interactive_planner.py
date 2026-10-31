"""Interactive manual predictions using the application's existing service."""

import json
from pathlib import Path
import sqlite3
from datetime import datetime
import uuid

from content_planner.domain import Fault
from content_planner.reporting import markdown
from content_planner.service import export_task, resume_task, run_task, show_task
from content_planner.domain import SystemClock
from content_planner.intake import IntakeSession, LOCAL
from content_planner.prompts import INTAKE_VERSION


def console_session(model, source, target, *, database, output_root, clock=None, input_mode='natural'):
    if input_mode not in {'natural', 'json'}:
        raise ValueError('Unknown input mode')
    clock = clock or SystemClock()
    intake = IntakeSession(model, clock) if input_mode == 'natural' else None
    session_id, event_index, sequence = uuid.uuid4().hex, 0, 0

    def intake_event(event):
        nonlocal sequence
        sequence += 1
        path = Path(output_root) / 'intake.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'session_id': session_id, 'sequence': sequence,
                'at': clock.now().isoformat(), 'prompt_version': INTAKE_VERSION, **event}, ensure_ascii=False) + '\n')

    print('内容活动规划｜真实模型手工预测', file=target)
    print(('请用自然语言描述主题、整数模拟预算和截止时间；确认后启动业务。\n'
           '确认前的需求理解也可能产生API费用；草稿只存当前进程，重启丢失。\n'
           '“确认”提交，“取消/新建”清空草稿。' if intake else '粘贴一行请求JSON后回车。') +
          'show <ID>查看；resume <ID>续跑；exit退出。', file=target)
    print('每个新任务会调用真实模型；重复相同ID及输入只读。', file=target, flush=True)
    while True:
        print('\n' + ('需求 > ' if intake else 'JSON > '), end='', file=target, flush=True)
        line = source.readline()
        if not line or line.strip().lower() in {'exit', 'quit'}:
            return
        line = line.strip()
        if not line:
            continue
        try:
            if line.startswith('show '):
                result = show_task(line[5:].strip(), database=database)
            elif line.startswith('resume '):
                result = resume_task(line[7:].strip(), database=database, model=model, clock=clock)
            else:
                if intake:
                    reply = intake.receive(line)
                    for event in intake.events[event_index:]:
                        intake_event(event)
                    event_index = len(intake.events)
                    intake_event({'kind': 'reply', 'state': reply['state'], 'version': reply['version'],
                        'draft': reply['draft'], 'deadline_anchor': reply['deadline_anchor'],
                        'request_id': reply['request']['request_id'] if reply['request'] else None,
                        'intake_usage': reply['intake_usage']})
                    draft = reply['draft']
                    deadline = (datetime.fromisoformat(draft['deadline_at']).astimezone(LOCAL).strftime('%Y-%m-%d %H:%M:%S')
                                + ' 北京时间 UTC+08:00' if draft['deadline_at'] else '待补充')
                    print(f"主题：{draft['topic'] or '待补充'}\n预算上限：{draft['budget_units'] or '待补充'} 个模拟单位\n截止时间：{deadline}", file=target)
                    print(reply['message'], file=target)
                    print('需求理解用量：' + json.dumps(reply['intake_usage'], ensure_ascii=False), file=target, flush=True)
                    if reply['request'] is None:
                        continue
                    raw = reply['request']
                else:
                    try:
                        raw = json.loads(line)
                    except ValueError:
                        print('INVALID_JSON：请粘贴单行JSON，字段名使用英文双引号。', file=target, flush=True)
                        continue
                print('正在执行，请等待……', file=target, flush=True)
                result = run_task(raw, database=database, model=model, clock=clock,
                                  backend='mock' if model.model_id == 'mock' else 'deepseek')
            directory = Path(output_root) / (result['request_id'] or 'invalid-input')
            result = export_task(result, database=database, directory=directory)
            print(markdown(result), file=target)
            print('实际执行步骤：', file=target)
            for step in result['execution_steps']:
                print(f"  {step['tool']} attempt={step['attempt']} {step['status']} reused={step['reused']}"
                      + (f" error={step['error_code']}" if step['error_code'] else ''), file=target)
            print('业务用量：' + json.dumps(result['usage'], ensure_ascii=False), file=target)
            for warning in result['warnings']:
                print(warning['code'] + ': ' + warning['message'], file=target)
            print('结果目录：' + str(directory.resolve()), file=target, flush=True)
            if intake:
                intake_event({'kind': 'business_result', 'request_id': result['request_id'], 'status': result['status']})
        except Fault as error:
            print(error.code + ': ' + error.message, file=target, flush=True)
        except (sqlite3.Error, OSError):
            print('STORAGE_UNAVAILABLE：无法读取或保存本地结果。', file=target, flush=True)


def main(argv=None):
    import argparse
    import getpass
    import os
    import subprocess
    import sys
    import time
    import uuid

    from content_planner.deepseek import DeepSeekModelClient

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch-window', action='store_true', help='Open a separate Windows console')
    parser.add_argument('--key-pipe', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--key-stdin', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--launch-id', default=None, help=argparse.SUPPRESS)
    parser.add_argument('--input-mode', choices=['natural', 'json'], default='natural')
    parser.add_argument('--db', type=Path, default=Path('work/manual/runtime.db'))
    parser.add_argument('--output-root', type=Path, default=Path('work/manual/runs'))
    parser.add_argument('--ready-file', type=Path, default=Path('work/manual/session.json'))
    args = parser.parse_args(argv)
    if args.launch_window and os.name != 'nt':
        parser.error('--launch-window is supported on Windows; run directly in your terminal otherwise')
    if args.launch_window:
        launch_id = uuid.uuid4().hex
        key = getpass.getpass('DeepSeek API key (hidden): ')
        process = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--key-pipe',
            '--launch-id', launch_id,
            '--input-mode', args.input_mode,
            '--db', str(args.db.resolve()), '--output-root', str(args.output_root.resolve()),
            '--ready-file', str(args.ready_file.resolve())], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NEW_CONSOLE)
        try:
            process.stdin.write(key + '\n')
            process.stdin.close()
        finally:
            key = None
        for _ in range(50):
            try:
                current = json.loads(args.ready_file.read_text(encoding='utf-8'))
            except (FileNotFoundError, json.JSONDecodeError):
                current = None
            if current and current.get('launch_id') == launch_id:
                print(json.dumps(current, ensure_ascii=False), flush=True)
                return 0 if current['status'] == 'ready' else 1
            if process.poll() is not None:
                return 1
            time.sleep(0.1)
        print('Terminal started; readiness is not yet confirmed', flush=True)
        return 1
    if args.key_pipe:
        key = sys.stdin.readline().rstrip('\r\n')
        sys.stdin.close()
        sys.stdin = open('CONIN$', 'r', encoding='utf-8')
        sys.stdout = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
        sys.stderr = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW('内容活动规划 - DeepSeek ' + ('自然语言预测' if args.input_mode == 'natural' else 'JSON预测'))
    elif args.key_stdin:
        key = sys.stdin.readline().rstrip('\r\n')
    else:
        key = getpass.getpass('DeepSeek API key (hidden): ')

    def status(state, model=None):
        args.ready_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.ready_file.with_name(args.ready_file.name + f'.{os.getpid()}.tmp')
        temporary.write_text(json.dumps({'pid': os.getpid(), 'status': state, 'launch_id': args.launch_id,
            'model': 'deepseek-v4-pro', 'input_mode': args.input_mode, 'api_key_configured': model is not None,
            'http_attempts': model.http_attempts if model else 0,
            'database': str(args.db.resolve()), 'output_root': str(args.output_root.resolve())}, ensure_ascii=False), encoding='utf-8')
        temporary.replace(args.ready_file)

    model = None
    try:
        with DeepSeekModelClient(api_key=key) as model:
            key = None
            status('ready', model)
            console_session(model, sys.stdin, sys.stdout, database=args.db, output_root=args.output_root,
                            input_mode=args.input_mode)
    except KeyboardInterrupt:
        print('\n已退出。')
    except Fault as error:
        print(error.code + ': ' + error.message)
        return 1
    finally:
        key = None
        status('stopped', model)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
