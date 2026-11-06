"""Cached filtered Markdown is invalidated when the kept rows change."""

from __future__ import annotations

from pathlib import Path

import pytest

import migration_oracle.pipeline.filters as filters
from migration_oracle.pipeline._cache import CacheFlags
from migration_oracle.pipeline.filters import (
    filter_input_digest_path,
    refresh_flags_for_filter_input,
    run_filter,
)
from migration_oracle.pipeline.triage.markdown import FILTER_TABLE_HEADER

CACHED = CacheFlags(
    skip_extraction=True,
    skip_filter_llm=True,
    skip_entity_llm=True,
    raw_was_cached=True,
    stale_filtered_warning=False,
    stale_json_warning=False,
)

TRIAGED_A = f"{FILTER_TABLE_HEADER}\n| behavioral | inferred | u1 | A | behavior_change | 1.00 |\n"
TRIAGED_B = f"{FILTER_TABLE_HEADER}\n| behavioral | inferred | u2 | B | breaking | 2.00 |\n"
UNTRIAGED = "| Type | Confidence | Source | Statement |\n| behavioral | inferred | u1 | A |\n"


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def fake_invoke(table: str) -> str:
        seen.append(table)
        return f"## filtered\n{len(seen)}"

    monkeypatch.setattr(filters, "_invoke_filter", fake_invoke)
    return seen


def test_same_input_reuses_cache(tmp_path: Path, calls: list[str]) -> None:
    out = tmp_path / "x-changes_filtered.md"
    fresh = refresh_flags_for_filter_input(CACHED, TRIAGED_A, out)
    assert fresh is CACHED  # nothing cached yet
    run_filter(TRIAGED_A, output_path=out, flags=CacheFlags(**{**CACHED.__dict__, "skip_filter_llm": False}))
    assert filter_input_digest_path(out).exists()
    assert refresh_flags_for_filter_input(CACHED, TRIAGED_A, out) is CACHED
    assert len(calls) == 1


def test_changed_kept_rows_rerun_both_llm_steps(tmp_path: Path, calls: list[str]) -> None:
    out = tmp_path / "x-changes_filtered.md"
    run_filter(TRIAGED_A, output_path=out, flags=CacheFlags(**{**CACHED.__dict__, "skip_filter_llm": False}))
    flags = refresh_flags_for_filter_input(CACHED, TRIAGED_B, out)
    assert not flags.skip_filter_llm and not flags.skip_entity_llm
    result = run_filter(TRIAGED_B, output_path=out, flags=flags)
    assert len(calls) == 2 and calls[-1] == TRIAGED_B
    assert result.filtered_md.endswith("2")
    assert refresh_flags_for_filter_input(CACHED, TRIAGED_B, out) is CACHED


def test_legacy_artifact_without_sidecar(tmp_path: Path, calls: list[str]) -> None:
    out = tmp_path / "x-changes_filtered.md"
    out.write_text("## legacy\n", encoding="utf-8")
    # Untriaged input: legacy artifact is trusted and adopted.
    assert refresh_flags_for_filter_input(CACHED, UNTRIAGED, out) is CACHED
    # Triaged input: legacy artifact was built from all rows, so it is stale.
    out_b = tmp_path / "y-changes_filtered.md"
    out_b.write_text("## legacy\n", encoding="utf-8")
    flags = refresh_flags_for_filter_input(CACHED, TRIAGED_A, out_b)
    assert not flags.skip_filter_llm and not flags.skip_entity_llm
    assert calls == []
