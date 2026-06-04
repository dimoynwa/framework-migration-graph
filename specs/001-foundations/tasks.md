# Tasks — 000 Foundations

> Ordered implementation tasks. `[P]` = can run in parallel with other `[P]` tasks at the same level.
> Do NOT start a task until its dependency is complete.

---

## Phase 1 — Project scaffold (sequential, must be first)

### TASK-001 — Initialise uv project [X]

Create `pyproject.toml` with all runtime and dev dependencies as specified in `plan.md`.
Create the top-level `migration_oracle/` package with an empty `__init__.py`.
Run `uv sync` and verify it exits 0 with a clean lockfile.

**Deliverables:** `pyproject.toml`, `uv.lock`, `migration_oracle/__init__.py`
**Acceptance:** `uv sync` exits 0. `python -c "import migration_oracle"` succeeds.

---

## Phase 2 — Core modules (independent after TASK-001)

### TASK-002 — `config.py` [P] [X]

Implement `migration_oracle/config.py` exactly as specified in `data-model.md`.

Requirements:
- `_require(name)` raises `ConfigurationError(f"Required env var {name!r} is not set")` when absent or empty
- `_optional(name, default)` returns default when absent
- `SSL_VERIFY` parsed: `"false"`, `"False"`, `"FALSE"`, `"0"` → `False`; everything else → `True`
- `MCP_PORT` parsed to `int`; `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` parsed to `float`
- `ConfigurationError(ValueError)` defined in this module
- No imports from `migration_oracle.*`

**Deliverables:** `migration_oracle/config.py`
**Acceptance:** With `NEO4J_URI` and `NEO4J_PASSWORD` unset, `import migration_oracle.config` raises `ConfigurationError`.

---

### TASK-003 — `models/entities.py` [P] [X]

Implement `migration_oracle/models/entities.py` verbatim from `data-model.md`.

Requirements:
- All six enums with exact string values (note hyphens in `CO_REQUIRED = "co-required"`,
  `API_SURFACE = "api-surface"`)
- `MigrationEntitiesBatch`, `MigrationEntity`, `MigrationStep`, `AffectedEntity`, `BreakingScopeInput`
- `SOURCE_SECTION_TO_RULE_TYPE` dict
- `MigrationEntity.source_section` uses `Literal[...]` with all seven values
- No imports from `migration_oracle.config` or `migration_oracle.graph.*`

**Deliverables:** `migration_oracle/models/entities.py`
**Acceptance:** `MigrationEntitiesBatch.model_validate(full_fixture)` succeeds (see test fixture in TASK-007).

---

### TASK-004 — `models/graph.py` [P] [X]

Implement `migration_oracle/models/graph.py` with the dataclasses and `sortable_version()` as
specified in `data-model.md`.

Requirements:
- All five dataclasses (`VersionNode`, `MigrationRuleNode`, `MigrationStepNode`, `BreakingScopeNode`, `MigrationContextNode`)
- `sortable_version(version: str) -> int` formula: `major * 1_000_000 + minor * 1_000 + patch`
- Accepts two-part versions (`"3.2"` → patch defaults to 0)
- Raises `ValueError(f"Cannot parse version: {version!r}")` for anything else
- No imports from `migration_oracle.config` or `migration_oracle.graph.*`

**Deliverables:** `migration_oracle/models/graph.py`
**Acceptance:** `sortable_version("3.2.1") == 3_002_001`. `sortable_version("bad") raises ValueError`.

---

### TASK-005 — `models/__init__.py` [P] [X]

Create `migration_oracle/models/__init__.py` that re-exports all public names from
`entities.py` and `graph.py`. This allows `from migration_oracle.models import MigrationEntitiesBatch`.

**Deliverables:** `migration_oracle/models/__init__.py`

---

## Phase 3 — Graph layer (depends on TASK-002)

### TASK-006 — `graph/driver.py` [X]

Implement `migration_oracle/graph/driver.py` as specified in `plan.md`.

Requirements:
- Module-level `_driver: neo4j.Driver | None = None`
- `get_driver()` lazy-initialises with `neo4j.GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD), encrypted=not config.SSL_VERIFY)`
- `read_session()` context manager using `neo4j.READ_ACCESS`
- `write_session()` context manager using `neo4j.WRITE_ACCESS`
- `close_driver()` calls `_driver.close()` and resets to `None`
- `DriverNotInitialisedError(RuntimeError)` raised by session helpers if driver is `None` after `close_driver()`
- `get_driver()` re-initialises after `close_driver()` was called

**Deliverables:** `migration_oracle/graph/driver.py`
**Acceptance:** Unit test with mocked `neo4j.GraphDatabase.driver` passes (see TASK-009).

---

### TASK-007 — `graph/indexes.py` (depends on TASK-006) [X]

Implement `migration_oracle/graph/indexes.py` as specified in `plan.md` and `data-model.md`.

Requirements:
- `_INDEXES` list with all 15 DDL statements, each using `IF NOT EXISTS`
- `ensure_indexes(driver)` runs each in a separate write transaction
- Catches `neo4j.exceptions.ClientError` and `neo4j.exceptions.CypherSyntaxError` per statement
- Logs WARNING with index statement and error; continues to next statement
- Does not raise on partial failure
- `migration_oracle/graph/__init__.py` created (empty)

**Deliverables:** `migration_oracle/graph/__init__.py`, `migration_oracle/graph/indexes.py`
**Acceptance:** `ensure_indexes` with a mock driver that raises on the full-text DDL calls still processes all remaining statements.

---

## Phase 4 — Tests (depends on Phase 2 + Phase 3)

### TASK-008 — `test_models.py` [P] [X]

Write `tests/test_000_foundations/test_models.py`.

Test cases:
1. **Full round-trip** — `MigrationEntitiesBatch.model_validate(full_fixture)` where `full_fixture` is a JSON dict
   with one entity that has all fields populated, two steps with `requires`, two entities, two scopes.
   Assert field values, enum membership, and that `model_dump()` round-trips cleanly.
2. **Enum string equality** — `EntityKind.CLASS == "class"`, `EntityRole.CO_REQUIRED == "co-required"`,
   `ScopeLevel.API_SURFACE == "api-surface"` all evaluate `True`.
3. **`sortable_version` formula** — `sortable_version("3.2.1") == 3_002_001`,
   `sortable_version("17.0") == 17_000_000`, `sortable_version("bad")` raises `ValueError`.
4. **Source section map completeness** — All seven `source_section` literal values are keys in
   `SOURCE_SECTION_TO_RULE_TYPE`.

**Deliverables:** `tests/test_000_foundations/test_models.py`, `tests/__init__.py`, `tests/test_000_foundations/__init__.py`

---

### TASK-009 — `test_config.py` [P] [X]

Write `tests/test_000_foundations/test_config.py`.

Test cases (all use `monkeypatch` to set/unset env vars, then `importlib.reload(config)`):
1. **Missing `NEO4J_URI`** → `ConfigurationError` naming `NEO4J_URI`
2. **Missing `NEO4J_PASSWORD`** → `ConfigurationError` naming `NEO4J_PASSWORD`
3. **Empty `NEO4J_PASSWORD`** → treated as absent → `ConfigurationError`
4. **`SSL_VERIFY` variants** — `"false"` → `False`; `"FALSE"` → `False`; `"0"` → `False`; `"true"` → `True`; `"yes"` → `True`
5. **`MCP_PORT` parsed to int** — `"9090"` → `9090`
6. **`FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` parsed to float** — `"0.75"` → `0.75`

---

### TASK-010 — `test_driver.py` [P] [X]

Write `tests/test_000_foundations/test_driver.py`.

Test cases (mock `neo4j.GraphDatabase.driver`):
1. **Singleton** — two calls to `get_driver()` return same object; constructor called once
2. **`close_driver()` resets** — after close, `get_driver()` constructs a new driver
3. **`read_session` context manager** — enters and exits without raising
4. **`write_session` context manager** — enters and exits without raising
5. **`DriverNotInitialisedError`** — call `close_driver()`, then `read_session().__enter__()` raises

---

### TASK-011 — `test_indexes.py` [P] [X]

Write `tests/test_000_foundations/test_indexes.py`.

Test cases (mock driver with mock session):
1. **All statements run** — `ensure_indexes` calls the session `run` method once per statement in `_INDEXES`
2. **Partial failure** — mock raises `ClientError` on the full-text index DDL; `ensure_indexes` does not raise;
   remaining statements are still called
3. **Idempotent** — `ensure_indexes` called twice does not raise

---

## Phase 5 — Smoke validation

### TASK-012 — Integration smoke test (depends on all Phase 4 tasks) [X]

Write `tests/test_000_foundations/test_smoke.py` with one integration test gated on
`@pytest.mark.skipif(not os.getenv("NEO4J_URI"), reason="requires live graph")`.

The smoke test:
1. Calls `ensure_indexes(get_driver())`
2. Verifies all constraints exist by running `SHOW CONSTRAINTS` Cypher
3. Closes the driver

This test is skipped in CI unless `NEO4J_URI` is set. It is the only test that requires a live database.

**Deliverables:** `tests/test_000_foundations/test_smoke.py`
