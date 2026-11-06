"""``migration_keys``: shared key formats and Angular data (spec 026 AC-1.4).

The keys are the contract between ingestion (025) and the planner (026): a rule
entity and a scanner fact must land on the same string, or the matcher in 028
compares nothing. Everything here runs without Neo4j and without
``migration_oracle``; the 025-side assertions live in
``tests/pipeline/test_shared_keys.py``, where the graph env is set up.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


from migration_keys import (
    ANGULAR_CONFIG_PREFIXES,
    ANGULAR_PACKAGES,
    ANGULAR_SYNTAX_TOKENS,
    DIAGNOSTIC_RE,
    cfg_key,
    config_file_for_key,
    diag_key,
    maven_key,
    npm_key,
    syntax_key,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_npm_class_and_member_keys() -> None:
    assert npm_key("@angular/core", "inject") == "npm:@angular/core#inject"
    assert (
        npm_key("@angular/core/testing", "TestBed", "get")
        == "npm:@angular/core/testing#TestBed.get"
    )


def test_npm_dependency_key_has_no_hash() -> None:
    assert npm_key("@angular/platform-server") == "npm:@angular/platform-server"


def test_npm_unresolved_package_uses_the_placeholder() -> None:
    assert npm_key("", "InjectFlags") == "npm:?#InjectFlags"
    assert npm_key("?", "InjectFlags", "x") == "npm:?#InjectFlags.x"


def test_maven_keys() -> None:
    assert maven_key("com.example.Foo") == "maven:com.example.Foo"
    assert (
        maven_key("org.springframework:spring-core")
        == "maven:org.springframework:spring-core"
    )


def test_cfg_key_with_and_without_a_file() -> None:
    assert cfg_key("package.json", "engines.node") == "cfg:package.json#engines.node"
    assert cfg_key("application.properties", "spring.datasource.password") == (
        "cfg:application.properties#spring.datasource.password"
    )
    assert cfg_key("", "engines.node") == "cfg:engines.node"


def test_syntax_and_diagnostic_keys() -> None:
    assert syntax_key("angular", "@defer") == "syntax:angular-template#@defer"
    assert (
        syntax_key("spring-boot", "@deprecated")
        == "syntax:spring-boot-template#@deprecated"
    )
    assert diag_key("NG8115") == "diag:NG8115"


def test_config_file_lookup_uses_the_shared_prefixes() -> None:
    assert (
        config_file_for_key("engines.node", ANGULAR_CONFIG_PREFIXES) == "package.json"
    )
    assert (
        config_file_for_key("compilerOptions.strict", ANGULAR_CONFIG_PREFIXES)
        == "tsconfig.json"
    )
    assert (
        config_file_for_key("projects.*.architect", ANGULAR_CONFIG_PREFIXES)
        == "angular.json"
    )
    assert config_file_for_key("something.else", ANGULAR_CONFIG_PREFIXES) == ""
    assert config_file_for_key("engines.node", {}) == ""


def test_angular_data_has_the_expected_shape() -> None:
    assert "@angular/core/testing" in ANGULAR_PACKAGES
    assert "@angular/core/rxjs-interop" in ANGULAR_PACKAGES
    assert "@defer" in ANGULAR_SYNTAX_TOKENS
    assert "@else if" in ANGULAR_SYNTAX_TOKENS
    # Ingestion imports these exact tuples (checked in the 025 test).
    assert isinstance(ANGULAR_PACKAGES, tuple)
    assert isinstance(ANGULAR_SYNTAX_TOKENS, tuple)


def test_diagnostic_regex_still_matches_ng_codes() -> None:
    assert DIAGNOSTIC_RE.match("NG8115") is not None
    assert DIAGNOSTIC_RE.match("ng8115") is None
    assert DIAGNOSTIC_RE.match("NG811") is None


def test_prefixes_cover_every_angular_config_file() -> None:
    assert set(ANGULAR_CONFIG_PREFIXES.values()) == {
        "package.json",
        "tsconfig.json",
        "angular.json",
    }


def test_migration_keys_imports_nothing_but_the_standard_library() -> None:
    """The planner installs this module without pydantic, neo4j or langchain (AC-10)."""
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "migration_keys").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.Import):
                offenders.extend(
                    f"{path.name}: {alias.name}"
                    for alias in node.names
                    if alias.name.split(".")[0] not in sys.stdlib_module_names
                )
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                module = node.module
                if module.split(".")[0] not in sys.stdlib_module_names | {
                    "migration_keys"
                }:
                    offenders.append(f"{path.name}: {module}")
    assert offenders == []


def test_migration_keys_imports_without_the_project_on_the_path() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import migration_keys; print(migration_keys.npm_key('p', 'A'))",
        ],
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
    assert completed.stdout.strip() == "npm:p#A"
