# Module Contracts: PaysafeMigrationOracle MCP Server (005)

**Phase 1 output** | Branch: `005-mcp-server` | Date: 2026-06-07

These contracts are hard constraints on module boundaries and implementation patterns. Violations must be caught in code review before merge.

---

## Contract A — Paysafe tool module import boundary

**File**: `migration_oracle/mcp/tools/paysafe.py`

`mcp/tools/paysafe.py` MUST import **only** `migration_oracle.paysafe.resolver.resolve`. It MUST NOT import:
- `migration_oracle.paysafe.findit`
- `migration_oracle.paysafe.gitlab`
- `migration_oracle.paysafe._types`
- Any other symbol from `migration_oracle.paysafe.*` directly

The only responsibilities of `paysafe.py` are:
1. Accept MCP tool parameters.
2. Map those parameters to the `resolve()` function signature.
3. Pass the return value of `resolve()` directly back to the MCP framework.

**Why**: The `resolve()` function is the sole public API of the Paysafe resolver module. Direct imports of `findit.py` or `gitlab.py` from a tool module would bypass the orchestration layer, skip error handling in `resolver.py`, and couple the MCP tool to internal implementation details that are subject to change.

**Compliant example**:
```python
from migration_oracle.paysafe.resolver import resolve

def resolve_paysafe_dependency_by_service_name(service_name: str, ...) -> dict:
    return resolve(service_name=service_name, ...)
```

**Violation example** (do not do this):
```python
from migration_oracle.paysafe.findit import lookup  # VIOLATES CONTRACT A
```

---

## Contract B — Artifact tool filesystem path restriction

**File**: `migration_oracle/mcp/tools/artifacts.py`

`mcp/tools/artifacts.py` MUST resolve all file paths exclusively from `Version` node properties. The tool MUST NOT:
- Accept a file path as a direct parameter from the MCP caller.
- Construct or infer a path from caller-supplied strings (e.g., by joining `framework + "/" + version + ".md"`).
- Read any file whose path was not retrieved from a `Version` node's `rawMdPath`, `filteredMdPath`, or `entitiesJsonPath` property.

The enforced read path is:
1. Caller supplies `(framework, from_version, to_version, artifact_type)`.
2. Tool queries the graph: `MATCH (v:Version {framework: $framework, version: $to_version}) RETURN v.rawMdPath, v.filteredMdPath, v.entitiesJsonPath`.
3. Tool reads the property value matching `artifact_type`.
4. Tool opens the file at that path.

If the Version node does not exist, or the requested property is null, the tool returns a `not_found` error without touching the filesystem.

**Why**: Accepting caller-supplied file paths is a path traversal vulnerability. Binding all file access to graph-stored node properties ensures the server can only read files that the data pipeline explicitly registered.

---

## Contract C — Query module dependency direction

**Directories**: `migration_oracle/mcp/graph/queries/` and `migration_oracle/mcp/tools/`

The dependency arrow is **one-way**: `mcp/tools/` → `mcp/graph/queries/`. Specifically:

- `mcp/graph/queries/*.py` modules MUST NOT import from `mcp/tools/*.py`.
- `mcp/graph/queries/*.py` modules MUST NOT import from `mcp/server.py`.
- `mcp/tools/*.py` modules MUST import their Cypher execution functions from `mcp/graph/queries/*.py`.
- `mcp/tools/*.py` modules MUST NOT inline Cypher strings (FR-041).

The only imports `mcp/graph/queries/*.py` modules may have from within the `migration_oracle` package are:
- `migration_oracle.graph.driver` (session helpers)
- `migration_oracle.config` (env vars)

**Why**: Inverting this dependency (queries importing from tools) would create circular imports and make graph queries impossible to test in isolation without instantiating MCP tool handlers.

---

## Contract D — execute_custom_cypher in-process mutation blocking

**File**: `migration_oracle/mcp/graph/queries/schema.py` and `migration_oracle/mcp/tools/schema.py`

`execute_custom_cypher` MUST apply TWO independent enforcement layers:

**Layer 1 — In-process keyword check** (in `mcp/graph/queries/schema.py` or the tool handler, BEFORE any graph contact):

The query string MUST be rejected (returning a `CypherResult` with `status="blocked"`) if it contains any of the following, case-insensitively:
- `CREATE`
- `MERGE`
- `SET`
- `DELETE`
- `REMOVE`
- `DROP`
- `CALL db` (as a prefix — blocks `CALL db.index.*`, `CALL db.create.*`, etc.)

The rejection MUST happen before any call to the Neo4j driver. The driver is never contacted for a blocked query.

**Layer 2 — READ session** (in `mcp/graph/queries/schema.py`):

All sessions opened for `execute_custom_cypher` MUST use `neo4j.READ_ACCESS` mode via the existing `read_session()` context manager from `migration_oracle.graph.driver`.

**Neither layer alone is sufficient** — both are required. The in-process check protects against cases where the Neo4j READ session might not block all mutation attempts (e.g., stored procedures, future Neo4j versions). The READ session provides defence-in-depth in case the keyword list has gaps.

**Why**: Relying solely on the graph driver's READ session creates a single point of failure. A query like `CALL apoc.custom.asProcedure(...)` might bypass keyword checks if only the driver guard is present, or vice versa if only the keyword check is present.

---

## Contract E — Embedding model singleton

**File**: `migration_oracle/mcp/tools/search.py`

The `SentenceTransformer` instance MUST be stored in exactly one module-level variable named `_model`:

```python
from sentence_transformers import SentenceTransformer
from migration_oracle import config

_model: SentenceTransformer | None = None

def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.SENTENCE_TRANSFORMERS_MODEL)
    return _model
```

The following are **prohibited**:
- Instantiating `SentenceTransformer` inside any `@mcp.tool` decorated function or any function called per-request.
- Creating a second module-level variable to hold the instance.
- Using a class-level or function-local cache instead of the module-level `_model`.
- Calling `SentenceTransformer(...)` anywhere other than inside `get_embedding_model()`.

**Why**: SC-007 requires that the model is loaded exactly once per process. Per-call instantiation causes 5–30 seconds of overhead per search request. The exact variable name `_model` is specified so that future refactors and recovery prompts can reliably target this pattern by name.

---

## Contract G — Backward compatibility guarantees

**Scope**: All files under `migration_oracle/mcp/`

The MCP server redesign is **strictly additive**. Three backward compatibility guarantees are non-negotiable:

### (a) 14 existing tool parameter signatures are frozen

The following 14 tools existed before spec 005 and their parameter signatures MUST NOT change:

`analyze_upgrade_path`, `build_recipe_plan`, `resolve_deprecation`, `entity_evolution`, `search_migration_knowledge`, `search_openrewrite_recipes`, `get_graph_schema`, `execute_custom_cypher`, `submit_migration_insight`, `get_community_insights`, `vote_insight`, `verify_insight`, `resolve_paysafe_dependency_by_service_name`, `install_migration_skill`

New parameters (`scope_filter`, `min_severity`) are **additive and optional** with defaults that reproduce the original behaviour when omitted. No existing parameter may be renamed, removed, or have its type narrowed.

**Verification**: Any call that worked before spec 005 must continue to work unchanged.

### (b) AUTOMATED_BY edges are absent in the first release

`AUTOMATED_BY` edges between `MigrationStep` and `OpenRewriteRecipe` will NOT exist in the first deployment. Every tool that reads `AUTOMATED_BY` edges MUST produce correct, non-error output when zero such edges exist:

- `build_recipe_plan`: MUST return an empty auto track and a complete manual track. An empty auto track is NOT an error.
- `analyze_upgrade_path`: MUST return `recipes: []` on every rule. Empty `recipes` is NOT an error.
- Loop III of `framework_migration_main.md`: MUST route ALL steps to the manual track. A manual-only execution is NOT an error.

**Verification**: A test seeded with rules + steps but zero `AUTOMATED_BY` edges must produce clean output for all three of the above.

### (c) `actionStep` on existing MigrationRule nodes remains readable

The `actionStep` property on `MigrationRule` nodes written by pre-redesign population runs is deprecated but NOT removed. Every tool that returns rule data MUST include `action_step` in its output. No tool may drop, discard, or block the `actionStep` value from old nodes.

`build_recipe_plan` MUST use `actionStep` as the fallback card content when no `MigrationStep` nodes are linked to a rule (FR-013).

**Violation example** (do not do this):
```python
# Do NOT filter out rules where actionStep is None — they may still have instructions
rules = [r for r in raw_rules if r["action_step"]]  # VIOLATES CONTRACT G(c)
```

---

## Contract F — No inline os.environ in mcp/ modules

**Scope**: All files under `migration_oracle/mcp/`

No file in `mcp/` may call `os.environ.get(...)`, `os.environ[...]`, or `os.getenv(...)` directly. All environment variables MUST be accessed via attributes of the `migration_oracle.config` module (FR-042).

**Compliant**: `config.NEO4J_URI`, `config.MCP_TRANSPORT`, `config.SENTENCE_TRANSFORMERS_MODEL`

**Violation**: `os.environ.get("NEO4J_URI")` in any `mcp/` file.
