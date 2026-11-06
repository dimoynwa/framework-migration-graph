"""Live settings for dossier entity extraction.

Read from the environment on each call so tests and CLI flags see current values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


@dataclass(frozen=True)
class EntitySettings:
    concurrency: int
    cluster_max_rows: int
    cluster_confirm: str
    protected_categories: frozenset[str]
    cache_dir: Path


def load_settings() -> EntitySettings:
    confirm = _env("CLUSTER_CONFIRM", "off").strip().lower()
    if confirm not in {"off", "llm"}:
        raise ValueError("CLUSTER_CONFIRM must be 'off' or 'llm'")
    protected = frozenset(
        part.strip().lower()
        for part in _env("GATE_PROTECTED_CATEGORIES", "breaking,deprecation,security").split(",")
        if part.strip()
    )
    return EntitySettings(
        concurrency=max(1, int(_env("ENTITY_CONCURRENCY", "4"))),
        cluster_max_rows=max(1, int(_env("CLUSTER_MAX_ROWS", "4"))),
        cluster_confirm=confirm,
        protected_categories=protected,
        cache_dir=Path(_env("ARTIFACT_CACHE_DIR", "./artifacts")),
    )


def resolve_entity_source(
    explicit: str | None,
    *,
    skip_research: bool,
    research_enabled: bool,
) -> str:
    """``dossier`` when research ran, otherwise ``filter``.

    ``--entity-source`` wins over the environment. ``--skip-research`` forces
    ``filter``. Asking for dossiers and skipping research is an error.
    """
    if explicit == "dossier" and skip_research:
        raise ValueError(
            "--entity-source dossier cannot be combined with --skip-research"
        )
    if explicit in {"dossier", "filter"}:
        return explicit
    if skip_research:
        return "filter"
    env = os.environ.get("ENTITY_SOURCE", "").strip().lower()
    if env:
        if env not in {"dossier", "filter"}:
            raise ValueError("ENTITY_SOURCE must be 'dossier' or 'filter'")
        return env
    if research_enabled:
        return "dossier"
    return "filter"
