"""Shared fixtures for paysafe resolver tests."""

import importlib
import os

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")

import pytest

import migration_oracle.config as config


@pytest.fixture(autouse=True)
def _required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "test")
    monkeypatch.setenv("FINDIT_BASE_URL", "https://findit-api.icd.paysafe.cloud")
    importlib.reload(config)
    yield
    importlib.reload(config)
