# Quickstart — 000 Foundations

How to run this spec locally end-to-end, from a clean checkout.

---

## Prerequisites

- Python 3.11+ on `PATH`
- `uv` installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- (Optional for smoke test) Neo4j 5+ or Memgraph 2.x running on Bolt port 7687

---

## 1. Install dependencies

```bash
uv sync
```

This installs all runtime and dev dependencies from `pyproject.toml` into a `.venv`.

---

## 2. Set required environment variables

For unit tests (no live DB needed):

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=test
```

These values are required at import time but the unit tests mock the driver, so the
actual DB does not need to be running for non-smoke tests.

---

## 3. Run unit tests (no live DB)

```bash
uv run pytest tests/test_000_foundations/ -v -k "not smoke"
```

Expected output: all tests PASSED.

---

## 4. Verify imports

```bash
uv run python -c "from migration_oracle.models import MigrationEntitiesBatch; print('models OK')"
uv run python -c "from migration_oracle.graph.driver import get_driver; print('driver OK')"
uv run python -c "from migration_oracle.graph.indexes import ensure_indexes; print('indexes OK')"
```

---

## 5. Verify config fail-fast

Unset the required vars and verify that `ConfigurationError` is raised:

```bash
unset NEO4J_URI
unset NEO4J_PASSWORD
uv run python -c "import migration_oracle.config" 2>&1
# Expected: ConfigurationError: Required env var 'NEO4J_URI' is not set
```

---

## 6. Run smoke test (requires live DB)

Start Neo4j or Memgraph, then:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=neo4j   # your actual password
uv run pytest tests/test_000_foundations/test_smoke.py -v
```

The smoke test calls `ensure_indexes(get_driver())` and verifies constraints are created.

---

## 7. Check the whole test suite

```bash
uv run pytest tests/test_000_foundations/ -v
```

Smoke test is skipped automatically when `NEO4J_URI` is not set.
