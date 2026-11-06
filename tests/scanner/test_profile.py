"""Profile model, merge, determinism and writer (spec 026 AC-9a, FR-9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from migration_planner.scanner.contract import (
    ConfigFact,
    DependencyFact,
    Diagnostic,
    FileFacts,
    FrameworkFact,
    SCANNER_VERSION,
    Usage,
)
from migration_planner.scanner.profile import (
    SCHEMA_VERSION,
    FactAccumulator,
    Generated,
    Profile,
    Summary,
    default_profile_path,
    inputs_hash,
    utc_now,
    write_profile,
)
from migration_planner.scanner.scan import scan

from .conftest import read_profile, write

FIXED_TIME = utc_now()


def _usage(key: str, file: str = "src/a.ts", line: int = 1, **kwargs) -> Usage:
    return Usage(key=key, file=file, line=line, **kwargs)


def test_profile_json_uses_the_schema_field_name() -> None:
    profile = Profile(generated=Generated(at=FIXED_TIME))

    payload = json.loads(profile.to_json())

    assert payload["schema"] == SCHEMA_VERSION
    assert "schema_version" not in payload
    # Every section the later specs fill exists now, empty.
    for section in (
        "modules",
        "dependencies",
        "symbols",
        "members",
        "side_effect_imports",
        "wildcard_imports",
        "config",
        "templates",
        "diagnostics",
    ):
        assert payload[section] == []
    assert payload["framework"] is None


def test_schema_field_round_trips() -> None:
    profile = Profile.model_validate({"schema": 7, "generated": {"at": FIXED_TIME}})

    assert profile.schema_version == 7
    assert json.loads(profile.to_json())["schema"] == 7


def test_keys_are_sorted_in_the_json() -> None:
    profile = Profile(generated=Generated(at=FIXED_TIME, files_scanned=5))
    text = profile.to_json()

    assert (
        text.index('"config"') < text.index('"dependencies"') < text.index('"symbols"')
    )
    assert text.endswith("\n")


def _entries(accumulator: FactAccumulator, attr: str) -> list:
    return getattr(accumulator, attr)()


def test_symbol_count_is_exact_while_locations_are_capped() -> None:
    accumulator = FactAccumulator(max_locations=5)
    accumulator.add_file(
        FileFacts(
            symbols=[
                _usage(
                    "npm:@angular/core#inject", file=f"src/f{index}.ts", line=index + 1
                )
                for index in range(30)
            ]
        )
    )

    entries = _entries(accumulator, "symbol_entries")

    assert len(entries) == 1
    entry = entries[0]
    assert entry.key == "npm:@angular/core#inject"
    assert entry.count == 30
    assert entry.files == 30
    assert len(entry.locations) == 5
    assert entry.truncated is True


def test_locations_are_sorted_and_deduplicated() -> None:
    accumulator = FactAccumulator()
    accumulator.add_file(
        FileFacts(
            symbols=[
                _usage("npm:p#B", file="src/b.ts", line=9),
                _usage("npm:p#B", file="src/a.ts", line=4),
                _usage("npm:p#B", file="src/a.ts", line=4),
                _usage("npm:p#A", file="src/z.ts", line=1),
            ]
        )
    )

    entries = _entries(accumulator, "symbol_entries")

    assert [entry.key for entry in entries] == ["npm:p#A", "npm:p#B"]
    b = entries[1]
    # One site per (file, line): the repeated import on a.ts:4 counts once.
    assert b.count == 2
    assert b.files == 2
    assert [(location.file, location.line) for location in b.locations] == [
        ("src/a.ts", 4),
        ("src/b.ts", 9),
    ]
    assert b.truncated is False


def test_test_flag_survives_into_locations() -> None:
    accumulator = FactAccumulator()
    accumulator.add_file(
        FileFacts(
            members=[
                _usage(
                    "npm:@angular/core/testing#TestBed.get", file="a.spec.ts", test=True
                )
            ]
        )
    )

    entry = _entries(accumulator, "member_entries")[0]

    assert entry.locations[0].test is True


def test_type_only_is_true_only_when_every_usage_is_type_only() -> None:
    accumulator = FactAccumulator()
    accumulator.add_file(FileFacts(symbols=[_usage("npm:p#A", type_only=True)]))
    accumulator.add_file(FileFacts(symbols=[_usage("npm:p#B", type_only=True)]))
    accumulator.add_file(FileFacts(symbols=[_usage("npm:p#B", type_only=False)]))

    entries = {entry.key: entry for entry in _entries(accumulator, "symbol_entries")}

    assert entries["npm:p#A"].type_only is True
    assert entries["npm:p#B"].type_only is False


def test_max_locations_zero_keeps_the_exact_count() -> None:
    accumulator = FactAccumulator(max_locations=0)
    accumulator.add_file(FileFacts(side_effect_imports=[_usage("npm:zone.js")]))

    entry = _entries(accumulator, "side_effect_entries")[0]

    assert entry.count == 1
    assert entry.locations == []
    assert entry.truncated is True


def test_dependencies_are_deduplicated_by_key_and_module() -> None:
    accumulator = FactAccumulator()
    accumulator.add_dependency(
        DependencyFact(
            key="npm:@angular/core", name="@angular/core", range="^19.2.0", module="."
        )
    )
    accumulator.add_dependency(
        DependencyFact(
            key="npm:@angular/core", name="@angular/core", range="^19.2.0", module="."
        )
    )
    accumulator.add_dependency(
        DependencyFact(
            key="npm:@angular/core", name="@angular/core", range="^19.2.0", module="ui"
        )
    )

    entries = _entries(accumulator, "dependency_entries")

    assert [(entry.key, entry.module) for entry in entries] == [
        ("npm:@angular/core", "."),
        ("npm:@angular/core", "ui"),
    ]


def test_config_values_are_kept_once_per_key() -> None:
    accumulator = FactAccumulator()
    accumulator.add_config(
        ConfigFact(key="cfg:package.json#type", value="module", file="package.json")
    )
    accumulator.add_config(
        ConfigFact(key="cfg:package.json#type", value="module", file="package.json")
    )

    assert [entry.key for entry in _entries(accumulator, "config_entries")] == [
        "cfg:package.json#type"
    ]


def test_same_dependency_with_another_kind_or_scope_is_a_separate_entry() -> None:
    """A BOM import and a plain dependency on one artifact are two facts (spec6)."""
    accumulator = FactAccumulator()
    key = "maven:org.springframework.boot:spring-boot-dependencies"
    accumulator.add_dependency(
        DependencyFact(key=key, version="3.5.0", kind="bom", scope="import")
    )
    accumulator.add_dependency(
        DependencyFact(key=key, version="3.5.0", kind="dependency")
    )
    accumulator.add_dependency(
        DependencyFact(key=key, version="3.5.0", kind="dependency")
    )

    entries = _entries(accumulator, "dependency_entries")

    assert sorted((entry.kind, entry.scope) for entry in entries) == [
        ("bom", "import"),
        ("dependency", "dependencies"),
    ]


def test_same_config_key_in_two_modules_files_or_profiles_is_kept_per_occurrence() -> (
    None
):
    """FR-8a: one entry per occurrence, so "only in test" is distinguishable."""
    accumulator = FactAccumulator()
    key = "cfg:application.properties#spring.data.mongodb.uri"
    accumulator.add_config(
        ConfigFact(
            key="cfg:package.json#engines.node",
            value=">=18",
            file="package.json",
            module=".",
        )
    )
    accumulator.add_config(
        ConfigFact(
            key="cfg:package.json#engines.node",
            value=">=20",
            file="ui/package.json",
            module="ui",
        )
    )
    accumulator.add_config(
        ConfigFact(
            key=key,
            value="a",
            file="src/main/resources/application.yml",
            profile="default",
            kind="application",
            line=3,
        )
    )
    accumulator.add_config(
        ConfigFact(
            key=key,
            value="b",
            file="src/main/resources/application.yml",
            profile="prod",
            kind="application",
            line=12,
        )
    )
    accumulator.add_config(
        ConfigFact(
            key=key,
            value="c",
            file="src/test/resources/application.yml",
            profile="default",
            kind="application",
            line=1,
            test=True,
        )
    )

    entries = _entries(accumulator, "config_entries")

    assert len(entries) == 5
    spring = [entry for entry in entries if entry.key == key]
    assert [(entry.profile, entry.test) for entry in spring] == [
        ("default", False),
        ("prod", False),
        ("default", True),
    ]


def test_diagnostics_are_deduplicated_and_sorted() -> None:
    accumulator = FactAccumulator()
    accumulator.add_diagnostic(Diagnostic(kind="generated_js", file="b.js"))
    accumulator.add_diagnostic(Diagnostic(kind="generated_js", file="b.js"))
    accumulator.add_diagnostic(
        Diagnostic(kind="file_too_large", file="a.ts", detail="x")
    )

    entries = _entries(accumulator, "diagnostic_entries")

    assert [(entry.file, entry.kind) for entry in entries] == [
        ("a.ts", "file_too_large"),
        ("b.js", "generated_js"),
    ]


def test_frameworks_are_recorded_per_module() -> None:
    accumulator = FactAccumulator()
    accumulator.add_framework(".", FrameworkFact(name="angular", version="19.2.0"))
    accumulator.add_framework(
        "backend", FrameworkFact(name="spring-boot", version="3.5.0")
    )

    assert sorted(accumulator.frameworks) == [".", "backend"]


# --- inputs hash -----------------------------------------------------------


def test_inputs_hash_is_order_independent_and_content_sensitive() -> None:
    first = inputs_hash([("a.ts", b"one"), ("b.ts", b"two")])
    reordered = inputs_hash([("b.ts", b"two"), ("a.ts", b"one")])
    changed = inputs_hash([("a.ts", b"ONE"), ("b.ts", b"two")])

    assert first == reordered
    assert first != changed
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64


def test_inputs_hash_changes_with_the_scanner_version() -> None:
    assert inputs_hash([("a.ts", b"one")], "026.1") != inputs_hash(
        [("a.ts", b"one")], "026.2"
    )


def test_inputs_hash_changes_with_the_scan_options() -> None:
    """Other ``--max-locations`` / ``--include-tests`` must never look ``unchanged`` (spec9)."""
    entries = [("a.ts", b"one")]
    base = inputs_hash(entries, options={"include_tests": True, "max_locations": 20})

    assert base == inputs_hash(
        entries, options={"max_locations": 20, "include_tests": True}
    )
    assert base != inputs_hash(
        entries, options={"include_tests": True, "max_locations": 5}
    )
    assert base != inputs_hash(
        entries, options={"include_tests": False, "max_locations": 20}
    )


# --- writer ----------------------------------------------------------------


def test_writer_is_atomic_and_creates_the_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / ".migration" / "profile.json"
    profile = Profile(generated=Generated(at=FIXED_TIME))

    written = write_profile(profile, target)

    assert written == target
    assert read_profile(target)["schema"] == SCHEMA_VERSION
    assert list(target.parent.glob("*.tmp")) == []


def test_writer_never_leaves_a_partial_file(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "profile.json"
    write(tmp_path, "profile.json", "previous")
    profile = Profile(generated=Generated(at=FIXED_TIME))

    import migration_planner.scanner.profile as profile_module

    def boom(*args, **kwargs):
        raise RuntimeError("crashed mid-write")

    monkeypatch.setattr(profile_module.os, "replace", boom)
    with pytest.raises(RuntimeError):
        write_profile(profile, target)

    # The old profile is intact and no temp file is left behind.
    assert target.read_text() == "previous"
    assert list(tmp_path.glob("*.tmp")) == []


def test_default_profile_path() -> None:
    assert default_profile_path("/repo") == Path("/repo/.migration/profile.json")


# --- determinism (AC-9a) ---------------------------------------------------


def _scan_twice(repo: Path) -> tuple[str, str]:
    first = scan(repo, out=repo / "p1.json").profile.to_json()
    second = scan(repo, out=repo / "p2.json").profile.to_json()
    return first, second


def test_two_scans_differ_only_in_generated_at(polyglot_repo) -> None:
    first, second = _scan_twice(polyglot_repo)

    first_payload = json.loads(first)
    second_payload = json.loads(second)
    first_generated = first_payload.pop("generated")
    second_generated = second_payload.pop("generated")
    for generated in (first_generated, second_generated):
        assert generated["at"]
        generated.pop("at")
        generated.pop("duration_ms")
    assert first_generated == second_generated
    assert first_payload == second_payload


def test_two_scans_write_byte_identical_files_apart_from_the_timestamp(
    polyglot_repo,
) -> None:
    scan(polyglot_repo, out=polyglot_repo / "p1.json")
    scan(polyglot_repo, out=polyglot_repo / "p2.json")

    first = (polyglot_repo / "p1.json").read_text().splitlines()
    second = (polyglot_repo / "p2.json").read_text().splitlines()

    differing = [
        (left, right)
        for left, right in zip(first, second, strict=True)
        if left != right
    ]
    assert len(first) == len(second)
    # AC-9a: "at" and the measured duration are the only time-dependent fields.
    assert all('"at"' in left or "duration_ms" in left for left, _ in differing)


def test_inputs_hash_changes_when_one_byte_changes(polyglot_repo) -> None:
    before = scan(polyglot_repo, out=polyglot_repo / "p1.json").profile.inputs_hash
    write(polyglot_repo, "src/app/app.component.ts", "// changed\n")

    after = scan(polyglot_repo, out=polyglot_repo / "p2.json").profile.inputs_hash

    assert before != after


def test_inputs_hash_is_stable_without_changes(polyglot_repo) -> None:
    first = scan(polyglot_repo, out=polyglot_repo / "p1.json").profile.inputs_hash
    second = scan(polyglot_repo, out=polyglot_repo / "p2.json").profile.inputs_hash

    assert first == second


def test_generated_block_records_the_scan(polyglot_repo) -> None:
    result = scan(polyglot_repo, out=polyglot_repo / "p.json")
    generated = json.loads(result.profile.to_json())["generated"]

    assert generated["scanner"] == SCANNER_VERSION
    assert generated["root"] == "."
    assert generated["files_scanned"] == len(result.discovery.files)
    assert generated["files_skipped"] == 0
    assert generated["duration_ms"] >= 0
    assert generated["at"].endswith("Z")


def test_profile_model_rejects_a_missing_generated_block() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({"schema": 1})


# --- summary ---------------------------------------------------------------


def test_summary_text_format() -> None:
    summary = Summary(
        files_scanned=4812,
        framework="angular",
        framework_version="19.2.0",
        dependencies=61,
        symbols=312,
        members=48,
        config=27,
        template_tokens=4,
        diagnostics=3,
        out=".migration/profile.json",
        duration_ms=2410,
    )

    assert summary.text() == (
        "scanned 4812 files · angular 19.2.0 · 61 deps · 312 symbols · 48 members · "
        "27 config · 4 template tokens · 3 diagnostics → .migration/profile.json (2.4 s)"
    )


def test_summary_text_without_a_framework() -> None:
    summary = Summary(files_scanned=3, out=".migration/profile.json", duration_ms=20)

    assert "no framework" in summary.text()
    assert summary.text().startswith("scanned 3 files · no framework · 0 deps")


def test_fact_accumulator_merges_across_files_and_modules() -> None:
    accumulator = FactAccumulator(max_locations=2)
    accumulator.add_file(
        FileFacts(
            symbols=[
                _usage("npm:p#A", file="src/a.ts", line=1),
                _usage("npm:p#A", file="src/a.ts", line=2),
            ]
        )
    )
    accumulator.add_file(
        FileFacts(symbols=[_usage("npm:p#A", file="src/b.ts", line=1)])
    )

    entry = accumulator.symbol_entries()[0]

    assert entry.count == 3
    assert entry.files == 2
    assert len(entry.locations) == 2
    assert entry.truncated is True
