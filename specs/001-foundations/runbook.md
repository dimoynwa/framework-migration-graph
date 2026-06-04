# Runbook — 000 Foundations

> Copy-paste prompts for every SpecKit step, post-step gap reviews, and recovery prompts.
> This runbook assumes you are working in Claude Code with the project root open.

---

## Prerequisites

None. `000-foundations` has no upstream spec dependency.

Before running any SpecKit command, verify:
- [ ] `uv` is installed and on `PATH`
- [ ] The four reference documents are in the project knowledge base
- [ ] `SPEC_ORGANIZATION.md` is in project knowledge and shows `000` as the active spec

---

## Step 1 — `/speckit.specify`

The `spec.md` is already written at `specs/000-foundations/spec.md`. Paste it as context for
Claude Code before running `/speckit.specify`. If SpecKit regenerates it, use the gap review
below immediately.

**Prompt to paste:**

```
/speckit.specify

WHAT it does: Provides the shared Python package scaffold, all Pydantic data models,
the Neo4j/Memgraph connection layer, and the startup index DDL that every other spec
imports. Nothing in the Migration Oracle system runs until this spec is complete.

WHY it exists: Specs 001–005 all import from migration_oracle.models, migration_oracle.config,
and migration_oracle.graph. These modules must be a settled, tested contract before any
downstream spec starts. If they are unstable, every spec that depends on them fails in
untraceable ways.

MODELS MODULE and what it does:
- Exposes the full MigrationEntitiesBatch Pydantic schema (verbatim from migration-oracle-redesign.md §4.5)
  including MigrationEntity, MigrationStep, AffectedEntity, BreakingScopeInput, and all enums:
  EntityKind, EntityRole, StepType, Effort, ScopeLevel, Severity
- Exposes SOURCE_SECTION_TO_RULE_TYPE dict (source_section string → ruleType graph property value)
- Exposes sortable_version(version: str) -> int utility (major * 1_000_000 + minor * 1_000 + patch)
- Exposes read-only graph dataclasses: VersionNode, MigrationRuleNode, MigrationStepNode,
  BreakingScopeNode, MigrationContextNode

CONFIG MODULE and what it does:
- Loads all environment variables at module import time
- Raises ConfigurationError (subclass of ValueError) for absent or empty required vars
- Required: NEO4J_URI, NEO4J_PASSWORD
- Optional with defaults: NEO4J_USERNAME, MODEL_PROVIDER, MODEL_ID, GITHUB_TOKEN,
  FINDIT_AUTH_TOKEN, FINDIT_BASE_URL, SENTENCE_TRANSFORMERS_MODEL, SSL_VERIFY,
  MCP_TRANSPORT, MCP_HOST, MCP_PORT, ARTIFACT_CACHE_DIR,
  FINDIT_SERVICE_NAME_FUZZY_THRESHOLD, LOG_LEVEL

GRAPH DRIVER MODULE and what it does:
- Manages the Neo4j/Memgraph Bolt connection as a module-level singleton
- Exposes: get_driver(), read_session(), write_session(), close_driver()
- get_driver() lazy-initialises on first call; never re-instantiates per request

GRAPH INDEXES MODULE and what it does:
- Declares and ensures all graph indexes and uniqueness constraints on startup
- Exposes: ensure_indexes(driver) — idempotent, catches DDL failures, logs and continues

KEY BEHAVIORS:
MODEL_SCHEMA_CONTRACT — MigrationEntitiesBatch matches migration-oracle-redesign.md §4.5 exactly: field names, types, enum values, Literal values. No aliases, no extras.
SORTABLE_VERSION_FORMULA — sortable_version() is the only implementation of major*1_000_000+minor*1_000+patch in the codebase. All other modules import it.
DRIVER_SINGLETON — get_driver() uses module-level check-then-assign. Never instantiated inside a session, handler, or per-call path.
GRACEFUL_MEMGRAPH_DEGRADATION — ensure_indexes catches ClientError/CypherSyntaxError per DDL statement, logs WARNING, continues. Does not raise.
CONFIG_FAIL_FAST — Missing NEO4J_URI or NEO4J_PASSWORD raises ConfigurationError at import time with the variable name in the message.
SSL_PROPAGATION — SSL_VERIFY bool from config is used as the verify/encrypted argument for every network client in the system.
MODELS_HAVE_NO_SIDE_EFFECTS — Importing models/* completes with no network I/O, file I/O, or env var reads.
ENUM_MEMBERSHIP — All enums are str enums. EntityKind.CLASS == "class" is True. Required for Cypher parameter serialisation.

INTEGRATION CONSTRAINTS:
- Python 3.11+. pyproject.toml declares requires-python = ">=3.11".
- uv for dependency management. No pip install commands.
- neo4j>=5.0, pydantic>=2.0, httpx>=0.27, langchain>=0.2, langchain-community>=0.2,
  sentence-transformers>=3.0, mcp>=1.0, streamlit>=1.35, click>=8.1, rapidfuzz>=3.0,
  structlog>=24.0.
- No circular imports. config.py imports stdlib only. models/* imports pydantic/typing/enum/stdlib.
  graph/driver.py imports neo4j + config. graph/indexes.py imports neo4j + config.
- graph/indexes.py is the only module issuing CREATE CONSTRAINT / CREATE INDEX Cypher.
- config.py is the only module reading os.environ.
- neo4j.GraphDatabase.driver() is called only in graph/driver.py.
- All index DDL uses IF NOT EXISTS for idempotency.
```

---

## Gap review — post-specify

Paste this immediately after SpecKit generates `spec.md`:

```
Review the generated spec.md for 000-foundations and check for these critical gaps
before we proceed to planning:

GAP-001: Enum hyphen values
  EntityRole.CO_REQUIRED must serialise as "co-required" (hyphen, not underscore).
  ScopeLevel.API_SURFACE must serialise as "api-surface" (hyphen).
  If spec says "co_required" or "api_surface", that is wrong — fix it.

GAP-002: sortable_version edge cases
  The spec must state what happens on a two-part version string ("3.2" → patch=0)
  and what error is raised on unparseable input (ValueError with the offending string).
  If these cases are missing, add them.

GAP-003: SSL_VERIFY falsy variants
  The spec must list exactly which string values are treated as False:
  "false", "False", "FALSE", "0". Any other value is True.
  If only "false" is mentioned, expand to all four.

GAP-004: DriverNotInitialisedError
  The spec must state that read_session() and write_session() raise DriverNotInitialisedError
  (subclass of RuntimeError) if close_driver() was called and get_driver() has not been
  called again. If this error case is missing, add it.

GAP-005: Empty password treated as absent
  The spec must explicitly state that an empty string for NEO4J_PASSWORD is treated as
  absent and raises ConfigurationError. "if not value" not "if value is None".
  If this is not explicit, add it.

GAP-006: SOURCE_SECTION_TO_RULE_TYPE ownership
  The mapping from source_section values to ruleType graph property values must be
  defined as a module-level constant in models/entities.py, not in populator.py.
  If the spec does not specify this ownership, add it.

GAP-007: No DDL in pipeline or MCP code
  The spec must state that graph/indexes.py is the ONLY module that issues
  CREATE CONSTRAINT or CREATE INDEX Cypher. If this constraint is missing, add it.

GAP-008: Write boundary clarity
  The spec must state which modules write to the graph (indexes.py, populator.py,
  community.py, context.py) and which are read-only (all MCP query tools, Streamlit UI).
  If write boundaries are not explicit, add them.

Fix any gaps above before proceeding to /speckit.plan.
```

---

## Step 2 — `/speckit.plan`

```
/speckit.plan

Use spec.md for 000-foundations (already written at specs/000-foundations/spec.md).

Required plan artifacts:
1. plan.md — file layout, module design decisions, tech choices, test strategy
2. data-model.md — all Pydantic types verbatim from migration-oracle-redesign.md §4.5,
   all dataclasses, the sortable_version utility, all env vars with types and defaults,
   full index DDL table
3. contracts/000-foundations.md — import rules, what downstream specs may/must import,
   graph access boundaries, error type ownership
4. quickstart.md — how to run the spec locally (uv sync, set env vars, run pytest)

Key constraints for the plan:
- Repository layout must match the structure in the prompt exactly:
  migration_oracle/config.py, migration_oracle/models/entities.py,
  migration_oracle/models/graph.py, migration_oracle/graph/driver.py,
  migration_oracle/graph/indexes.py
- pyproject.toml at repo root, not inside migration_oracle/
- Tests in tests/test_000_foundations/ (not tests/foundations/ or test_foundations/)
- driver.py uses module-level _driver: neo4j.Driver | None = None with get_driver()
  lazy-init pattern — document this in plan.md
- ensure_indexes iterates _INDEXES list, one write transaction per statement, catches
  exceptions per statement (not per batch)
- models/__init__.py re-exports all public names so downstream can do
  "from migration_oracle.models import MigrationEntitiesBatch"
```

---

## Gap review — post-plan

```
Review the generated plan.md, data-model.md, and contracts/ for 000-foundations
and check for these gaps before we run /speckit.tasks:

PLAN-GAP-001: data-model.md completeness
  data-model.md must contain the complete Pydantic model code (all six enums, all five
  models) and the complete SOURCE_SECTION_TO_RULE_TYPE dict. If any enum or model is
  missing or abbreviated, expand it.

PLAN-GAP-002: _INDEXES list in data-model.md
  The 15 index DDL statements must be enumerated in data-model.md as a reference table
  (index name, node, property). If they are described in prose without listing all 15,
  expand to the full table.

PLAN-GAP-003: Singleton pattern documented
  plan.md must show the module-level pattern with _driver variable and check-then-assign.
  If it only says "singleton" without showing the code pattern, add the code snippet.

PLAN-GAP-004: Test isolation
  plan.md test strategy must state that all tests except the smoke test run without a
  live database (mock the driver). If this is not explicit, add it.

PLAN-GAP-005: quickstart.md exists
  Verify quickstart.md was generated. If missing, create it with: uv sync, env var setup
  (NEO4J_URI, NEO4J_PASSWORD), and how to run pytest with and without the live DB flag.

PLAN-GAP-006: models/__init__.py scope
  plan.md must list models/__init__.py as a deliverable that re-exports all public names.
  If it is absent from the file layout, add it.

PLAN-GAP-007: graph/__init__.py scope
  plan.md must list graph/__init__.py as a deliverable (empty package marker).
  If it is absent from the file layout, add it.
```

---

## Step 3 — `/speckit.tasks`

```
/speckit.tasks
```

No additional context needed — SpecKit reads the plan automatically.

---

## Gap review — post-tasks

```
Review the generated tasks.md for 000-foundations and check for these gaps:

TASK-GAP-001: Foundation ordering
  TASK-001 (uv project init) must be the first task, before any module tasks.
  config.py and models/* may be parallel (Phase 2). graph/driver.py and graph/indexes.py
  come after config.py (Phase 3). Tests come after modules (Phase 4).
  If tasks are not ordered in these phases, reorder them.

TASK-GAP-002: Parallel markers
  TASK-002 (config.py), TASK-003 (models/entities.py), TASK-004 (models/graph.py), and
  TASK-005 (models/__init__.py) are independent and must all be marked [P].
  If any of these lack [P] markers, add them.

TASK-GAP-003: Test tasks cover all error cases
  test_config.py must include: missing URI, missing password, empty password,
  SSL_VERIFY variants (false/False/FALSE/0/true/yes), MCP_PORT as int, threshold as float.
  test_driver.py must include the DriverNotInitialisedError after close_driver case.
  test_indexes.py must include partial failure (one DDL fails, others continue).
  If any of these cases are missing from the task descriptions, add them.

TASK-GAP-004: Smoke test is live-DB-gated
  The smoke test task must specify @pytest.mark.skipif(not os.getenv("NEO4J_URI")).
  If the task does not mention this skip condition, add it.

TASK-GAP-005: Enum acceptance criteria
  The models test task must include explicit assertion that
  EntityRole.CO_REQUIRED == "co-required" and ScopeLevel.API_SURFACE == "api-surface".
  If these specific assertions are missing, add them to the task acceptance criteria.
```

---

## Step 4 — `/speckit.implement`

```
/speckit.implement
```

---

## Recovery prompts

Use these verbatim when Claude Code drifts from the spec.

### Recovery 1 — Wrong enum values (hyphen vs underscore)

```
The EntityRole and ScopeLevel enums must use hyphens in their string values, not underscores.
Correct values:
  EntityRole.CO_REQUIRED = "co-required"   (not "co_required")
  ScopeLevel.API_SURFACE = "api-surface"   (not "api_surface")
These values are written to the graph as Cypher string parameters and queried back exactly.
Fix the enum definitions in models/entities.py.
```

### Recovery 2 — config.py reads env vars lazily

```
config.py must read all environment variables at module import time, not inside functions.
The current implementation defers reading to first call — that is wrong.
Required vars must raise ConfigurationError at import time, not at first use.
Rewrite config.py so all constants are assigned at module level (top-level code),
not inside a function, class, or __init__.
```

### Recovery 3 — Driver instantiated outside get_driver()

```
neo4j.GraphDatabase.driver() must only be called inside get_driver() in graph/driver.py.
Do not call it in read_session(), write_session(), or anywhere else.
The pattern is:
  _driver: neo4j.Driver | None = None

  def get_driver() -> neo4j.Driver:
      global _driver
      if _driver is None:
          _driver = neo4j.GraphDatabase.driver(...)
      return _driver

  @contextmanager
  def read_session():
      yield get_driver().session(default_access_mode=neo4j.READ_ACCESS)

Fix graph/driver.py to use this pattern exactly.
```

### Recovery 4 — ensure_indexes raises on DDL failure

```
ensure_indexes must NOT raise when a DDL statement fails.
The correct behaviour: catch ClientError and CypherSyntaxError per statement,
log a WARNING with the statement and error, and continue to the next statement.
Only a total connection failure (ServiceUnavailable before any DDL) is allowed to propagate.
Fix graph/indexes.py so that one failed statement does not abort the remaining ones.
```

### Recovery 5 — models/ importing from config or graph

```
models/entities.py and models/graph.py must import nothing from migration_oracle.config
or migration_oracle.graph.*. These modules are pure data shapes.
If you see any import from config or graph inside models/, remove it.
The dependency direction is strictly: config ← graph ← pipeline/mcp (all import config).
Models are imported by pipeline and mcp but import nothing from them.
```

### Recovery 6 — Wrong file path for tests

```
Tests for spec 000 must be in tests/test_000_foundations/, not in tests/foundations/
or tests/test_foundations/ or tests/.
The test files are:
  tests/test_000_foundations/test_models.py
  tests/test_000_foundations/test_config.py
  tests/test_000_foundations/test_driver.py
  tests/test_000_foundations/test_indexes.py
  tests/test_000_foundations/test_smoke.py
Move any misplaced test files to the correct location.
```

---

## What success looks like

The completion gate from `SPEC_ORGANIZATION.md` for `000-foundations`:

```bash
# All unit tests pass (no live DB required)
uv run pytest tests/test_000_foundations/ -v -k "not smoke"

# Expected: all PASSED, zero FAILED, zero ERROR

# Imports work
uv run python -c "from migration_oracle.models import MigrationEntitiesBatch; print('OK')"
uv run python -c "from migration_oracle.graph.driver import get_driver; print('OK')"
uv run python -c "from migration_oracle.graph.indexes import ensure_indexes; print('OK')"

# Config fails fast on missing vars (NEO4J_URI and NEO4J_PASSWORD not set)
uv run python -c "import migration_oracle.config" 2>&1 | grep "ConfigurationError"

# Smoke test (requires live DB)
NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test \
  uv run pytest tests/test_000_foundations/test_smoke.py -v
```

Gate checklist:
- [ ] `MigrationEntitiesBatch` and all sub-models importable with no errors
- [ ] `graph/driver.py` connects to a running Neo4j or Memgraph instance
- [ ] `graph/indexes.py` is idempotent — running it twice does not raise
- [ ] All env vars load with defaults; missing required vars raise at import time
- [ ] `uv sync` produces a clean environment
