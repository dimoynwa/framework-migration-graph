# Spec 000 — Foundations

> **Status:** 🔄 In progress
> **Prerequisite:** None — this is the root spec
> **Reference docs:** `migration-oracle-redesign.md` §4.5, `graph-mcp-skills-and-paysafe-resolution.md` §2–3, `GRAPH_STRUCTURE.md`

---

## WHAT it does

Provides the shared Python package scaffold, all Pydantic data models, the graph database
connection layer, and the startup index DDL that every other spec imports or depends on.
Nothing in the system runs until this spec is complete and its completion gate is passing.

## WHY it exists

All five downstream specs (`001` through `005`) import from `migration_oracle.models`,
`migration_oracle.config`, and `migration_oracle.graph`. If those modules are unstable,
inconsistently typed, or missing, every spec that depends on them fails in untraceable ways.
Foundations must be a settled, tested contract before any other spec starts.

---

## Components

### `migration_oracle/models/`

Contains every Pydantic model used by the system. Models are the contract between the
pipeline (which writes JSON) and the graph (which reads it). They must be importable with
no side effects — no network calls, no file reads, no environment requirements.

Named operations / types this module exposes:

- `MigrationEntitiesBatch` — the top-level extraction schema produced by the second LLM call
- `MigrationEntity` — one row from the filtered Markdown table
- `MigrationStep` — one atomic migration action inside an entity
- `AffectedEntity` — one entity reference with kind + role
- `BreakingScopeInput` — a (scope, severity) pair
- Enums: `EntityKind`, `EntityRole`, `StepType`, `Effort`, `ScopeLevel`, `Severity`
- `graph.py` — lightweight value objects for graph node reads (not Pydantic ORM — plain dataclasses)

### `migration_oracle/config.py`

Loads all environment variables at import time. Required vars that are absent must raise
a `ConfigurationError` immediately with the variable name in the message. Optional vars
use documented defaults. No other module in the system does environment variable loading —
all configuration flows through this module.

Named variables this module exposes:

- `NEO4J_URI` (required) — Bolt URI, e.g. `bolt://localhost:7687`
- `NEO4J_USERNAME` (default: `"neo4j"`)
- `NEO4J_PASSWORD` (required)
- `MODEL_PROVIDER` (default: `"anthropic"`) — `bedrock | openai | anthropic | ollama | litellm`
- `MODEL_ID` (default: provider-dependent)
- `GITHUB_TOKEN` (optional — unauthenticated rate limited to 60 req/hr)
- `FINDIT_AUTH_TOKEN` (optional — required only for Paysafe resolution)
- `FINDIT_BASE_URL` (default: `"https://findit.paysafe.com"`)
- `SENTENCE_TRANSFORMERS_MODEL` (default: `"all-mpnet-base-v2"`)
- `SSL_VERIFY` (default: `"true"`) — parsed to bool; `"false"` disables TLS verification everywhere
- `MCP_TRANSPORT` (default: `"stdio"`) — `stdio | sse | streamable-http`
- `MCP_HOST` (default: `"0.0.0.0"`)
- `MCP_PORT` (default: `"8080"`) — parsed to int
- `ARTIFACT_CACHE_DIR` (default: `"./artifacts"`) — root path for pipeline output files
- `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` (default: `"0.68"`) — parsed to float
- `LOG_LEVEL` (default: `"INFO"`)

### `migration_oracle/graph/driver.py`

Manages the Neo4j/Memgraph connection. Provides session helpers for read and write
operations. The driver is a module-level singleton — created once on first call to
`get_driver()`, never re-instantiated per request.

Named operations this module exposes:

- `get_driver()` — returns the singleton `neo4j.Driver`; lazy-initialises on first call
- `read_session()` — context manager; returns a session in read access mode
- `write_session()` — context manager; returns a session in write access mode
- `close_driver()` — tears down the singleton; used in tests and graceful shutdown

### `migration_oracle/graph/indexes.py`

Declares and ensures all graph indexes on startup. Must be idempotent — safe to call
on every server start, on both Neo4j 5+ and Memgraph. Unsupported DDL (e.g. full-text
indexes on Memgraph) must be caught, logged at WARNING level, and not re-raised.

Named operations this module exposes:

- `ensure_indexes(driver)` — the single entry point; called once at startup by any layer that needs it

---

## Key behaviors

**MODEL_SCHEMA_CONTRACT** — `MigrationEntitiesBatch` and all its nested types must match
the Pydantic model definition in `migration-oracle-redesign.md` §4.5 exactly, field by
field, enum value by enum value. No aliases, no extra fields, no omissions.

**SORTABLE_VERSION_FORMULA** — `sortableVersion` is computed as
`major × 1_000_000 + minor × 1_000 + patch` everywhere in the system. This formula must
be available as a utility function in `models/graph.py` so no other module re-implements it.

**DRIVER_SINGLETON** — `get_driver()` must use a module-level variable with a
check-then-assign pattern. The driver must never be instantiated inside a session context
manager, a request handler, or any per-call code path.

**GRACEFUL_MEMGRAPH_DEGRADATION** — When `ensure_indexes` encounters a `ClientError` or
`CypherSyntaxError` from an unsupported DDL statement (e.g. `CREATE FULLTEXT INDEX`),
it catches the exception, logs a WARNING with the index name and error message, and
continues. It must not raise. The remaining indexes continue to be created.

**CONFIG_FAIL_FAST** — Missing required environment variables (`NEO4J_URI`,
`NEO4J_PASSWORD`) must raise `ConfigurationError` at module import time, not at first use.
The error message must name the missing variable.

**SSL_PROPAGATION** — The `SSL_VERIFY` bool from `config.py` must be used as the
`verify` argument for every `httpx` client created anywhere in the system, and as the
`encrypted` / `trust` argument for the Neo4j driver. No module may create a network
client without reading it from `config`.

**MODELS_HAVE_NO_SIDE_EFFECTS** — `from migration_oracle.models.entities import *`
must complete with no network I/O, no file I/O, and no environment variable reads.
Models are pure data shapes.

**ENUM_MEMBERSHIP** — All enums are `str` enums (`class X(str, Enum)`). This means
`EntityKind.CLASS == "class"` evaluates to `True`. This property is relied upon by
Cypher parameter serialisation throughout the pipeline.

---

## Integration constraints

- Python 3.11+ required. `pyproject.toml` must declare `requires-python = ">=3.11"`.
- Dependency management via `uv`. `pyproject.toml` is the single source of truth for
  all runtime and dev dependencies.
- `neo4j` driver version must support both Neo4j 5.x and Memgraph 2.x. Use `neo4j>=5.0`.
- `pydantic>=2.0` required. `BaseModel` with `model_validate` and `model_dump` APIs.
- No circular imports. `config.py` imports nothing from `migration_oracle`. `models/`
  imports nothing from `graph/`. `graph/` imports from `config` only.
- `graph/indexes.py` must not import from `models/` — it operates on the driver only.
- All index DDL must use `IF NOT EXISTS` syntax to remain idempotent on re-runs.

---

## Error cases

**`ConfigurationError`** — raised by `config.py` at import time when a required env var
is absent. Inherits from `ValueError`. Must include the variable name.

**`DriverNotInitialisedError`** — raised by `read_session()` / `write_session()` if
`close_driver()` was called and `get_driver()` has not been called again. Inherits from
`RuntimeError`.

**`IndexEnsureError`** — NOT raised. All index DDL failures are logged, not propagated.
The only exception is a total connection failure before any DDL runs — that is allowed
to propagate as a raw `neo4j.exceptions.ServiceUnavailable`.

---

## Edge cases

**Double-call idempotency** — `ensure_indexes` called twice on the same driver must
produce no errors and no duplicate indexes.

**Empty `NEO4J_PASSWORD`** — An empty string is treated as absent. The password check
must use `if not value` not `if value is None`.

**`SSL_VERIFY=false` (lowercase)** — The config parser must accept `"false"`, `"False"`,
`"FALSE"`, and `"0"` as falsy. Any other value is truthy.

**`sortable_version` on non-semver strings** — If the version string cannot be parsed
into three integer components, `sortable_version()` must raise `ValueError` with the
offending string in the message. It must not silently return 0.
