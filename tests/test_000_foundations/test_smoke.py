"""Integration smoke test against a live Neo4j instance."""

import importlib
import os

import pytest

import migration_oracle.config as config
import migration_oracle.graph.driver as driver_mod
from migration_oracle.graph.indexes import _EXPECTED_CONSTRAINTS, ensure_indexes

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="requires live graph",
)


def test_ensure_indexes_on_live_neo4j(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use env from the shell; default SSL_VERIFY=false for local non-TLS Bolt."""
    monkeypatch.setenv("NEO4J_URI", os.environ["NEO4J_URI"])
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ.get("NEO4J_PASSWORD", "password123"))
    monkeypatch.setenv("NEO4J_USERNAME", os.environ.get("NEO4J_USERNAME", "neo4j"))
    monkeypatch.setenv("SSL_VERIFY", os.environ.get("SSL_VERIFY", "false"))
    importlib.reload(config)
    driver_mod.close_driver()
    importlib.reload(driver_mod)

    driver = driver_mod.get_driver()
    try:
        ensure_indexes(driver)
        with driver.session() as session:
            result = session.run("SHOW CONSTRAINTS")
            names = {record["name"] for record in result}
        missing = _EXPECTED_CONSTRAINTS - names
        # Populated graphs may have duplicate MigrationRule.sourceUrl values that
        # prevent creating migration_rule_url; other constraints must still exist.
        allowed_missing = {"migration_rule_url"}
        unexpected = missing - allowed_missing
        assert not unexpected, f"Missing constraints: {unexpected}"
    finally:
        driver_mod.close_driver()
