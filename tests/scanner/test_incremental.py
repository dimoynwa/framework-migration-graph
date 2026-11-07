"""Incremental cache and parallel parsing (spec 026 FR-10, AC-9b, AC-9c).

The two requirements share one property: whatever the scanner does with the
cache or with ``--jobs``, the profile is the one a `--force`, single-process scan
would write. So the tests compare profiles, not timings — plus the one timing
claim the spec makes ("no change → nothing parsed"), which is observable as
``summary.parsed_files == 0`` instead of a stopwatch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from migration_planner.scanner import builtin, cli, contract
from migration_planner.scanner.cache import (
    CACHE_NAME,
    ScanCache,
    decode_facts,
    encode_facts,
    environment_digest,
)
from migration_planner.scanner.contract import (
    FileFacts,
    ModuleEnv,
    PathMap,
    SCANNER_VERSION,
    Usage,
)
from migration_planner.scanner.parallel import MIN_FILES_FOR_POOL, ParseJob, parse_parallel
from migration_planner.scanner.scan import cache_path_for, scan

from .conftest import run_cli, write

TYPESCRIPT = """\
import {{ Injectable }} from '@angular/core';
import {{ switchMap }} from 'rxjs/operators';

@Injectable()
export class Service {n} {{
  run() {{
    return switchMap(() => null);
  }}
}}
"""


@pytest.fixture(autouse=True)
def installed_registry():
    """``scan()`` installs nothing; a scan test asks for the shipped readers."""
    contract.reset_registry()
    builtin.install()
    yield
    contract.reset_registry()


def _repo(make_repo, files: int = 3, name: str = "repo") -> Path:
    """A small Angular-ish module: ``files`` TypeScript sources plus a manifest."""
    tree = {
        "package.json": json.dumps(
            {"name": "svc", "dependencies": {"@angular/core": "^19.2.0"}}
        ),
        "src/0.ts": TYPESCRIPT.format(n=0),
    }
    for index in range(1, files):
        tree[f"src/{index}.ts"] = TYPESCRIPT.format(n=index)
    return make_repo(tree, name=name)


def _stateless(profile: dict) -> dict:
    """The profile without the two time-dependent fields (AC-9c)."""
    payload = json.loads(json.dumps(profile))
    payload["generated"].pop("at")
    payload["generated"].pop("duration_ms")
    return payload


# --- the cache file --------------------------------------------------------


def test_first_scan_writes_a_cache_next_to_the_profile(make_repo) -> None:
    repo = _repo(make_repo)

    scan(repo)

    cache_file = repo / ".migration" / CACHE_NAME
    assert cache_file.is_file()
    payload = json.loads(cache_file.read_text())
    assert payload["scanner"] == SCANNER_VERSION
    assert "src/0.ts" in payload["files"]


def test_the_cache_lives_next_to_an_out_path_outside_the_repo(make_repo, tmp_path) -> None:
    """``--out`` elsewhere must not write into the service work tree (AC-11 runs)."""
    repo = _repo(make_repo)
    target = tmp_path / "elsewhere" / "profile.json"

    result = scan(repo, out=target)

    # Outside the repo the name carries the root's digest (one `--out`
    # directory may serve several services).
    assert result.cache_path == cache_path_for(repo.resolve(), target)
    assert result.cache_path.parent == target.resolve().parent
    assert result.cache_path.name.startswith("scan-cache-")
    assert result.cache_path.is_file()
    assert not (repo / ".migration").exists()


def test_two_repos_sharing_an_out_directory_keep_their_own_caches(
    make_repo, tmp_path
) -> None:
    first = _repo(make_repo, name="one")
    second = _repo(make_repo, name="two")
    shared = tmp_path / "shared"

    scan(first, out=shared / "one.json")
    scan(second, out=shared / "two.json")
    again = scan(first, out=shared / "one.json")

    assert again.summary.parsed_files == 0
    assert len(list(shared.glob("scan-cache-*.json"))) == 2


def test_a_cache_written_for_another_root_is_not_used(make_repo, tmp_path) -> None:
    repo = _repo(make_repo)
    scan(repo)
    cache_file = repo / ".migration" / CACHE_NAME
    payload = json.loads(cache_file.read_text())
    payload["root"] = "/somewhere/else"
    cache_file.write_text(json.dumps(payload))

    result = scan(repo, force=False)

    assert result.summary.parsed_files == len(result.discovery.sources)
    assert result.run_diagnostics == []  # another repo's cache is not corrupt


def test_a_cache_entry_round_trips_through_json(make_repo) -> None:
    facts = FileFacts(
        symbols=[
            Usage(key="npm:@angular/core#Injectable", file="src/a.ts", line=3, test=False)
        ],
        members=[Usage(key="npm:rxjs#map", file="src/a.ts", line=9, test=True)],
        diagnostics=[],
        local_declarations={"Service"},
        package_name=None,
        export_map={},
        star_exports=["pkg"],
    )

    restored = decode_facts(json.loads(json.dumps(encode_facts(facts))), "src/a.ts")

    assert restored == facts


def test_a_corrupt_cache_is_a_diagnostic_and_a_full_scan(make_repo) -> None:
    """AC-9b: a cache that cannot be read is never trusted, and never fatal."""
    repo = _repo(make_repo)
    scan(repo)
    cache_file = repo / ".migration" / CACHE_NAME
    cache_file.write_text("{ not json")

    result = scan(repo)

    # A run problem, not a repo fact: reported on the result, never in the
    # profile (an unchanged profile would keep it forever).
    assert [entry.kind for entry in result.run_diagnostics] == ["cache_corrupt"]
    assert "cache_corrupt" not in [entry.kind for entry in result.profile.diagnostics]
    # A full scan: every source was parsed despite the cache file being there.
    assert result.summary.parsed_files == len(result.discovery.sources)
    assert result.summary.cached_files == 0
    assert result.profile.symbols  # the facts are the ones a clean scan gives


def test_a_cache_from_another_scanner_version_is_dropped_whole(make_repo) -> None:
    repo = _repo(make_repo)
    scan(repo)
    cache_file = repo / ".migration" / CACHE_NAME
    payload = json.loads(cache_file.read_text())
    payload["scanner"] = "026.0-ancient"
    cache_file.write_text(json.dumps(payload))

    result = scan(repo)

    assert result.summary.parsed_files == len(result.discovery.sources)


# --- AC-9b incremental -----------------------------------------------------


def test_a_second_scan_parses_nothing_and_says_unchanged(make_repo) -> None:
    repo = _repo(make_repo)
    first = scan(repo)
    before = (repo / ".migration" / "profile.json").read_text()

    second = scan(repo)

    assert second.summary.parsed_files == 0
    assert second.summary.cached_files == len(first.discovery.sources)
    assert second.summary.unchanged is True
    assert second.summary.text().endswith("unchanged")
    # The profile was not rewritten: not even `generated.at` moved.
    assert (repo / ".migration" / "profile.json").read_text() == before


def test_editing_one_file_parses_only_that_file(make_repo) -> None:
    repo = _repo(make_repo, files=4)
    scan(repo)
    write(repo, "src/2.ts", TYPESCRIPT.format(n=99))

    result = scan(repo)

    assert result.summary.parsed_files == 1
    assert result.parsed_files == ["src/2.ts"]
    assert result.summary.unchanged is False


def test_an_incremental_profile_equals_a_forced_one(make_repo) -> None:
    """AC-9b: the cheap path must produce the expensive path's file."""
    repo = _repo(make_repo, files=4)
    scan(repo)
    write(repo, "src/1.ts", TYPESCRIPT.format(n=42))
    write(repo, "src/new.ts", TYPESCRIPT.format(n=7))

    incremental = scan(repo).profile.to_json()
    forced = scan(repo, force=True).profile.to_json()

    assert _stateless(json.loads(incremental)) == _stateless(json.loads(forced))


def test_a_touch_without_an_edit_reuses_the_facts(make_repo) -> None:
    """The stat moved but the hash did not: nothing is re-parsed."""
    repo = _repo(make_repo)
    scan(repo)
    target = repo / "src" / "1.ts"
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    result = scan(repo)

    assert result.summary.parsed_files == 0
    assert result.summary.unchanged is True


def test_force_ignores_the_cache_and_re_parses_every_file(make_repo) -> None:
    repo = _repo(make_repo)
    scan(repo)
    before = (repo / ".migration" / "profile.json").read_text()

    result = scan(repo, force=True)

    assert result.summary.parsed_files == len(result.discovery.sources)
    # `--force` always rewrites the profile: it is how a user regenerates one
    # that is stale for a reason `inputs_hash` cannot see.
    assert result.summary.unchanged is False
    assert result.written is True
    after = json.loads((repo / ".migration" / "profile.json").read_text())
    assert _stateless(after) == _stateless(json.loads(before))


def test_a_corrupt_cache_never_leaves_a_stale_diagnostic_in_the_profile(
    make_repo,
) -> None:
    """The case the review found: no profile yet, a corrupt cache, then a warm scan."""
    repo = _repo(make_repo)
    (repo / ".migration").mkdir()
    (repo / ".migration" / CACHE_NAME).write_text("garbage")

    first = scan(repo)
    second = scan(repo)

    assert [entry.kind for entry in first.run_diagnostics] == ["cache_corrupt"]
    profile = json.loads((repo / ".migration" / "profile.json").read_text())
    assert "cache_corrupt" not in [entry["kind"] for entry in profile["diagnostics"]]
    assert second.summary.unchanged is True
    assert second.summary.diagnostics == len(profile["diagnostics"])


def test_the_cli_reports_a_corrupt_cache_on_stderr_and_in_the_json_summary(
    make_repo,
) -> None:
    repo = _repo(make_repo)
    run_cli(str(repo))
    (repo / ".migration" / CACHE_NAME).write_text("garbage")

    code, stdout, stderr = run_cli(str(repo), "--json-summary")

    assert code == 0
    assert "warning: cache_corrupt" in stderr
    payload = json.loads(stdout)
    assert [item["kind"] for item in payload["run_diagnostics"]] == ["cache_corrupt"]


def test_a_file_changed_right_around_the_caching_scan_is_re_hashed(make_repo) -> None:
    """Racy stat: same size and mtime, new content, within the caching scan's tick."""
    repo = _repo(make_repo)
    target = repo / "src" / "1.ts"
    first = scan(repo)
    cache = ScanCache.load(repo / ".migration" / CACHE_NAME, root=repo.resolve())[0]
    stat = target.stat()
    # Same length, other content, mtime forced back to what the cache recorded.
    original = target.read_text()
    target.write_text(original.replace("switchMap", "concatMap"))  # same length
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert target.stat().st_size == stat.st_size
    assert cache.is_racy(stat.st_mtime_ns)

    result = scan(repo)

    assert result.summary.unchanged is False
    assert result.parsed_files == ["src/1.ts"]
    assert first.summary.parsed_files == 3


def test_an_old_file_is_trusted_by_its_stat_alone(make_repo) -> None:
    """Outside the racy window the stat is enough: the file is not even read."""
    repo = _repo(make_repo)
    old = 1_600_000_000 * 1_000_000_000
    for path in (repo / "src").glob("*.ts"):
        os.utime(path, ns=(old, old))
    scan(repo)
    cache = ScanCache.load(repo / ".migration" / CACHE_NAME, root=repo.resolve())[0]

    assert cache.started_ns > old
    assert not cache.is_racy(old)


def test_a_deleted_file_leaves_the_cache(make_repo) -> None:
    repo = _repo(make_repo, files=3)
    scan(repo)
    (repo / "src" / "2.ts").unlink()

    scan(repo)

    payload = json.loads((repo / ".migration" / CACHE_NAME).read_text())
    assert "src/2.ts" not in payload["files"]


def test_a_manifest_edit_invalidates_the_modules_cached_facts(make_repo) -> None:
    """An own package name is not in the file's bytes, so the env digest decides.

    A source's facts depend on what the manifest reader learned about its module
    (own packages, path map, declared groupIds). Editing only ``package.json``
    must not leave stale facts behind: an import of the new own package name is
    own code, and the old one is not.
    """
    repo = _repo(make_repo)
    scan(repo)
    write(
        repo,
        "package.json",
        json.dumps(
            {"name": "renamed", "dependencies": {"@angular/core": "^19.2.0"}}
        ),
    )

    result = scan(repo)

    assert result.summary.parsed_files == len(result.discovery.sources)


def test_option_changes_rewrite_the_profile(make_repo) -> None:
    """Different `--max-locations` is different output, never `unchanged` (FR-9)."""
    repo = _repo(make_repo)
    scan(repo)

    result = scan(repo, max_locations=1)

    assert result.summary.unchanged is False


def test_the_cache_stores_the_module_environment_digest(make_repo) -> None:
    repo = _repo(make_repo)
    scan(repo)

    payload = json.loads((repo / ".migration" / CACHE_NAME).read_text())
    entry = payload["files"]["src/0.ts"]
    assert entry["extractor"].endswith("extract_ts")
    assert entry["env"].startswith("sha256:")


def test_the_environment_digest_ignores_nothing_that_changes_facts() -> None:
    base = ModuleEnv(module=".", own_packages=("a",))
    variants = [
        ModuleEnv(module=".", own_packages=("b",)),
        ModuleEnv(module=".", own_packages=("a",), declared_dependencies=("rxjs",)),
        ModuleEnv(module=".", own_packages=("a",), group_ids=("org.x",)),
        ModuleEnv(module=".", own_packages=("a",), own_group_ids=("com.acme",)),
        ModuleEnv(module=".", own_packages=("a",), framework_names=("angular",)),
        ModuleEnv(module=".", own_packages=("a",), base_url_roots=("src",)),
        ModuleEnv(
            module=".",
            own_packages=("a",),
            path_map=PathMap(paths={"@app/*": ("src/app/*",)}),
        ),
    ]

    assert len({environment_digest(base), *(environment_digest(v) for v in variants)}) == len(
        variants
    ) + 1


# --- AC-9c determinism across --jobs --------------------------------------


def _many_file_repo(make_repo, count: int = MIN_FILES_FOR_POOL + 4) -> Path:
    files = {
        f"src/mod{index}/service{index}.ts": TYPESCRIPT.format(n=index)
        for index in range(count)
    }
    files["package.json"] = json.dumps(
        {"name": "svc", "dependencies": {"@angular/core": "^19.2.0"}}
    )
    return make_repo(files, name="many")


def test_jobs_one_and_jobs_eight_give_the_same_profile(make_repo, tmp_path) -> None:
    """AC-9c: the pool changes the wall clock, never the profile."""
    repo = _many_file_repo(make_repo)

    single = scan(repo, out=tmp_path / "j1.json", jobs=1, force=True).profile
    pooled = scan(repo, out=tmp_path / "j8.json", jobs=8, force=True).profile

    assert _stateless(json.loads(single.to_json())) == _stateless(
        json.loads(pooled.to_json())
    )


def test_parallel_parsing_falls_back_to_this_process_for_a_small_set(make_repo) -> None:
    """A pool for three files costs more than it saves; the result is the same."""
    from migration_planner.scanner.parallel import ParseJob as Job

    jobs = [
        (
            Job(
                relative=f"src/a{index}.ts",
                path=Path(f"src/a{index}.ts"),
                module=".",
                language="ts",
                test=False,
                data=TYPESCRIPT.format(n=index).encode("utf-8"),
            ),
            contract.source_extractors()["ts"],
            ModuleEnv(module="."),
        )
        for index in range(3)
    ]

    outcome = parse_parallel(jobs, jobs=8)

    assert len(outcome.facts) == 3
    assert outcome.failed == []


def test_a_pool_that_cannot_start_still_parses_every_file(monkeypatch) -> None:
    """A sandbox without process creation is a slower scan, not a failed one."""

    def refuse(*args, **kwargs):
        raise OSError("no processes here")

    monkeypatch.setattr("multiprocessing.context.BaseContext.Pool", refuse)
    jobs = [
        (
            ParseJob(
                relative=f"src/a{index}.ts",
                path=Path(f"src/a{index}.ts"),
                module=".",
                language="ts",
                test=False,
                data=TYPESCRIPT.format(n=index).encode("utf-8"),
            ),
            contract.source_extractors()["ts"],
            ModuleEnv(module="."),
        )
        for index in range(MIN_FILES_FOR_POOL + 1)
    ]

    outcome = parse_parallel(jobs, jobs=4)

    assert len(outcome.facts) == len(jobs)


# --- CLI -------------------------------------------------------------------


def test_cli_accepts_jobs_and_force(make_repo) -> None:
    repo = _repo(make_repo)

    code, stdout, _ = run_cli(str(repo), "--jobs", "2", "--force")

    assert code == cli.EXIT_OK
    assert "→" in stdout


def test_cli_rejects_a_negative_jobs_value(make_repo) -> None:
    repo = _repo(make_repo)

    code, _, stderr = run_cli(str(repo), "--jobs", "-1")

    assert code == cli.EXIT_USAGE
    assert "--jobs" in stderr


def test_cli_reports_unchanged_on_a_warm_scan(make_repo) -> None:
    repo = _repo(make_repo)
    run_cli(str(repo))

    code, stdout, _ = run_cli(str(repo))

    assert code == cli.EXIT_OK
    assert stdout.strip().endswith("unchanged")


def test_cli_json_summary_carries_the_cache_counts(make_repo) -> None:
    repo = _repo(make_repo)
    run_cli(str(repo))

    _, stdout, _ = run_cli(str(repo), "--json-summary")

    payload = json.loads(stdout)
    assert payload["unchanged"] is True
    assert payload["parsed_files"] == 0
    assert payload["cached_files"] == len(scan(repo).discovery.sources)


def test_use_cache_false_leaves_no_cache_file(make_repo) -> None:
    repo = _repo(make_repo)

    scan(repo, use_cache=False)

    assert not (repo / ".migration" / CACHE_NAME).exists()


def test_scan_cache_load_of_a_missing_file_is_empty(tmp_path) -> None:
    cache, diagnostics = ScanCache.load(tmp_path / CACHE_NAME)

    assert diagnostics == []
    assert len(cache) == 0


# --- a worker that dies never hangs the scan --------------------------------


def _java_repo(make_repo, count: int = MIN_FILES_FOR_POOL + 8) -> Path:
    files = {
        f"src/main/java/p/A{index}.java": (
            f"package p;\nimport org.springframework.stereotype.Component;\n"
            f"@Component class A{index} {{}}\n"
        )
        for index in range(count)
    }
    files["src/main/java/p/Crash.java"] = (
        "package p;\nimport org.springframework.stereotype.Service;\nclass Crash {}\n"
    )
    files["pom.xml"] = (
        "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
        "<version>1</version></project>"
    )
    return make_repo(files, name="crash")


def test_a_worker_that_dies_is_one_diagnostic_not_a_hang(
    make_repo, tmp_path, monkeypatch
) -> None:
    """A native crash in a worker: the scan finishes, the file is reported."""
    from tests.scanner.crashing_extractor import crashing_extract_java

    monkeypatch.setenv("SCANNER_TEST_PARENT_PID", str(os.getpid()))
    contract.register_source_extractor("java", crashing_extract_java)
    repo = _java_repo(make_repo)

    result = scan(repo, out=tmp_path / "p.json", jobs=4, force=True)

    crashes = [
        diagnostic
        for diagnostic in result.profile.diagnostics
        if diagnostic.kind == "extractor_crash"
    ]
    assert [diagnostic.file for diagnostic in crashes] == ["src/main/java/p/Crash.java"]
    component = next(
        entry
        for entry in result.profile.symbols
        if entry.key == "maven:org.springframework.stereotype.Component"
    )
    # Every other file kept its facts: two sites (import + annotation) each.
    assert component.files == MIN_FILES_FOR_POOL + 8
    assert "maven:org.springframework.stereotype.Service" not in {
        entry.key for entry in result.profile.symbols
    }


def test_a_crashed_file_is_not_cached_and_is_retried(make_repo, tmp_path, monkeypatch) -> None:
    from tests.scanner.crashing_extractor import crashing_extract_java

    monkeypatch.setenv("SCANNER_TEST_PARENT_PID", str(os.getpid()))
    contract.register_source_extractor("java", crashing_extract_java)
    repo = _java_repo(make_repo)
    result = scan(repo, out=tmp_path / "p.json", jobs=4, force=True)

    cache, _ = ScanCache.load(result.cache_path, root=repo.resolve())

    assert "src/main/java/p/Crash.java" not in cache.entries
    assert len(cache.entries) == MIN_FILES_FOR_POOL + 8
