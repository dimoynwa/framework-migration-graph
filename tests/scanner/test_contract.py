"""The extractor contract (spec 026 FR-1, "Extractor contract") and the scan loop.

Spec1 ships no readers or extractors: every fact section stays empty until
spec2–spec8 register one. These tests prove the seam works, so each later spec
only adds a module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from migration_planner.scanner import contract
from migration_planner.scanner.contract import (
    SCANNER_VERSION,
    ConfigFact,
    DependencyFact,
    Diagnostic,
    FileFacts,
    FrameworkFact,
    ManifestFacts,
    Usage,
)
from migration_planner.scanner.scan import NoSupportedManifest, scan

from .conftest import read_profile, write


@pytest.fixture(autouse=True)
def clean_registry():
    """Every test starts with no readers, so a registration cannot leak across."""
    contract.reset_registry()
    yield
    contract.reset_registry()


def test_no_reader_or_extractor_is_registered_by_default() -> None:
    assert contract.manifest_readers() == {}
    assert contract.source_extractors() == {}
    assert contract.post_passes() == ()


def test_spec1_writes_every_fact_section_empty(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": '{"name": "demo"}',
            "src/app.ts": "import { Component } from '@angular/core';\n",
            "src/app.html": "<div>{{ x }}</div>\n",
            "backend/pom.xml": "<project/>",
        }
    )

    result = scan(repo, out=repo / "profile.json")
    payload = read_profile(repo / "profile.json")

    assert result.profile.dependencies == []
    assert result.profile.symbols == []
    assert result.profile.members == []
    assert result.profile.side_effect_imports == []
    assert result.profile.wildcard_imports == []
    assert result.profile.config == []
    assert result.profile.templates == []
    assert payload["framework"] is None
    # Modules and diagnostics are spec1's own sections.
    assert [module["path"] for module in payload["modules"]] == [".", "backend"]


def test_a_manifest_reader_fills_its_sections(make_repo) -> None:
    repo = make_repo({"package.json": '{"name": "demo"}'})

    def read_package_json(context):
        return ManifestFacts(
            dependencies=[
                DependencyFact(
                    key="npm:@angular/core",
                    name="@angular/core",
                    range="^19.2.0",
                    version="19.2.4",
                    scope="dependencies",
                    module=context.module,
                )
            ],
            config=[
                ConfigFact(
                    key="cfg:package.json#type", value="module", file="package.json"
                )
            ],
            frameworks=[
                FrameworkFact(
                    name="angular",
                    version="19.2.4",
                    raw="^19.2.0",
                    source="package-lock.json",
                )
            ],
        )

    contract.register_manifest_reader("package.json", read_package_json)
    result = scan(repo, out=repo / "profile.json")
    payload = read_profile(repo / "profile.json")

    assert [entry["key"] for entry in payload["dependencies"]] == ["npm:@angular/core"]
    assert payload["dependencies"][0]["version"] == "19.2.4"
    assert payload["config"][0]["key"] == "cfg:package.json#type"
    assert payload["framework"] == {
        "name": "angular",
        "version": "19.2.4",
        "raw": "^19.2.0",
        "source": "package-lock.json",
    }
    assert payload["modules"][0]["frameworks"][0]["name"] == "angular"
    assert result.summary.framework == "angular"
    assert result.summary.framework_version == "19.2.4"


def test_a_reader_gets_only_its_own_modules_manifests(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}",
            "ui/package.json": "{}",
            "backend/pom.xml": "<project/>",
        }
    )
    seen: list[tuple[str, list[str]]] = []

    def read_package_json(context):
        seen.append((context.module, [manifest.name for manifest in context.files]))
        return ManifestFacts()

    contract.register_manifest_reader("package.json", read_package_json)
    scan(repo, out=repo / "profile.json")

    assert sorted(seen) == [(".", ["package.json"]), ("ui", ["package.json"])]


def test_a_reader_handling_two_kinds_runs_once(make_repo) -> None:
    repo = make_repo(
        {"gradle.properties": "a=1\n", "gradle/libs.versions.toml": "[versions]\n"}
    )
    calls: list[str] = []

    def read_gradle(context):
        calls.append(context.module)
        return ManifestFacts()

    contract.register_manifest_reader("gradle.properties", read_gradle)
    contract.register_manifest_reader("libs.versions.toml", read_gradle)
    scan(repo, out=repo / "profile.json")

    assert calls == ["."]


def test_a_source_extractor_fills_symbols_and_members(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}",
            "src/app.ts": "import { inject } from '@angular/core';\n",
            "src/app.spec.ts": "import { TestBed } from '@angular/core/testing';\n",
        }
    )

    def extract_ts(context):
        if context.test:
            return FileFacts(
                members=[
                    Usage(
                        key="npm:@angular/core/testing#TestBed.get",
                        file=context.relative,
                        line=3,
                        test=True,
                    )
                ]
            )
        return FileFacts(
            symbols=[
                Usage(key="npm:@angular/core#inject", file=context.relative, line=1)
            ]
        )

    contract.register_source_extractor("ts", extract_ts)
    result = scan(repo, out=repo / "profile.json")
    payload = read_profile(repo / "profile.json")

    assert [entry["key"] for entry in payload["symbols"]] == [
        "npm:@angular/core#inject"
    ]
    assert payload["symbols"][0]["count"] == 1
    assert payload["symbols"][0]["locations"] == [
        {"file": "src/app.ts", "line": 1, "test": False}
    ]
    assert [entry["key"] for entry in payload["members"]] == [
        "npm:@angular/core/testing#TestBed.get"
    ]
    assert payload["members"][0]["locations"][0]["test"] is True
    assert result.summary.symbols == 1
    assert result.summary.members == 1


def test_an_extractor_receives_the_module_and_the_bytes(make_repo) -> None:
    repo = make_repo(
        {"package.json": "{}", "ui/package.json": "{}", "ui/src/a.ts": "const a=1;"}
    )
    seen: list[tuple[str, str, str, bool, bytes]] = []

    def extract(context):
        seen.append(
            (
                context.relative,
                context.module,
                context.language,
                context.test,
                context.data,
            )
        )
        return FileFacts()

    contract.register_source_extractor("ts", extract)
    scan(repo, out=repo / "profile.json")

    assert seen == [("ui/src/a.ts", "ui", "ts", False, b"const a=1;")]


def test_an_extractor_is_not_called_for_a_language_it_did_not_register(
    make_repo,
) -> None:
    repo = make_repo(
        {"package.json": "{}", "src/a.ts": "const a=1;", "src/b.java": "class B {}"}
    )
    calls: list[str] = []

    def extract_ts(context):
        calls.append(context.language)
        return FileFacts()

    contract.register_source_extractor("ts", extract_ts)
    scan(repo, out=repo / "profile.json")

    assert calls == ["ts"]


def test_extractor_diagnostics_reach_the_profile(make_repo) -> None:
    repo = make_repo({"package.json": "{}", "src/broken.ts": "import {"})

    def extract(context):
        return FileFacts(
            diagnostics=[
                Diagnostic(kind="parse_error", file=context.relative, detail="syntax")
            ]
        )

    contract.register_source_extractor("ts", extract)
    result = scan(repo, out=repo / "profile.json")

    assert [
        (entry.kind, entry.file, entry.detail) for entry in result.profile.diagnostics
    ] == [("parse_error", "src/broken.ts", "syntax")]


def test_a_failing_extractor_does_not_sink_the_scan(make_repo) -> None:
    """A crash in one extractor must surface as a diagnostic, not as exit code 2."""
    repo = make_repo({"package.json": "{}", "src/a.ts": "const a=1;"})

    def exploding(context):
        raise ValueError("boom")

    contract.register_source_extractor("ts", exploding)

    # The contract is best effort: the scan completes and reports the failure.
    result = scan(repo, out=repo / "profile.json")

    assert (repo / "profile.json").is_file()
    assert result.profile.diagnostics


def test_post_passes_run_after_collection(make_repo) -> None:
    repo = make_repo({"package.json": "{}", "src/a.ts": "const a=1;"})
    order: list[str] = []

    def extract(context):
        order.append("extract")
        return FileFacts(symbols=[Usage(key="npm:?#X", file=context.relative, line=1)])

    def post_pass(_accumulator):
        order.append("post")

    contract.register_source_extractor("ts", extract)
    contract.register_post_pass(post_pass)
    scan(repo, out=repo / "profile.json")

    assert order == ["extract", "post"]


def test_scan_raises_for_a_tree_with_no_manifest(tmp_path: Path) -> None:
    write(tmp_path, "src/a.ts", "const a=1;")

    with pytest.raises(NoSupportedManifest):
        scan(tmp_path)


def test_scanner_version_is_recorded_in_the_profile(make_repo) -> None:
    repo = make_repo({"package.json": "{}"})

    payload = read_profile(scan(repo, out=repo / "p.json").path)

    assert payload["generated"]["scanner"] == SCANNER_VERSION
    assert SCANNER_VERSION == "026.1"


def test_manifest_context_helpers(make_repo) -> None:
    repo = make_repo(
        {"package.json": "{}", "tsconfig.json": "{}", "pom.xml": "<project/>"}
    )
    contexts = {}

    def reader(context):
        contexts[context.module] = context
        return ManifestFacts()

    contract.register_manifest_reader("package.json", reader)
    contract.register_manifest_reader("tsconfig.json", reader)
    contract.register_manifest_reader("pom.xml", reader)
    scan(repo, out=repo / "p.json")

    context = contexts["."]
    assert [manifest.name for manifest in context.files] == [
        "package.json",
        "pom.xml",
        "tsconfig.json",
    ]
    assert context.named("package.json") is not None
    assert context.named("missing.json") is None
    assert [manifest.kind for manifest in context.by_kind("tsconfig.json")] == [
        "tsconfig.json"
    ]
    assert context.by_kind("tsconfig.json", "pom.xml") != ()
    assert context.files[0].read_text() == "{}"
