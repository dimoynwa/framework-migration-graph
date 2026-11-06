"""Shared fixtures for pipeline-core tests."""

import importlib
import os

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")

import pytest

import migration_oracle.config as config


@pytest.fixture(autouse=True)
def _neo4j_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "test")
    # LLM calls are faked; the CLI still requires an explicit model id.
    monkeypatch.setenv("MODEL_ID", "test-model")
    # A developer shell may export the local classifier. Pipeline tests that
    # predate triage must keep the historical 4-column path.
    for name in (
        "TRIAGE_BASE_URL",
        "TRIAGE_MODEL",
        "TRIAGE_API_KEY",
        "TRIAGE_ENDPOINT_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    importlib.reload(config)
    yield
