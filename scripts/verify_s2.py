"""Verify the S2 wheel and all offline tests in a new, isolated environment."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--venv', type=Path, default=ROOT / 'work/s2-clean')
    parser.add_argument('--wheelhouse', type=Path)
    parser.add_argument('--report', type=Path, default=ROOT / 'examples/tests/stages/S2/clean-install.json')
    args = parser.parse_args()
    target = args.venv.resolve()
    if target.exists():
        parser.error('Choose a NEW virtualenv path; existing environments are preserved')
    wheel = ROOT / 'dist/xiaoying_content_planner-0.1.0-py3-none-any.whl'
    if not wheel.is_file():
        parser.error('Build first: python -m build --no-isolation')
    source = (['--no-index', '--find-links', str(args.wheelhouse.resolve())] if args.wheelhouse else
              ['--index-url', 'https://pypi.org/simple', '--timeout', '20', '--retries', '1'])
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith(('CODEX', 'DEEPSEEK', 'OPENAI', 'ANTHROPIC', 'LANGSMITH', 'LANGCHAIN'))
                   and key.upper() not in ('PYTHONPATH', 'PYTHONHOME')}
    environment.update(PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_NO_INPUT='1', PYTHONIOENCODING='utf-8')
    report = {'stage': 'S2', 'status': 'running', 'steps': [], 'live_model_calls': 0,
              'offline_install': args.wheelhouse is not None, 'cwd_is_repository': False}
    log = []

    def run(name, command):
        result = subprocess.run(command, cwd=tempfile.gettempdir(), env=environment,
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        report['steps'].append({'name': name, 'command': command, 'exit_code': result.returncode})
        log.extend([name, result.stdout, result.stderr])
        print(f'{name}: exit {result.returncode}', flush=True)
        if result.returncode:
            raise RuntimeError(f'Verification failed: {name}')

    try:
        venv.EnvBuilder(with_pip=True).create(target)
        python = str(target / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
        run('install_locked_dependencies', [python, '-m', 'pip', 'install', '--no-deps', *source,
                                           '-r', str(ROOT / 'requirements-dev.lock')])
        run('install_wheel', [python, '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel)])
        run('pip_check', [python, '-m', 'pip', 'check'])
        run('wheel_import_and_resources', [python, '-I', '-c',
            "import sys,json; from pathlib import Path; from importlib import resources; "
            "from content_planner import catalog,contracts,domain,model,tools; "
            "modules=[catalog,contracts,domain,model,tools]; "
            "assert all(Path(m.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) for m in modules); "
            "data=resources.files('content_planner').joinpath('data'); "
            "assert all(data.joinpath(n+'.json').is_file() for n in ('materials','pricing','aliases')); "
            "assert catalog.load_catalog().search('caption',1)[0]['material_id']=='M01'; "
            "print(json.dumps({'modules':[m.__file__ for m in modules],'resources':'passed'}))"])
        run('all_tests_against_wheel', [python, '-I', '-m', 'pytest', '-q', '-c', str(ROOT / 'pyproject.toml'),
            '-o', 'pythonpath=', '--import-mode=importlib', str(ROOT / 'tests'),
            '--junitxml=' + str(args.report.resolve().with_name('clean-junit.xml'))])
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    args.report.with_suffix('.txt').write_text('\n'.join(log), encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
