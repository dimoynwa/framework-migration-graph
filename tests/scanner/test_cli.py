"""CLI contract (spec 026 AC-1.1, FR-1).

``migration-scan [PATH] [--out FILE] [--force] [--max-locations N]
[--include-tests/--no-include-tests] [--json-summary]``
"""

from __future__ import annotations

import json
from pathlib import Path

from migration_planner.scanner import cli
from migration_planner.scanner.contract import SCANNER_VERSION

from .conftest import read_profile, run_cli, write


def test_help_exits_zero_and_documents_the_flags() -> None:
    code, stdout, _ = run_cli("--help")

    assert code == cli.EXIT_OK
    for flag in (
        "--out",
        "--force",
        "--max-locations",
        "--include-tests",
        "--no-include-tests",
        "--json-summary",
    ):
        assert flag in stdout
    # The exit codes are part of the contract (FR-1).
    assert "2 no supported manifest" in stdout


def test_version_exits_zero() -> None:
    code, stdout, _ = run_cli("--version")

    assert code == cli.EXIT_OK
    assert SCANNER_VERSION in stdout


def test_default_path_is_cwd_and_default_out_is_under_it(
    make_repo, monkeypatch, tmp_path: Path
) -> None:
    repo = make_repo({"package.json": '{"name": "demo"}'})
    monkeypatch.chdir(repo)

    code, stdout, _ = run_cli()

    assert code == cli.EXIT_OK
    profile = read_profile(repo / ".migration" / "profile.json")
    assert profile["schema"] == 1
    assert profile["generated"]["root"] == "."
    assert ".migration/profile.json" in stdout


def test_out_flag_writes_where_asked(make_repo, tmp_path: Path) -> None:
    repo = make_repo({"package.json": '{"name": "demo"}'})
    target = tmp_path / "elsewhere" / "profile.json"

    code, stdout, _ = run_cli(str(repo), "--out", str(target))

    assert code == cli.EXIT_OK
    assert target.is_file()
    assert str(target) in stdout
    assert not (repo / ".migration").exists()


def test_summary_line_has_a_stable_shape(make_repo) -> None:
    repo = make_repo({"package.json": '{"name": "demo"}', "src/a.ts": "const a = 1;\n"})

    code, stdout, _ = run_cli(str(repo))

    assert code == cli.EXIT_OK
    line = stdout.strip().splitlines()[0]
    # Every count is printed even when zero, so later specs keep the format.
    assert line.startswith("scanned 2 files · no framework · 0 deps · 0 symbols")
    assert "0 members · 0 config · 0 template tokens" in line
    assert "0 diagnostics" in line
    assert "→ .migration/profile.json" in line
    assert line.endswith("s)")


def test_json_summary_parses_and_agrees_with_the_text_line(make_repo) -> None:
    repo = make_repo({"package.json": '{"name": "demo"}', "src/a.ts": "const a = 1;\n"})

    text_code, text_out, _ = run_cli(str(repo), "--force")
    json_code, json_out, _ = run_cli(str(repo), "--json-summary")

    assert text_code == json_code == cli.EXIT_OK
    payload = json.loads(json_out)
    assert payload["files_scanned"] == 2
    assert payload["framework"] is None
    assert payload["symbols"] == payload["members"] == payload["config"] == 0
    assert payload["scanner"] == SCANNER_VERSION
    text_line = text_out.strip().splitlines()[0]
    assert f"scanned {payload['files_scanned']} files" in text_line
    assert f"{payload['dependencies']} deps" in text_line
    assert f"{payload['diagnostics']} diagnostics" in text_line


def test_no_supported_manifest_exits_2_and_writes_nothing(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    write(empty, "src/a.ts", "const a = 1;\n")
    write(empty, "README.md", "# nothing to scan\n")

    code, _, stderr = run_cli(str(empty))

    assert code == cli.EXIT_NO_MANIFEST
    assert "no supported manifest" in stderr
    assert not (empty / ".migration").exists()


def test_a_supported_manifest_counts_even_without_a_reader(tmp_path: Path) -> None:
    """Exit code 2 depends on the file name, not on an implemented reader (FR-1)."""
    for name in (
        "gradle/libs.versions.toml",
        "package.json",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "angular.json",
        "tsconfig.json",
        "gradle.properties",
        "application.yml",
    ):
        repo = tmp_path / name.replace("/", "_").replace(".", "-")
        write(repo, name, "{}\n")

        assert run_cli(str(repo))[0] == cli.EXIT_OK, name


def test_a_lockfile_alone_is_not_a_supported_manifest(tmp_path: Path) -> None:
    """The Goal diagram lists ``package-lock.json`` under package.json, not on its own."""
    repo = tmp_path / "lock-only"
    write(repo, "package-lock.json", "{}")

    assert run_cli(str(repo))[0] == cli.EXIT_NO_MANIFEST


def test_usage_errors_exit_1(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write(repo, "package.json", "{}\n")

    assert run_cli(str(repo), "--max-locations", "-1")[0] == cli.EXIT_USAGE
    assert run_cli(str(repo), "--nope")[0] == cli.EXIT_USAGE
    assert run_cli(str(tmp_path / "missing"))[0] == cli.EXIT_USAGE
    assert run_cli(str(repo / "package.json"))[0] == cli.EXIT_USAGE


def test_gitignore_hint_is_printed_on_the_first_run_and_not_written(
    make_repo, capsys
) -> None:
    repo = make_repo({"package.json": '{"name": "demo"}'})
    write(repo, ".gitignore", "node_modules/\n")

    code, _, stderr = run_cli(str(repo))

    assert code == cli.EXIT_OK
    assert "add .migration/ to .gitignore" in stderr
    # A hint, never an edit.
    assert (repo / ".gitignore").read_text() == "node_modules/\n"


def test_gitignore_hint_is_silent_once_migration_is_ignored(make_repo) -> None:
    repo = make_repo({"package.json": '{"name": "demo"}'})
    write(repo, ".gitignore", "node_modules/\n.migration/\n")

    code, _, stderr = run_cli(str(repo))

    assert code == cli.EXIT_OK
    assert "add .migration/ to .gitignore" not in stderr
