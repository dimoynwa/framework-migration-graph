"""Isolation for triage tests.

Triage reads ``TRIAGE_*`` live from the environment. A developer shell that
exports the local classifier must not leak into these tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")


@pytest.fixture(autouse=True)
def _isolated_triage_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "test")
    for name in (
        "TRIAGE_BASE_URL",
        "TRIAGE_MODEL",
        "TRIAGE_API_KEY",
        "TRIAGE_ENDPOINT_PATH",
        "TRIAGE_DROP_MAX_ACTION_PROB",
        "TRIAGE_DROP_MIN_CATEGORY_PROB",
        "TRIAGE_DROP_MAX_IMPACT_SCORE",
        "FILTER_MAX_INPUT_TOKENS",
        "RESEARCH_BASE_URL",
        "RESEARCH_MODEL_ID",
        "RESEARCH_API_KEY",
        "RESEARCH_ENABLE_THINKING",
        "RESEARCH_MAX_CONCURRENT",
        "RESEARCH_MAX_TOOL_CALLS",
        "RESEARCH_TIMEOUT_SEC",
        "RESEARCH_MODEL_TIMEOUT_SEC",
        "RESEARCH_SEARCH_RESULTS",
        "RESEARCH_FETCH_MAX_CHARS",
        "TAVILY_API_KEY",
        "ENTITY_MAX_INPUT_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ARTIFACT_CACHE_DIR", str(tmp_path / "artifacts"))
    # LLM calls are faked; the CLI still requires an explicit model id.
    import migration_oracle.config as config

    monkeypatch.setattr(config, "MODEL_ID", "test-model")
    from migration_oracle.pipeline.research.run import reset_notices as reset_research_notices
    from migration_oracle.pipeline.research.settings import reset_url_notice
    from migration_oracle.pipeline.triage.run import reset_notices

    reset_notices()
    reset_research_notices()
    reset_url_notice()
