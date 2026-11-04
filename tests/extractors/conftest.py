"""Shared fixtures for extractor tests."""

from __future__ import annotations

import os

import pytest

# config.py reads required vars at import. Unit tests do not talk to Neo4j.
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")

from migration_oracle import config


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _no_github_token_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep extractor tests off the GitHub issue API unless a test opts in.

    Enrichment runs only when ``GITHUB_TOKEN`` is set. A developer token in the
    environment would otherwise make existing Spring Boot tests call ``/issues/``.
    """
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    monkeypatch.setattr(config, "SPRING_BOOT_GITHUB_ENRICHMENT", True)
    monkeypatch.setattr(config, "ANGULAR_GITHUB_ENRICHMENT", True)
