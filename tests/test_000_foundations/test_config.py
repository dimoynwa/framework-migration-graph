"""Tests for environment configuration loading."""

import importlib

import pytest

import migration_oracle.config as config


def _reload_config() -> None:
    importlib.reload(config)


def test_missing_neo4j_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    with pytest.raises(ValueError, match="NEO4J_URI"):
        _reload_config()


def test_missing_neo4j_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="NEO4J_PASSWORD"):
        _reload_config()


def test_empty_neo4j_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "")
    with pytest.raises(ValueError, match="NEO4J_PASSWORD"):
        _reload_config()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("true", True),
        ("yes", True),
    ],
)
def test_ssl_verify_variants(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("SSL_VERIFY", raw)
    _reload_config()
    assert config.SSL_VERIFY is expected


def test_mcp_port_parsed_to_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("MCP_PORT", "9090")
    _reload_config()
    assert config.MCP_PORT == 9090
    assert isinstance(config.MCP_PORT, int)


def test_findit_fuzzy_threshold_parsed_to_float(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("FINDIT_SERVICE_NAME_FUZZY_THRESHOLD", "0.75")
    _reload_config()
    assert config.FINDIT_SERVICE_NAME_FUZZY_THRESHOLD == 0.75
