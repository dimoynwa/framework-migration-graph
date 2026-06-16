"""Shared fixtures for MCP server tests."""

import importlib
import os

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")

import pytest

import migration_oracle.config as config
from migration_oracle.graph.driver import close_driver


@pytest.fixture(autouse=True)
def _required_neo4j_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Respect caller-supplied credentials so integration tests work with a real Neo4j.
    # Unit tests mock the driver so the actual values don't matter.
    monkeypatch.setenv("NEO4J_URI", os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    monkeypatch.setenv("NEO4J_USERNAME", os.environ.get("NEO4J_USERNAME", "neo4j"))
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ.get("NEO4J_PASSWORD", "test"))
    monkeypatch.setenv("SSL_VERIFY", os.environ.get("SSL_VERIFY", "false"))
    # Reset the driver singleton so it picks up the new credentials.
    close_driver()
    importlib.reload(config)
    yield
    close_driver()
    importlib.reload(config)
