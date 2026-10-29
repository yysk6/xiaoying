"""Rebuild S0 in a new virtualenv and test the wheel, not the source checkout."""

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
    parser.add_argument("--venv", type=Path, default=ROOT / "work/s0-clean")
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--report", type=Path, default=ROOT / "examples/tests/stages/S0/clean-install.json")
    args = parser.parse_args()
    target = args.venv.resolve()
    if target.exists():
        parser.error("Verification requires a NEW virtualenv path; choose --venv without deleting existing files")
    wheel = ROOT / "dist/xiaoying_content_planner-0.1.0-py3-none-any.whl"
    if not wheel.is_file():
        parser.error("Build the wheel first: python -m build --no-isolation")
    source = (["--no-index", "--find-links", str(args.wheelhouse.resolve())]
              if args.wheelhouse else ["--index-url", "https://pypi.org/simple", "--timeout", "20", "--retries", "1"])
    report = {"stage": "S0", "status": "running", "steps": [], "model_calls": 0,
              "offline_install": args.wheelhouse is not None, "cwd_is_repository": False}
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith(("CODEX", "DEEPSEEK", "OPENAI", "ANTHROPIC", "LANGSMITH", "LANGCHAIN"))
                   and key.upper() not in ("PYTHONPATH", "PYTHONHOME")}
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    environment["PIP_NO_INPUT"] = "1"

    def run(name, command):
        print(json.dumps({"step": name, "command": command}, ensure_ascii=False), flush=True)
        result = subprocess.run(command, cwd=tempfile.gettempdir(), env=environment,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", file=sys.stderr, flush=True)
        report["steps"].append({"name": name, "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError(f"S0 verification failed: {name}")

    try:
        venv.EnvBuilder(with_pip=True).create(target)
        python = str(target / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        pip = [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-deps"]
        run("runtime_from_lock", pip + source + ["-r", str(ROOT / "requirements.lock")])
        run("install_wheel", pip + ["--no-index", str(wheel)])
        run("runtime_pip_check", [python, "-m", "pip", "check"])
        run("wheel_import_outside_repository", [python, "-I", "-c",
            "import content_planner,sys,json; from pathlib import Path; "
            "assert Path(content_planner.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "assert content_planner.__version__=='0.1.0'; "
            "print(json.dumps({'version':content_planner.__version__,'module':content_planner.__file__}))"])
        run("development_from_lock", pip + source + ["-r", str(ROOT / "requirements-dev.lock")])
        run("development_pip_check", [python, "-m", "pip", "check"])
        run("s0_tests_against_wheel", [python, "-I", "-m", "pytest", "-q",
            "-c", str(ROOT / "pyproject.toml"), "-o", "pythonpath=", "--import-mode=importlib",
            str(ROOT / "tests/unit/test_environment.py"), str(ROOT / "tests/unit/test_package.py"),
            "--junitxml=" + str(args.report.resolve().with_name("clean-junit.xml"))])
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
