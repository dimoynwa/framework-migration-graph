"""Research reuses dossiers from an earlier runs/research JSONL before the row cache."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from migration_oracle.pipeline._paths import (
    default_research_jsonl_path,
    default_research_summary_path,
)
from migration_oracle.pipeline.research.markdown import parse_filtered_markdown
from migration_oracle.pipeline.research.run import run_research
from migration_oracle.pipeline.research.schema import PROMPT_VERSION, ResearchDossier

from tests.pipeline.test_research_agent import FILTERED, HOP, FakeFetcher, FakeSearch, _settings
from tests.pipeline.test_research_review_fixes import FlakyModel


def _run(rows, settings, model, *, force: bool = False):
    return run_research(
        rows,
        "Spring Boot",
        HOP,
        framework_key="spring-boot",
        settings=settings,
        model=model,  # type: ignore[arg-type]
        search=FakeSearch(),
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        force=force,
    )


def _write_jsonl(dossiers: list[ResearchDossier]) -> Path:
    path = default_research_jsonl_path("spring-boot", *HOP)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(d.model_dump_json() for d in dossiers) + "\n", encoding="utf-8")
    return path


def _dossier(row_key: str, settings, **update) -> ResearchDossier:
    values = {
        "row_key": row_key,
        "status": "ok",
        "text": "**What changed:** from the artifact.\n\n**Action:** none",
        "model": settings.model_id,
        "prompt_version": PROMPT_VERSION,
    }
    values.update(update)
    return ResearchDossier(**values)


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    settings = _settings(tmp_path)
    rows = parse_filtered_markdown(FILTERED)
    model = FlakyModel()  # unhealthy: any model call becomes an error dossier
    return settings, rows, model


def test_full_artifact_skips_the_model_and_the_cache(setup) -> None:
    settings, rows, model = setup
    _write_jsonl([_dossier(row.row_key, settings) for row in rows])

    dossiers = _run(rows, settings, model)

    assert model.calls == 0
    assert [d.row_key for d in dossiers] == [row.row_key for row in rows]
    assert all("from the artifact" in d.text for d in dossiers)
    assert not (settings.cache_dir / "research").exists()
    summary = json.loads(default_research_summary_path("spring-boot", *HOP).read_text())
    assert summary["artifact_hits"] == len(rows)
    assert summary["cache_hits"] == 0


def test_hand_edits_in_the_artifact_win_over_the_row_cache(setup) -> None:
    settings, rows, model = setup
    model.healthy = True
    _run(rows, settings, model)  # fills the row cache and writes the JSONL
    path = default_research_jsonl_path("spring-boot", *HOP)
    edited = [
        ResearchDossier.model_validate_json(line).model_copy(update={"text": "edited by hand"})
        for line in path.read_text().splitlines()
    ]
    _write_jsonl(edited)
    calls = model.calls

    dossiers = _run(rows, settings, model)

    assert model.calls == calls
    assert {d.text for d in dossiers} == {"edited by hand"}


@pytest.mark.parametrize(
    "update",
    [
        {"status": "error", "error": "timeout"},
        {"prompt_version": PROMPT_VERSION - 1},
        {"model": "some-other-model"},
    ],
)
def test_stale_or_failed_lines_are_researched_again(setup, update) -> None:
    settings, rows, model = setup
    model.healthy = True
    _write_jsonl([_dossier(row.row_key, settings, **update) for row in rows])

    dossiers = _run(rows, settings, model)

    assert model.calls > 0
    assert all("from the artifact" not in d.text for d in dossiers)


def test_rows_missing_from_the_artifact_fall_through(setup) -> None:
    settings, rows, model = setup
    model.healthy = True
    _write_jsonl([_dossier(rows[0].row_key, settings)])
    path = default_research_jsonl_path("spring-boot", *HOP)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")

    dossiers = _run(rows, settings, model)

    assert "from the artifact" in dossiers[0].text
    assert all("from the artifact" not in d.text for d in dossiers[1:])
    summary = json.loads(default_research_summary_path("spring-boot", *HOP).read_text())
    assert summary["artifact_hits"] == 1


def test_force_research_ignores_the_artifact(setup) -> None:
    settings, rows, model = setup
    model.healthy = True
    _write_jsonl([_dossier(row.row_key, settings) for row in rows])

    dossiers = _run(rows, settings, model, force=True)

    assert model.calls > 0
    assert all("from the artifact" not in d.text for d in dossiers)


def test_other_hop_artifact_is_not_used(setup) -> None:
    settings, rows, model = setup
    model.healthy = True
    path = _write_jsonl([_dossier(row.row_key, settings) for row in rows])
    other = default_research_jsonl_path("spring-boot", "3.5.1", "3.5.2")
    shutil.move(path, other)

    dossiers = _run(rows, settings, model)

    assert model.calls > 0
    assert all("from the artifact" not in d.text for d in dossiers)
