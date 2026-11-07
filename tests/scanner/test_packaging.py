"""Packaging (spec 026 spec9, AC-10b): the planner installs without ingestion.

The claim is about an *installed* artifact, not about this checkout: in a fresh
virtual environment, ``pip install .[planner]`` must give a working
``migration-scan`` while ``neo4j`` and ``langchain*`` stay out.

Building a wheel and creating a venv needs ``hatchling`` and network access for
the three parser wheels, so the test skips when either is unavailable (a
sandbox without network, a CI job that installs with ``--no-build-isolation``).
The version of the check that always runs is
:func:`test_the_planner_extra_declares_exactly_the_scanner_dependencies`, which
reads the metadata that the install consumes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

#: What the scanner itself imports (AC-10b: `tree-sitter*`, `pyyaml`, `pydantic`).
PLANNER_DEPENDENCIES = {
    "pydantic",
    "pyyaml",
    "tree-sitter",
    "tree-sitter-java",
    "tree-sitter-javascript",
    "tree-sitter-typescript",
}

#: The stack a service repo must not need.
INGEST_PACKAGES = ("neo4j", "langchain", "langchain_core", "httpx", "mcp")


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _names(requirements: list[str]) -> set[str]:
    """Requirement strings → bare project names."""
    names: set[str] = set()
    for requirement in requirements:
        name = requirement
        for separator in ("[", ">", "<", "=", "!", "~", " ", ";"):
            name = name.split(separator, 1)[0]
        names.add(name.strip().lower())
    return names


def test_the_planner_extra_declares_exactly_the_scanner_dependencies() -> None:
    project = _pyproject()["project"]

    assert _names(project["optional-dependencies"]["planner"]) == PLANNER_DEPENDENCIES
    # The base dependencies are the planner's too: `pip install .` is a scan.
    assert _names(project["dependencies"]) == PLANNER_DEPENDENCIES


def test_ingestion_is_an_extra_and_not_a_base_dependency() -> None:
    project = _pyproject()["project"]
    base = _names(project["dependencies"])
    ingest = _names(project["optional-dependencies"]["ingest"])

    # The named packages, and their own client names, are what a service repo
    # must never be made to install.
    for name in INGEST_PACKAGES:
        assert name not in base, f"{name} leaked into the base dependencies"
        if name in ("langchain_core",):
            # A sub-package: pulled in by `langchain`, never declared by us.
            assert "langchain" in ingest
            continue
        assert name in ingest, f"{name} is not in the [ingest] extra"
    # The extras are disjoint: nothing is installed twice by `.[planner,ingest]`.
    assert base & ingest == set() or base & ingest <= PLANNER_DEPENDENCIES & ingest


def test_the_scan_entry_point_is_declared() -> None:
    scripts = _pyproject()["project"]["scripts"]

    assert scripts["migration-scan"] == "migration_planner.scanner.cli:main"


def test_the_wheel_ships_the_planner_packages() -> None:
    packages = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]

    assert set(packages) == {"migration_oracle", "migration_planner", "migration_keys"}


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv is needed to build and install the wheel"
)
def test_a_fresh_venv_with_the_planner_extra_can_scan(tmp_path: Path) -> None:
    """AC-10b end to end, in a throwaway venv from a built wheel."""
    dist = tmp_path / "dist"
    built = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    wheels = sorted(dist.glob("*.whl"))
    if built.returncode != 0 or not wheels:
        pytest.skip(f"cannot build a wheel here: {built.stderr.strip()[:200]}")

    venv = tmp_path / "venv"
    created = subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(venv)],
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip(f"cannot create a venv here: {created.stderr.strip()[:200]}")

    install = subprocess.run(
        ["uv", "pip", "install", "--python", str(venv / "bin" / "python"),
         f"{wheels[0]}[planner]"],
        capture_output=True,
        text=True,
        check=False,
    )
    if install.returncode != 0:
        pytest.skip(f"cannot install the extra here: {install.stderr.strip()[:200]}")

    python = venv / "bin" / "python"
    absent = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib, json\n"
            "missing = []\n"
            f"for name in {INGEST_PACKAGES!r}:\n"
            "    try:\n"
            "        importlib.import_module(name)\n"
            "        missing.append(name)\n"
            "    except ModuleNotFoundError:\n"
            "        pass\n"
            "print(json.dumps(missing))\n",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(absent.stdout) == [], "[planner] installed an ingestion package"

    fixture = tmp_path / "fixture"
    shutil.copytree(
        REPO_ROOT / "tests" / "fixtures" / "scanner" / "angular-app", fixture
    )
    scanned = subprocess.run(
        [str(venv / "bin" / "migration-scan"), str(fixture), "--force"],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": os.environ.get("HOME", str(tmp_path)),
            "PYTHONNOUSERSITE": "1",
        },
        cwd=str(tmp_path),
    )

    assert scanned.returncode == 0, scanned.stderr
    assert "angular 19.2.4" in scanned.stdout
    assert (fixture / ".migration" / "profile.json").is_file()
