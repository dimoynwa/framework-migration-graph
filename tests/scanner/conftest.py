"""Scanner test helpers (spec 026).

The scanner is deliberately importable without ``migration_oracle``, so these
tests must not import the pipeline either — the isolation test (AC-10) proves
the same thing about the package itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "scanner"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def polyglot_repo(tmp_path: Path) -> Path:
    """Copy of the polyglot fixture: root npm module, Maven and Gradle modules."""
    target = tmp_path / "polyglot"
    shutil.copytree(FIXTURES / "polyglot", target)
    return target


@pytest.fixture()
def angular_app(tmp_path: Path) -> Path:
    """Copy of the angular-app fixture: package.json + lock + angular.json + 3 tsconfigs."""
    target = tmp_path / "angular-app"
    shutil.copytree(FIXTURES / "angular-app", target)
    return target


@pytest.fixture()
def npm_workspace(tmp_path: Path) -> Path:
    """Copy of the npm-workspace fixture: one root lockfile, two package modules."""
    target = tmp_path / "npm-workspace"
    shutil.copytree(FIXTURES / "npm-workspace", target)
    return target


@pytest.fixture()
def make_repo(tmp_path: Path) -> "callable":
    """Build a throwaway tree from ``{relative path: content}``."""

    def _make(files: dict[str, str | bytes], name: str = "repo") -> Path:
        repo = tmp_path / name
        repo.mkdir(parents=True, exist_ok=True)
        for relative, content in files.items():
            write(repo, relative, content)
        return repo

    return _make


@pytest.fixture()
def git_repo(make_repo) -> "callable":
    """An initialized git work tree, so discovery reads ``git ls-files``.

    Skips the test when git cannot initialize a repository (a sandbox that
    refuses writes inside ``.git/``): the behavior under test needs real git.
    """

    def _make(files: dict[str, str | bytes], name: str = "repo") -> Path:
        repo = make_repo(files, name=name)
        write(repo, ".gitignore", "ignored.ts\nnode_modules/\n")
        if not git_available(repo):
            pytest.skip("git cannot initialize a repository in this sandbox")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
        git(repo, "add", "-A")
        return repo

    return _make


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def git_available(repo: Path) -> bool:
    """``git init`` needs a writable ``.git/``; some sandboxes refuse it."""
    try:
        git(repo, "init", "-q")
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def write(root: Path, relative: str, content: str | bytes = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)
    return path


def read_profile(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(*args: str) -> tuple[int, str, str]:
    """The shipped ``main``, in process: ``(exit code, stdout, stderr)``."""
    import contextlib
    import io

    from migration_planner.scanner import cli

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(list(args))
    return code, stdout.getvalue(), stderr.getvalue()


def run_python(
    snippet: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """Run a snippet in a fresh interpreter (used by the isolation test)."""
    import os
    import sys

    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONNOUSERSITE": "1",
    }
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        cwd=str(REPO_ROOT),
    )
