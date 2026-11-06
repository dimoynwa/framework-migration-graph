"""Isolation (spec 026 AC-10): the scanner runs in a service repo, offline.

Two independent checks:

1. **Import graph.** Nothing under ``migration_planner/`` or ``migration_keys/``
   may import ``migration_oracle``, ``neo4j``, ``langchain*`` or ``httpx`` (or
   any other HTTP client), because a service repo has none of them installed.
   The check is AST-based, so a lazy import inside a function is caught too.
2. **Clean environment.** ``migration-scan`` completes with no ``NEO4J_URI``,
   no ``.env`` and sockets blocked — the profile comes from local files only.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARDED_PACKAGES = ("migration_planner", "migration_keys")

# Anything a service scan must never depend on (AC-10).
FORBIDDEN_PREFIXES = (
    "migration_oracle",
    "neo4j",
    "langchain",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "http.client",
    "ssl",
    "sentence_transformers",
    "mcp",
    "streamlit",
)
# The planner walks the tree and shells out to ``git ls-files``; neither needs
# a socket. ``socket`` itself is allowed only as a *name*, never as an import.
FORBIDDEN_MODULES = FORBIDDEN_PREFIXES + ("socket",)


def _module_files(package: str) -> list[Path]:
    return sorted((REPO_ROOT / package).rglob("*.py"))


def _forbidden(module: str) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in FORBIDDEN_MODULES
    )


def _imports_of(tree: ast.AST) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # ``from . import x`` is internal
                continue
            found.append((node.module or "", node.lineno))
    return found


def _docstring_ids(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


@pytest.mark.parametrize("package", GUARDED_PACKAGES)
def test_guarded_packages_import_nothing_from_the_ingestion_stack(package: str) -> None:
    files = _module_files(package)
    assert files, f"{package} has no modules"

    violations = [
        f"{path.relative_to(REPO_ROOT)}:{line}: {module}"
        for path in files
        for module, line in _imports_of(ast.parse(path.read_text(encoding="utf-8")))
        if _forbidden(module)
    ]

    assert violations == [], "forbidden imports:\n" + "\n".join(violations)


@pytest.mark.parametrize("package", GUARDED_PACKAGES)
def test_guarded_packages_do_not_smuggle_a_module_path_in_a_string(
    package: str,
) -> None:
    """``importlib.import_module("migration_oracle")`` would evade the import check."""
    offenders: list[str] = []
    for path in _module_files(package):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_ids(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in docstrings:
                continue
            if _forbidden(node.value.strip()):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {node.value!r}")

    assert offenders == []


@pytest.mark.parametrize("package", GUARDED_PACKAGES)
def test_guarded_packages_do_not_read_graph_config(package: str) -> None:
    """``NEO4J_URI`` is required at import time, so one reference breaks a service scan."""
    for path in _module_files(package):
        assert "NEO4J_" not in path.read_text(encoding="utf-8"), path.relative_to(
            REPO_ROOT
        )


def test_scanner_runs_with_no_env_no_dotenv_and_no_network(
    polyglot_repo: Path, monkeypatch, tmp_path: Path
) -> None:
    """AC-10: clean environment, sockets blocked, valid profile still written."""
    for name in ("NEO4J_URI", "NEO4J_PASSWORD", "NEO4J_USERNAME", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no repository .env within reach

    def no_network(*args, **kwargs):
        raise AssertionError("the scanner opened a socket")

    monkeypatch.setattr(socket.socket, "connect", no_network, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network, raising=True)
    monkeypatch.setattr(socket, "create_connection", no_network, raising=True)

    from migration_planner.scanner.scan import scan

    result = scan(polyglot_repo, out=tmp_path / "profile.json")

    assert result.profile.schema_version == 1
    assert [module.path for module in result.profile.modules] == [
        ".",
        "backend",
        "tools",
    ]
    assert (tmp_path / "profile.json").is_file()


def test_importing_the_scanner_pulls_none_of_the_ingestion_stack() -> None:
    """``socket`` may come in transitively from ``subprocess``; the ingestion stack may not."""
    snippet = (
        "import sys\n"
        "import migration_planner.scanner\n"
        "guarded = ('migration_oracle', 'neo4j', 'langchain', 'httpx', 'requests',"
        " 'sentence_transformers', 'mcp', 'streamlit')\n"
        "loaded = [m for m in sys.modules if m.split('.')[0] in guarded]\n"
        "print(','.join(sorted(loaded)))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONNOUSERSITE": "1",
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ""
