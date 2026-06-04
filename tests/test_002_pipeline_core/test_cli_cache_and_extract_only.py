"""CLI extract-only flag and LLM artifact cache skip behaviour."""

from __future__ import annotations

from pathlib import Path

import migration_oracle.cli as cli_module
import pytest
from click.testing import CliRunner
from migration_oracle.cli import export_extract_populate_framework
from migration_oracle.models.entities import (
    AffectedEntity,
    BreakingScopeInput,
    Effort,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
    MigrationEntity,
    MigrationStep,
    ScopeLevel,
    Severity,
    StepType,
)
from migration_oracle.pipeline._cache import resolve_cache_flags


def _minimal_entities_json() -> str:
    batch = MigrationEntitiesBatch(
        entities=[
            MigrationEntity(
                source_section="breaking_change",
                title="Cached entity",
                change_type="breaking_change",
                reason="Cached.",
                scopes=[
                    BreakingScopeInput(
                        scope=ScopeLevel.RUNTIME, severity=Severity.LOW
                    )
                ],
                entities=[
                    AffectedEntity(
                        kind=EntityKind.CLASS,
                        name="com.example.Foo",
                        role=EntityRole.MENTIONED,
                    )
                ],
                steps=[
                    MigrationStep(
                        index=0,
                        step_type=StepType.VERIFY,
                        summary="Verify",
                        instruction="Check.",
                        effort=Effort.MODERATE,
                        automatable=False,
                        requires=[],
                        verification="OK",
                    )
                ],
            )
        ]
    )
    return batch.model_dump_json(indent=2) + "\n"


def test_cache_flags_skip_filter_when_nodes_artifact_exists(tmp_path: Path) -> None:
    """Filtered MD in runs/nodes/ + cached raw → skip filter LLM, run entity LLM."""
    raw = tmp_path / "raw.md"
    filtered = tmp_path / "nodes/filtered.md"
    json_path = tmp_path / "entities.json"
    raw.write_text("raw", encoding="utf-8")
    filtered.parent.mkdir(parents=True, exist_ok=True)
    filtered.write_text("filtered", encoding="utf-8")

    flags = resolve_cache_flags(
        raw_path=raw,
        filtered_path=filtered,
        json_path=json_path,
        force=False,
        force_extract=False,
        force_llm=False,
    )
    assert flags.skip_extraction
    assert flags.skip_filter_llm
    assert not flags.skip_entity_llm


def test_cache_flags_skip_both_llm_when_json_exists(tmp_path: Path) -> None:
    """Entities JSON in runs/json/ → skip filter and entity LLM."""
    raw = tmp_path / "raw.md"
    filtered = tmp_path / "nodes/filtered.md"
    json_path = tmp_path / "entities.json"
    raw.write_text("raw", encoding="utf-8")
    filtered.parent.mkdir(parents=True, exist_ok=True)
    filtered.write_text("filtered", encoding="utf-8")
    json_path.write_text("{}", encoding="utf-8")

    flags = resolve_cache_flags(
        raw_path=raw,
        filtered_path=filtered,
        json_path=json_path,
        force=False,
        force_extract=False,
        force_llm=False,
    )
    assert flags.skip_extraction
    assert flags.skip_filter_llm
    assert flags.skip_entity_llm


def test_extract_only_skips_filter_and_entity_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw.md"
    monkeypatch.chdir(tmp_path)

    llm_called = False

    def _track_llm() -> None:
        nonlocal llm_called
        llm_called = True
        raise AssertionError("LLM must not run in --extract-only mode")

    monkeypatch.setattr("migration_oracle.pipeline.filters.get_llm", _track_llm)
    monkeypatch.setattr("migration_oracle.pipeline.extractor.get_llm", _track_llm)

    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "stub_framework",
            "1.0.0",
            "2.0.0",
            "--extract-only",
            "--dry-run",
            "--output-md",
            str(raw),
        ],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "test"},
    )

    assert result.exit_code == 0, result.output
    assert raw.exists()
    assert "Extract-only complete" in result.output
    assert not llm_called


def test_cli_skips_filter_llm_when_nodes_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "runs/raw/stub_framework-1.0.0-to-2.0.0-changes.md"
    filtered = tmp_path / "runs/nodes/stub_framework-1.0.0-to-2.0.0-changes_filtered.md"
    json_path = tmp_path / "runs/json/stub_framework-1.0.0-to-2.0.0-entities.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        "# Stub — documented changes\n\n| Type | Confidence | Source | Statement |\n",
        encoding="utf-8",
    )
    filtered.parent.mkdir(parents=True, exist_ok=True)
    filtered.write_text("## 🔴 Breaking Changes\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    filter_calls = 0

    def _filter_llm() -> None:
        nonlocal filter_calls
        filter_calls += 1
        raise AssertionError("filter LLM must be skipped")

    def _mock_entity_extraction(filtered_md, *, framework_display, output_path, flags):
        from migration_oracle.pipeline.extractor import ExtractionResult

        batch = MigrationEntitiesBatch.model_validate_json(_minimal_entities_json())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(_minimal_entities_json(), encoding="utf-8")
        return ExtractionResult(batch=batch, artifact_path=output_path)

    monkeypatch.setattr("migration_oracle.pipeline.filters.get_llm", _filter_llm)
    monkeypatch.setattr(cli_module, "run_extraction", _mock_entity_extraction)
    monkeypatch.setattr(
        cli_module,
        "populate_graph",
        lambda **kw: type("P", (), {"skipped": True})(),
    )

    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "stub_framework",
            "1.0.0",
            "2.0.0",
            "--dry-run",
            "--output-md",
            str(raw),
            "--output-filtered-md",
            str(filtered),
            "--output-json",
            str(json_path),
        ],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "test"},
    )

    assert result.exit_code == 0, result.output
    assert filter_calls == 0
    assert json_path.exists()


def test_cli_skips_both_llm_when_json_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "runs/raw/stub_framework-1.0.0-to-2.0.0-changes.md"
    filtered = tmp_path / "runs/nodes/stub_framework-1.0.0-to-2.0.0-changes_filtered.md"
    json_path = tmp_path / "runs/json/stub_framework-1.0.0-to-2.0.0-entities.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("# cached raw\n", encoding="utf-8")
    filtered.parent.mkdir(parents=True, exist_ok=True)
    filtered.write_text("## 🔴 Breaking Changes\n", encoding="utf-8")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(_minimal_entities_json(), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    filter_calls = 0
    entity_calls = 0

    def _filter_llm() -> None:
        nonlocal filter_calls
        filter_calls += 1
        raise AssertionError("filter LLM must be skipped")

    def _entity_llm() -> None:
        nonlocal entity_calls
        entity_calls += 1
        raise AssertionError("entity LLM must be skipped")

    monkeypatch.setattr("migration_oracle.pipeline.filters.get_llm", _filter_llm)
    monkeypatch.setattr("migration_oracle.pipeline.extractor.get_llm", _entity_llm)
    monkeypatch.setattr(
        cli_module,
        "populate_graph",
        lambda **kw: type("P", (), {"skipped": True})(),
    )

    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "stub_framework",
            "1.0.0",
            "2.0.0",
            "--dry-run",
            "--output-md",
            str(raw),
            "--output-filtered-md",
            str(filtered),
            "--output-json",
            str(json_path),
        ],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "test"},
    )

    assert result.exit_code == 0, result.output
    assert filter_calls == 0
    assert entity_calls == 0
