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
    importlib.reload(config)
    yield
