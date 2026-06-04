"""Artifact cache decisions and force-flag handling."""

from dataclasses import dataclass
from pathlib import Path


def is_cached(path: Path) -> bool:
    """Return whether an artifact file already exists on disk."""
    return path.exists()


def mark_cached(path: Path, content: str) -> None:
    """Write artifact content to disk, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@dataclass(frozen=True)
class CacheFlags:
    """Resolved skip/reuse decisions for one pipeline run."""

    skip_extraction: bool
    skip_filter_llm: bool
    skip_entity_llm: bool
    raw_was_cached: bool
    stale_filtered_warning: bool
    stale_json_warning: bool


def resolve_cache_flags(
    *,
    raw_path: Path,
    filtered_path: Path,
    json_path: Path,
    force: bool,
    force_extract: bool,
    force_llm: bool,
) -> CacheFlags:
    """
    Six independent cache conditions:

    1. Raw exists without --force-extract/--force → skip extraction.
    2. JSON exists without --force-llm/--force → skip both LLM calls.
    3. Filtered exists, raw was cached, JSON missing → skip filter LLM only.
    4. --force → re-run extraction and both LLM steps.
    5. --force-extract only → re-extract raw; reuse LLM artifacts (stale warnings).
    6. --force-llm only → re-run LLM steps; reuse raw when present.
    """
    raw_exists = raw_path.exists()
    filtered_exists = filtered_path.exists()
    json_exists = json_path.exists()

    if force:
        return CacheFlags(
            skip_extraction=False,
            skip_filter_llm=False,
            skip_entity_llm=False,
            raw_was_cached=False,
            stale_filtered_warning=False,
            stale_json_warning=False,
        )

    skip_extraction = raw_exists and not force_extract
    raw_was_cached = skip_extraction

    skip_entity_llm = json_exists and not force_llm
    skip_filter_llm = skip_entity_llm or (
        filtered_exists and not force_llm and (raw_was_cached or force_extract)
    )

    stale_filtered_warning = force_extract and not force_llm and filtered_exists
    stale_json_warning = force_extract and not force_llm and json_exists

    return CacheFlags(
        skip_extraction=skip_extraction,
        skip_filter_llm=skip_filter_llm,
        skip_entity_llm=skip_entity_llm,
        raw_was_cached=raw_was_cached,
        stale_filtered_warning=stale_filtered_warning,
        stale_json_warning=stale_json_warning,
    )
