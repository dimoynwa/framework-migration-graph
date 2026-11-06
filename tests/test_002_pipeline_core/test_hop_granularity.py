"""Configurable version-hop granularity for the ingestion pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from click.testing import CliRunner

import migration_oracle.cli as cli_module
from migration_oracle.cli import export_extract_populate_framework
from migration_oracle.models.entities import (
    DocumentedChange,
    ExtractionResult,
    MigrationEntitiesBatch,
)
from migration_oracle.pipeline.extractor import ExtractionResult as LLMExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor, HopContext
from migration_oracle.pipeline.extractors.parsing import (
    enters_new_minor_line,
    select_hop_versions,
    validate_hop_granularity,
)
from migration_oracle.pipeline.filters import FilterResult

VERSIONS = ["3.1.0", "3.1.1", "3.1.2", "3.1.12", "3.2.0", "3.2.1", "3.2.4", "3.3.0"]

MINIMAL_BATCH = MigrationEntitiesBatch.model_validate(
    {
        "entities": [
            {
                "source_section": "breaking_change",
                "title": "Patch entity",
                "change_type": "breaking_change",
                "reason": "Patch release removed an API.",
                "scopes": [{"scope": "runtime", "severity": "low"}],
                "entities": [
                    {"kind": "class", "name": "com.example.Foo", "role": "mentioned"}
                ],
                "steps": [
                    {
                        "index": 0,
                        "step_type": "verify",
                        "summary": "Verify",
                        "instruction": "Compile.",
                        "effort": "moderate",
                        "automatable": False,
                        "requires": [],
                        "verification": "Build succeeds.",
                    }
                ],
            }
        ]
    }
)


def test_patch_granularity_keeps_every_release() -> None:
    assert select_hop_versions(VERSIONS, "3.1.0", "3.1.12", "patch") == [
        "3.1.0",
        "3.1.1",
        "3.1.2",
        "3.1.12",
    ]


def test_minor_granularity_keeps_line_starts_and_endpoints() -> None:
    assert select_hop_versions(VERSIONS, "3.1.12", "3.2.4", "minor") == [
        "3.1.12",
        "3.2.0",
        "3.2.4",
    ]
    assert select_hop_versions(VERSIONS, "3.1.0", "3.3.0", "minor") == [
        "3.1.0",
        "3.2.0",
        "3.3.0",
    ]


def test_select_hop_versions_defaults_to_patch() -> None:
    """The library default stays patch; the CLI default (HOP_GRANULARITY) is minor."""
    assert validate_hop_granularity("PATCH") == "patch"
    assert select_hop_versions(VERSIONS, "3.2.0", "3.2.4") == ["3.2.0", "3.2.1", "3.2.4"]


def test_cli_default_granularity_is_minor(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    from migration_oracle import config

    monkeypatch.delenv("HOP_GRANULARITY", raising=False)
    try:
        assert importlib.reload(config).HOP_GRANULARITY == "minor"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_unknown_granularity_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown hop granularity"):
        select_hop_versions(VERSIONS, "3.1.0", "3.2.0", "milestone")


def test_enters_new_minor_line_boundaries() -> None:
    assert enters_new_minor_line("3.1.12", "3.2.0")
    assert enters_new_minor_line("3.9.1", "4.0.0")
    assert not enters_new_minor_line("3.2.0", "3.2.1")
    assert not enters_new_minor_line("3.2.4", "3.2.9")


class _RecordingExtractor(BaseExtractor):
    """In-memory extractor that records how each hop was planned and called."""

    framework_key = "recording"
    display_name = "Recording Framework"

    def __init__(self, versions: list[str], failing: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._versions = versions
        self._failing = failing
        self.calls: list[tuple[str, str, HopContext | None]] = []
        self.metadata_calls: list[tuple[str, str]] = []

    async def discover_versions(self) -> list[str]:
        return list(self._versions)

    async def extract(
        self, from_version: str, to_version: str, *, hop_context: HopContext | None = None
    ) -> ExtractionResult:
        self.calls.append((from_version, to_version, hop_context))
        if to_version in self._failing:
            raise RuntimeError(f"no release page for {to_version}")
        return ExtractionResult(
            changes=[
                DocumentedChange(
                    type="breaking",
                    confidence="confirmed",
                    source_url=f"https://example.com/{to_version}",
                    statement=f"Breaking change released in {to_version}.",
                )
            ],
            metadata={"hop": f"{from_version}->{to_version}"},
        )

    async def build_range_metadata(self, from_version: str, to_version: str) -> dict:
        self.metadata_calls.append((from_version, to_version))
        return {"bom_diff": {f"{from_version}->{to_version}": "changed"}}


def _run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def extractor() -> _RecordingExtractor:
    ex = _RecordingExtractor(VERSIONS, failing=("3.1.2",))
    yield ex
    _run(ex.aclose())


def test_plan_hops_patch_granularity_yields_one_hop_per_release(extractor) -> None:
    contexts = _run(extractor.plan_hops("3.1.0", "3.2.1", "patch"))
    assert [(c.from_version, c.to_version) for c in contexts] == [
        ("3.1.0", "3.1.1"),
        ("3.1.1", "3.1.2"),
        ("3.1.2", "3.1.12"),
        ("3.1.12", "3.2.0"),
        ("3.2.0", "3.2.1"),
    ]
    assert [c.enters_minor_line for c in contexts] == [False, False, False, True, False]


def test_plan_hops_minor_granularity_collapses_patch_releases(extractor) -> None:
    contexts = _run(extractor.plan_hops("3.1.12", "3.2.4", "minor"))
    assert [(c.from_version, c.to_version) for c in contexts] == [
        ("3.1.12", "3.2.0"),
        ("3.2.0", "3.2.4"),
    ]
    assert [c.enters_minor_line for c in contexts] == [True, False]


def test_extract_contexts_passes_hop_context_and_survives_failures(extractor) -> None:
    contexts = _run(extractor.plan_hops("3.1.1", "3.2.0", "patch"))
    hops = _run(extractor.extract_contexts(contexts, per_hop_range_metadata=True))

    assert [(h.from_version, h.to_version, len(h.changes)) for h in hops] == [
        ("3.1.1", "3.1.2", 0),  # failing hop keeps its place with no changes
        ("3.1.2", "3.1.12", 1),
        ("3.1.12", "3.2.0", 1),
    ]
    assert all(call[2] is not None for call in extractor.calls)
    # Per-hop metadata for extracted hops only — a failed hop has no BOM to diff.
    assert extractor.metadata_calls == [
        ("3.1.2", "3.1.12"),
        ("3.1.12", "3.2.0"),
    ]
    assert hops[1].result.metadata["bom_diff"] == {"3.1.2->3.1.12": "changed"}


def test_extract_range_still_aggregates_and_uses_range_metadata(extractor) -> None:
    result, hop_changes = _run(extractor.extract_range("3.1.1", "3.1.12", "patch"))
    assert [h[1] for h in hop_changes] == ["3.1.2", "3.1.12"]
    assert len(result.changes) == 1
    assert result.metadata["bom_diff"] == {"3.1.1->3.1.12": "changed"}


def _stub_llm_stages(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replace filter/entity/populate stages and record populate calls per hop."""
    populate_calls: list[dict] = []

    def _filter(raw_md: str, *, output_path: Path, flags, research=None) -> FilterResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("## 🔴 Breaking Changes\n", encoding="utf-8")
        return FilterResult(filtered_md="## 🔴 Breaking Changes\n", artifact_path=output_path)

    def _entity(filtered_md: str, *, framework_display: str, output_path: Path, flags, **_extra):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(MINIMAL_BATCH.model_dump_json(indent=2), encoding="utf-8")
        return LLMExtractionResult(batch=MINIMAL_BATCH, artifact_path=output_path)

    class _Result:
        def __init__(self) -> None:
            self.skipped = False
            self.rules_written = 1
            self.steps_written = 1
            self.entities_written = 1

    def _populate(**kwargs):
        populate_calls.append(kwargs)
        return _Result()

    monkeypatch.setattr("migration_oracle.pipeline.filters.get_llm", _boom)
    monkeypatch.setattr(cli_module, "run_filter", _filter)
    monkeypatch.setattr(cli_module, "run_extraction", _entity)
    monkeypatch.setattr(cli_module, "populate_graph", _populate)
    return populate_calls


def _boom() -> None:
    raise AssertionError("real LLM must not be called")


def test_cli_hop_by_hop_populates_one_version_per_hop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    extractor = _RecordingExtractor(VERSIONS)
    monkeypatch.setattr(cli_module, "get_extractor", lambda _framework: extractor)
    populate_calls = _stub_llm_stages(monkeypatch)

    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "spring-boot",
            "3.1.0",
            "3.2.1",
            "--hop-granularity",
            "patch",
            "--hop-by-hop",
        ],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "test"},
    )

    assert result.exit_code == 0, result.output
    assert [
        (call["from_version"], call["to_version"]) for call in populate_calls
    ] == [
        ("3.1.0", "3.1.1"),
        ("3.1.1", "3.1.2"),
        ("3.1.2", "3.1.12"),
        ("3.1.12", "3.2.0"),
        ("3.2.0", "3.2.1"),
    ]
    for hop_from, hop_to in (
        ("3.1.0", "3.1.1"),
        ("3.1.1", "3.1.2"),
        ("3.1.2", "3.1.12"),
        ("3.1.12", "3.2.0"),
        ("3.2.0", "3.2.1"),
    ):
        assert (tmp_path / f"runs/raw/spring-boot-{hop_from}-to-{hop_to}-changes.md").exists()
        assert (
            tmp_path / "runs/json" / f"spring-boot-{hop_from}-to-{hop_to}-entities.json"
        ).exists()
    assert not (tmp_path / "runs/raw/spring-boot-3.1.0-to-3.2.1-changes.md").exists()
    assert "5 patch-level hop(s)" in result.output


def test_cli_hop_by_hop_extract_only_writes_per_hop_raw_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_module, "get_extractor", lambda _framework: _RecordingExtractor(VERSIONS)
    )
    monkeypatch.setattr("migration_oracle.pipeline.filters.get_llm", _boom)
    monkeypatch.setattr("migration_oracle.pipeline.extractor.get_llm", _boom)

    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "spring-boot",
            "3.2.0",
            "3.2.4",
            "--hop-by-hop",
            "--extract-only",
            "--hop-granularity",
            "patch",
        ],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "test"},
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "runs/raw/spring-boot-3.2.0-to-3.2.1-changes.md").exists()
    assert (tmp_path / "runs/raw/spring-boot-3.2.1-to-3.2.4-changes.md").exists()
    assert not (tmp_path / "runs/raw/spring-boot-3.2.0-to-3.2.4-changes.md").exists()


def test_cli_hop_by_hop_rejects_explicit_output_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_module, "get_extractor", lambda _framework: _RecordingExtractor(VERSIONS)
    )

    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "spring-boot",
            "3.1.0",
            "3.1.1",
            "--hop-by-hop",
            "--output-md",
            str(tmp_path / "raw.md"),
        ],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "test"},
    )

    assert result.exit_code != 0
    assert "one artifact set per version hop" in result.output


def test_cli_range_mode_rejects_unknown_granularity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_module, "get_extractor", lambda _framework: _RecordingExtractor(VERSIONS)
    )

    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "spring-boot",
            "3.1.0",
            "3.2.0",
            "--hop-granularity",
            "milestone",
        ],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "test"},
    )

    assert result.exit_code != 0


PRERELEASE_VERSIONS = ["4.0.5", "4.0.6", "4.1.0-M1", "4.1.0-M3", "4.1.0-RC1", "4.1.0"]


def test_patch_granularity_keeps_milestone_hops() -> None:
    assert select_hop_versions(PRERELEASE_VERSIONS, "4.0.6", "4.1.0", "patch") == [
        "4.0.6",
        "4.1.0-M1",
        "4.1.0-M3",
        "4.1.0-RC1",
        "4.1.0",
    ]


def test_minor_granularity_skips_milestones_but_keeps_prerelease_endpoint() -> None:
    assert select_hop_versions(PRERELEASE_VERSIONS, "4.0.6", "4.1.0", "minor") == [
        "4.0.6",
        "4.1.0",
    ]
    assert select_hop_versions(PRERELEASE_VERSIONS, "4.0.6", "4.1.0-RC1", "minor") == [
        "4.0.6",
        "4.1.0-RC1",
    ]


def test_cli_hop_by_hop_populates_milestone_hops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4.1.0-RC1 is a real release: it gets artifacts, a Version node, and rules."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "get_extractor",
        lambda _framework: _RecordingExtractor(PRERELEASE_VERSIONS),
    )
    populate_calls = _stub_llm_stages(monkeypatch)

    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "spring-boot",
            "4.0.6",
            "4.1.0-RC1",
            "--hop-by-hop",
            "--hop-granularity",
            "patch",
        ],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "test"},
    )

    assert result.exit_code == 0, result.output
    assert [
        (call["from_version"], call["to_version"]) for call in populate_calls
    ] == [
        ("4.0.6", "4.1.0-M1"),
        ("4.1.0-M1", "4.1.0-M3"),
        ("4.1.0-M3", "4.1.0-RC1"),
    ]
    assert "milestone build" in result.output
    assert (tmp_path / "runs/json/spring-boot-4.1.0-M3-to-4.1.0-RC1-entities.json").exists()
