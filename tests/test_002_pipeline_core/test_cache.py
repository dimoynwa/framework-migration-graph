"""Tests for pipeline cache flag resolution."""

from pathlib import Path

from migration_oracle.pipeline._cache import resolve_cache_flags


def test_json_cache_skips_both_llm_calls(tmp_path: Path) -> None:
    raw = tmp_path / "raw.md"
    filtered = tmp_path / "filtered.md"
    json_path = tmp_path / "entities.json"
    raw.write_text("raw")
    filtered.write_text("filtered")
    json_path.write_text("{}")

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


def test_filtered_cache_skips_filter_when_raw_cached(tmp_path: Path) -> None:
    raw = tmp_path / "raw.md"
    filtered = tmp_path / "filtered.md"
    json_path = tmp_path / "entities.json"
    raw.write_text("raw")
    filtered.write_text("filtered")

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


def test_force_extract_sets_stale_warnings(tmp_path: Path) -> None:
    raw = tmp_path / "raw.md"
    filtered = tmp_path / "filtered.md"
    json_path = tmp_path / "entities.json"
    filtered.write_text("filtered")
    json_path.write_text("{}")

    flags = resolve_cache_flags(
        raw_path=raw,
        filtered_path=filtered,
        json_path=json_path,
        force=False,
        force_extract=True,
        force_llm=False,
    )
    assert not flags.skip_extraction
    assert flags.skip_filter_llm
    assert flags.stale_filtered_warning
    assert flags.stale_json_warning
