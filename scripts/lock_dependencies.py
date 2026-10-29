"""Lock the installed project's dependency closure for the current environment.

Run after installing the project and its dev extra in a dedicated virtualenv.
This is a snapshot of resolved versions, not a dependency solver.
"""

from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


PROJECT = "xiaoying-content-planner"
ROOT = Path(__file__).resolve().parents[1]


def closure(extras):
    selected = {}
    pending = [(PROJECT, frozenset(extras))]
    visited = set()
    while pending:
        name, requested_extras = pending.pop()
        name = canonicalize_name(name)
        key = (name, requested_extras)
        if key in visited:
            continue
        visited.add(key)
        distribution = metadata.distribution(name)
        if name != PROJECT:
            selected[name] = distribution.version
        for raw in distribution.requires or []:
            requirement = Requirement(raw)
            if requirement.marker and not any(
                requirement.marker.evaluate({"extra": extra})
                for extra in ({""} | set(requested_extras))
            ):
                continue
            installed = metadata.version(requirement.name)
            if installed not in requirement.specifier:
                raise RuntimeError(f"Unsatisfied installed dependency: {requirement}")
            pending.append((requirement.name, frozenset(requirement.extras)))
    return selected


def write_lock(path, versions, prefix=""):
    header = (
        "# Resolved on Windows / Python 3.10; other targets are not yet verified.\n"
        "# Regenerate with: python scripts/lock_dependencies.py\n"
        "# Exact versions; artifact hashes are not enforced by this lock.\n"
    )
    lines = [f"{name}=={value}\n" for name, value in sorted(versions.items())]
    path.write_text(header + prefix + "".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    runtime = closure(set())
    development = closure({"dev"})
    # Pin the build frontend/backend as well, so --no-build-isolation is reproducible.
    for package in ("build", "setuptools", "wheel"):
        development[package] = metadata.version(package)
    write_lock(ROOT / "requirements.lock", runtime)
    write_lock(ROOT / "requirements-dev.lock", {
        name: value for name, value in development.items() if name not in runtime
    }, prefix="-r requirements.lock\n")
    print(f"runtime={len(runtime)}, development-only={len(set(development) - set(runtime))}")
