# Plan 000 — Foundations

> **Status:** 🔄 In progress
> **Spec:** `specs/000-foundations/spec.md`

---

## Directory and file layout

```
migration_oracle/
├── __init__.py                     # Empty. Package marker only.
├── config.py                       # All env var loading. Raises ConfigurationError on missing required vars.
├── models/
│   ├── __init__.py                 # Re-exports: MigrationEntitiesBatch, MigrationEntity, MigrationStep,
│   │                               #   AffectedEntity, BreakingScopeInput, all enums
│   ├── entities.py                 # MigrationEntitiesBatch + all nested types + all enums
│   └── graph.py                    # Value objects for graph reads + sortable_version() utility
└── graph/
    ├── __init__.py                 # Empty. Package marker only.
    ├── driver.py                   # Module-level singleton driver; get_driver(), read_session(),
    │                               #   write_session(), close_driver()
    └── indexes.py                  # ensure_indexes(driver) — idempotent DDL on startup

pyproject.toml                      # uv project; all deps declared here
```

Supporting project files (not in `migration_oracle/`):

```
pyproject.toml
uv.lock                             # Committed after uv sync
tests/
└── test_000_foundations/
    ├── test_models.py
    ├── test_config.py
    ├── test_driver.py
    └── test_indexes.py
```

---

## Technology choices

| Concern | Choice | Reason |
|---|---|---|
| Python version | 3.11+ | Required by spec; match-statement, tomllib, ExceptionGroup |
| Dependency manager | `uv` | Project requirement |
| Pydantic | `>=2.0` | `model_validate`, `model_dump`, `str` enum interop |
| Neo4j driver | `neo4j>=5.0` | Supports both Neo4j 5+ and Memgraph 2.x Bolt |
| Test runner | `pytest` | Standard; `pytest-asyncio` for async tests |
| Env var loading | stdlib `os.environ` | No extra deps; `config.py` is the only loader |

---

## Module design decisions

### `config.py`

Reads env vars at module level (not inside functions). Two helper functions are used
internally: `_require(name)` (raises `ConfigurationError` if absent or empty) and
`_optional(name, default)` (returns default if absent). All exported names are module-level
constants. No class required.

```python
# Public interface
NEO4J_URI: str
NEO4J_USERNAME: str
NEO4J_PASSWORD: str
MODEL_PROVIDER: str
MODEL_ID: str
GITHUB_TOKEN: str          # "" when not set
FINDIT_AUTH_TOKEN: str     # "" when not set
FINDIT_BASE_URL: str
SENTENCE_TRANSFORMERS_MODEL: str
SSL_VERIFY: bool           # parsed from string
MCP_TRANSPORT: str
MCP_HOST: str
MCP_PORT: int              # parsed from string
ARTIFACT_CACHE_DIR: str
FINDIT_SERVICE_NAME_FUZZY_THRESHOLD: float  # parsed from string
LOG_LEVEL: str

class ConfigurationError(ValueError): ...
```

### `models/entities.py`

Verbatim implementation of the Pydantic model from `migration-oracle-redesign.md` §4.5.
No deviation from the field names, types, or enum values defined there. The `source_section`
field on `MigrationEntity` uses `Literal[...]` exactly as specified.

The `MigrationStep` name shadows the graph node concept — this is intentional. The Pydantic
model is the input schema (extracted from LLM output). The graph node is a separate concept;
do not conflate them.

### `models/graph.py`

Plain Python dataclasses (not Pydantic) for reading graph node data back out of Cypher
results. These are not persisted — they exist so the MCP tools and Streamlit UI have
typed return objects instead of raw dicts.

```python
@dataclass
class VersionNode:
    framework: str
    version: str
    sortable_version: int
    raw_md_path: str | None
    filtered_md_path: str | None
    entities_json_path: str | None

@dataclass
class MigrationRuleNode:
    element_id: str
    statement: str
    rule_type: str
    change_type: str
    entity_classification: str
    title: str | None
    jira_keys: list[str]
    source_url: str

@dataclass
class MigrationStepNode:
    element_id: str
    step_type: str
    summary: str
    instruction: str
    effort: str
    automatable: bool
    verification_hint: str
    cli_operation: str

@dataclass
class BreakingScopeNode:
    scope: str
    severity: str

# Utility
def sortable_version(version: str) -> int:
    """Compute major * 1_000_000 + minor * 1_000 + patch. Raises ValueError on bad input."""
```

### `graph/driver.py`

Module-level singleton pattern:

```python
_driver: neo4j.Driver | None = None

def get_driver() -> neo4j.Driver:
    global _driver
    if _driver is None:
        _driver = neo4j.GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD),
            encrypted=not config.SSL_VERIFY,   # SSL_VERIFY=False → unencrypted
        )
    return _driver

@contextmanager
def read_session():
    yield get_driver().session(default_access_mode=neo4j.READ_ACCESS)

@contextmanager
def write_session():
    yield get_driver().session(default_access_mode=neo4j.WRITE_ACCESS)

def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
```

### `graph/indexes.py`

```python
_INDEXES = [
    # Uniqueness constraints (idempotent on re-run)
    "CREATE CONSTRAINT version_unique IF NOT EXISTS FOR (v:Version) REQUIRE (v.framework, v.version) IS UNIQUE",
    "CREATE CONSTRAINT migration_rule_url IF NOT EXISTS FOR (r:MigrationRule) REQUIRE r.sourceUrl IS UNIQUE",
    "CREATE CONSTRAINT class_name IF NOT EXISTS FOR (c:Class) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT property_name IF NOT EXISTS FOR (p:ApplicationProperty) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT dependency_name IF NOT EXISTS FOR (d:Dependency) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT breaking_scope_pair IF NOT EXISTS FOR (bs:BreakingScope) REQUIRE (bs.scope, bs.severity) IS UNIQUE",
    "CREATE CONSTRAINT migration_context_key IF NOT EXISTS FOR (mc:MigrationContext) REQUIRE (mc.projectId, mc.fromVersion, mc.toVersion) IS UNIQUE",
    # Range indexes for version range queries
    "CREATE INDEX version_sortable IF NOT EXISTS FOR (v:Version) ON (v.sortableVersion)",
    "CREATE INDEX version_framework IF NOT EXISTS FOR (v:Version) ON (v.framework)",
    # Full-text index — may fail on Memgraph; caught and logged
    "CREATE FULLTEXT INDEX rule_statement IF NOT EXISTS FOR (r:MigrationRule) ON EACH [r.statement]",
    "CREATE FULLTEXT INDEX step_instruction IF NOT EXISTS FOR (s:MigrationStep) ON EACH [s.instruction, s.summary]",
    # Step and scope lookups
    "CREATE INDEX step_rule_index IF NOT EXISTS FOR (s:MigrationStep) ON (s.ruleId, s.stepIndex)",
    "CREATE INDEX step_effort IF NOT EXISTS FOR (s:MigrationStep) ON (s.effort)",
    "CREATE INDEX breaking_scope_scope IF NOT EXISTS FOR (bs:BreakingScope) ON (bs.scope)",
    "CREATE INDEX context_project IF NOT EXISTS FOR (mc:MigrationContext) ON (mc.projectId)",
]

def ensure_indexes(driver: neo4j.Driver) -> None: ...
```

The function iterates `_INDEXES`, runs each in its own write transaction, catches
`neo4j.exceptions.ClientError` and `neo4j.exceptions.CypherSyntaxError` per statement,
logs WARNING, and continues.

---

## `pyproject.toml` structure

```toml
[project]
name = "migration-oracle"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "neo4j>=5.0",
    "pydantic>=2.0",
    "httpx>=0.27",
    "langchain>=0.2",
    "langchain-community>=0.2",
    "sentence-transformers>=3.0",
    "mcp>=1.0",
    "streamlit>=1.35",
    "click>=8.1",
    "rapidfuzz>=3.0",       # Paysafe fuzzy name matching
    "structlog>=24.0",      # Structured logging
]

[project.scripts]
migration-oracle = "migration_oracle.cli:main"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.14",
]
```

---

## Test strategy

Tests live in `tests/test_000_foundations/`. All tests must pass with no live Neo4j
or Memgraph instance — a `pytest-mock` fixture patches the driver.

| Test file | What it covers |
|---|---|
| `test_models.py` | Round-trip `MigrationEntitiesBatch.model_validate` on a full JSON fixture; enum membership equality; `sortable_version()` formula and error case |
| `test_config.py` | Missing required var → `ConfigurationError`; `SSL_VERIFY` parsing variants; empty password treated as absent |
| `test_driver.py` | Singleton — two calls return same object; `close_driver()` resets singleton; `read_session` / `write_session` context managers |
| `test_indexes.py` | `ensure_indexes` continues after a single DDL failure; calls each statement; idempotent on second call |
