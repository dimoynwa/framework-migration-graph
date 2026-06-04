"""Shared fixtures for foundations tests."""

import importlib
import os

# Set before any migration_oracle import during collection.
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")

import pytest

import migration_oracle.config as config


@pytest.fixture(autouse=True)
def _required_neo4j_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests need config importable; values are mocked at the driver layer."""
    monkeypatch.setenv("NEO4J_URI", os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ.get("NEO4J_PASSWORD", "test"))
    importlib.reload(config)
    yield
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "test")
    importlib.reload(config)
