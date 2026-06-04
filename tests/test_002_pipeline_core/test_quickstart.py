"""Quickstart CLI integration test with mocked LLM."""

from pathlib import Path

import migration_oracle.cli as cli_module
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
from migration_oracle.pipeline.extractor import ExtractionResult
from migration_oracle.pipeline.filters import FilterResult


def _sample_batch() -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            MigrationEntity(
                source_section="breaking_change",
                title="Sample change",
                change_type="breaking_change",
                reason="Reason text.",
                scopes=[
                    BreakingScopeInput(scope=ScopeLevel.RUNTIME, severity=Severity.MEDIUM)
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
                        summary="Verify startup",
                        instruction="Start the app.",
                        effort=Effort.MODERATE,
                        automatable=False,
                        requires=[],
                        verification="App starts.",
                    )
                ],
            )
        ]
    )


def test_quickstart_dry_run_creates_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    raw = tmp_path / "raw.md"
    filtered = tmp_path / "filtered.md"
    json_path = tmp_path / "entities.json"

    monkeypatch.chdir(tmp_path)
    def _mock_filter(raw_md: str, output_path: Path, flags) -> FilterResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("## 🔴 Breaking Changes\n", encoding="utf-8")
        return FilterResult(
            filtered_md="## 🔴 Breaking Changes\n", artifact_path=output_path
        )

    def _mock_extract(filtered_md: str, framework_display: str, output_path: Path, flags) -> ExtractionResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        batch = _sample_batch()
        output_path.write_text(batch.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return ExtractionResult(batch=batch, artifact_path=output_path)

    monkeypatch.setattr(cli_module, "run_filter", _mock_filter)
    monkeypatch.setattr(cli_module, "run_extraction", _mock_extract)

    runner = CliRunner()
    result = runner.invoke(
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
    assert raw.exists()
    assert filtered.exists()
    assert json_path.exists()
    assert "Dry run complete" in result.output
