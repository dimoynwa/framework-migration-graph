"""CLI wiring: triage runs on extract-only and can be skipped."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

import migration_oracle.pipeline.triage.run as triage_run
from migration_oracle.cli import export_extract_populate_framework
from migration_oracle.pipeline.triage.client import FakeTriageClient
from migration_oracle.pipeline.triage.markdown import TRIAGE_TABLE_HEADER, parse_raw_markdown

DROP_ANSWERS = {
    "requires_action": {"type": "noul", "noul": 0.05},
    "category": {
        "type": "choice",
        "choice": "noise",
        "probabilities": {"noise": 0.95},
        "confidence": 0.4,
    },
    "impact": {"type": "score", "score": 0.2, "confidence": 0.4},
}


def test_extract_only_triage_and_reuse_and_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    fake = FakeTriageClient(DROP_ANSWERS)
    monkeypatch.setattr(triage_run, "default_client", lambda _settings: fake)
    raw = tmp_path / "raw.md"
    env = {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_PASSWORD": "test",
        "TRIAGE_BASE_URL": "http://triage.example",
        "TRIAGE_MODEL": "nimble",
        "ARTIFACT_CACHE_DIR": str(tmp_path / "artifacts"),
    }
    first = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "stub_framework",
            "1.0.0",
            "2.0.0",
            "--extract-only",
            "--output-md",
            str(raw),
        ],
        env=env,
    )
    assert first.exit_code == 0, first.output
    assert TRIAGE_TABLE_HEADER in raw.read_text(encoding="utf-8")
    parsed = parse_raw_markdown(raw.read_text(encoding="utf-8"))
    # The confirmed breaking row is a rule keep. The behavioral row is classified.
    assert len(fake.calls) == 1
    decisions = {row.statement: row.triage_decision for row in parsed.rows}
    assert any(decision == "keep" for decision in decisions.values())
    assert any(decision == "drop" for decision in decisions.values())

    second = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "stub_framework",
            "1.0.0",
            "2.0.0",
            "--extract-only",
            "--output-md",
            str(raw),
        ],
        env=env,
    )
    assert second.exit_code == 0, second.output
    assert len(fake.calls) == 1

    skipped = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "stub_framework",
            "1.0.0",
            "2.0.0",
            "--extract-only",
            "--force-extract",
            "--skip-triage",
            "--output-md",
            str(tmp_path / "plain.md"),
        ],
        env=env,
    )
    assert skipped.exit_code == 0, skipped.output
    plain = (tmp_path / "plain.md").read_text(encoding="utf-8")
    assert TRIAGE_TABLE_HEADER not in plain
    assert "| Type | Confidence | Source | Statement |" in plain
    assert len(fake.calls) == 1
