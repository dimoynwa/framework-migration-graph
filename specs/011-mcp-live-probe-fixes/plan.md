# Implementation Plan: MCP Live-Probe Fixes

**Branch**: `011-mcp-live-probe-fixes` | **Date**: 2026-06-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-mcp-live-probe-fixes/spec.md`

## Summary

Fix ten live-probe defects across two layers: (1) MCP server-code fixes — replace the
`stepNotes` map-property write with a `STEP_OUTCOME` relationship, add a `canonical_framework`
helper to `check_version_availability`, fix the `get_steps_for_scope_tier` scope-filter WHERE
clause, fix `list_pipeline_runs` hardcoded `from_version`, and bound the FindIt HTTP call;
(2) ingestion fixes — populate `OpenRewriteRecipe` description/displayName, seed deprecated
classes and `LifecycleAlert` nodes, ensure every `MigrationRule` has a `framework` property
and a `HAS_SCOPE` edge, and persist `fromVersion` at population time.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `neo4j` (Python driver), `httpx`, `requests`, `mcp`, `sentence-transformers`, `packaging`

**Storage**: Neo4j 5 Community Edition (no APOC). Reads via `read_session()`; writes via `write_session()`.

**Testing**: `pytest` + `unittest.mock.patch`. Tests in `tests/mcp/` (unit). No live Neo4j required.

**Target Platform**: Linux container (Docker Compose). macOS for local dev.

**Project Type**: MCP server (Python daemon, tool-based API over Neo4j) + pipeline ingestion scripts.

**Constraints**: No APOC. No new env vars. No new top-level node labels except `LifecycleAlert`.

## Constitution Check

The project constitution file is an unfilled template. Constraints are derived from the codebase.

| Gate | Status | Notes |
|---|---|---|
| No APOC usage | PASS | All Cypher uses Neo4j 5 Community; MERGE on relationships used for STEP_OUTCOME |
| No new node labels beyond LifecycleAlert | PASS | Only `LifecycleAlert` is new; confirmed in spec |
| No duplicate helper functions | PASS | canonical_framework lives in one module (upgrade.py); not copied |
| Security: no credential leakage | PASS | credential_scrub.md contract from spec 010 still applies |
| No extra env vars | PASS | _FINDIT_TIMEOUT_SECONDS is module-level constant; no new os.environ keys |
| Step atomicity: completedSteps preserved | PASS | FR-003: array advancement + STEP_OUTCOME rel written in same session |

## Project Structure

### Documentation (this feature)

```text
specs/011-mcp-live-probe-fixes/
├── plan.md              ← this file
├── spec.md              ← feature specification
├── research.md          ← existing spike findings
├── data-model.md        ← Phase 1 output (new and updated schemas)
├── contracts/
│   ├── canonical_framework.md
│   ├── step_outcome_relationship.md
│   └── default_breaking_scope.md
└── tasks.md             ← Phase 2 (/speckit-tasks — not yet generated)
```

### Source Code — Modified Files

```text
migration_oracle/
├── mcp/
│   ├── tools/
│   │   ├── upgrade.py         # canonical_framework helper; check_version_availability uses .display/.slug
│   │   ├── context.py         # update_step_status: step_not_on_path guard, STEP_OUTCOME write
│   │   └── artifacts.py       # list_pipeline_runs: use stored fromVersion + filename fallback
│   └── graph/
│       └── queries/
│           ├── context.py     # remove _READ_STEP_NOTES/_WRITE_STEP_NOTES; add _VALIDATE_STEP_ON_PATH,
│           │                  # _MERGE_STEP_OUTCOME_REL; fix _GET_STEPS_FOR_SCOPE_TIER WITH+WHERE
│           ├── upgrade.py     # _ANALYZE_UPGRADE_PATH: add title, fix reason←statement; _CHECK_VERSION_IN_GRAPH: use $display
│           └── artifacts.py   # _LIST_PIPELINE_RUNS: return v.fromVersion; add filename fallback
├── paysafe/
│   └── resolver.py            # add _FINDIT_TIMEOUT_SECONDS; wrap findit.lookup() with total timeout
│   └── findit.py              # add optional timeout parameter to _fetch_services/_get_services
└── pipeline/
    ├── populator.py           # set rule.framework; default BreakingScope; seed deprecated classes;
    │                          # seed LifecycleAlert; set description/displayName on recipe stubs
    └── seeds/
        ├── deprecated_classes.py   # NEW — curated deprecated-class seed data
        └── lifecycle_alerts.py     # NEW — curated lifecycle alert seed data

migration_oracle/
└── graph/
    └── queries/
        └── pipeline.py        # upsert_version_artifact_paths: add fromVersion parameter and SET

tests/
└── mcp/
    ├── test_update_step_status.py          # NEW — Issue 1 (FR-001–FR-004)
    ├── test_check_version_availability.py  # NEW — Issues 3 & 4 (FR-005–FR-008)
    ├── test_get_steps_for_scope_tier.py    # NEW — Issue 7 (FR-018–FR-019)
    ├── test_list_pipeline_runs.py          # NEW — Issue 8 (FR-020–FR-022)
    ├── test_lifecycle_alert.py             # NEW — Issue 9 (FR-023–FR-024)
    ├── test_analyze_upgrade_path.py        # NEW — Issue 6 (FR-015–FR-017): title/reason/severity
    ├── test_search_openrewrite_recipes.py  # NEW — Issue 2 (FR-009–FR-012): description populated
    └── test_resolve_deprecation.py        # NEW — Issue 5 (FR-013–FR-014): deprecated class seed
```

**Structure Decision**: Seed data lives in `migration_oracle/pipeline/seeds/` as importable Python
modules (not inline in populator.py) so they can be independently tested and version-controlled.

## Phase 0 — Research Findings

All facts are confirmed by code inspection; no open questions remain.

| Question | Confirmed Answer |
|---|---|
| `HAS_SCOPE` vs `SCOPED_TO` | `HAS_SCOPE` is authoritative (confirmed: context.py lines 68, 131; upgrade.py lines 45, 114). SCOPED_TO in ISSUES.md was a probe misidentification. |
| stepNotes already in codebase? | Yes — `_READ_STEP_NOTES` (~line 109) and `_WRITE_STEP_NOTES` (~line 114) exist in context.py; `record_step_outcome` calls both. This is the live bug. |
| canonical_framework scope | `check_version_availability` only. Other tools (`analyze_upgrade_path`, `build_recipe_plan`, etc.) already accept `"Spring Boot"` and pass it unchanged to graph — correct. |
| `_GET_STEPS_FOR_SCOPE_TIER` bug | The `$scope` parameter is not passed to the Cypher at all; `severity_meets_threshold(None, "medium")` returns False, dropping scopeless steps. |
| `from_version` in `list_pipeline_runs` | Hardcoded to `""` in artifacts.py line 29. `_LIST_PIPELINE_RUNS` query does not project `v.fromVersion`. |
| FindIt timeout | `findit.py` has `_HTTP_TIMEOUT_SECONDS=10` per request but `_RETRIES=2` with `_BACKOFF_SECONDS=[1.0, 3.0]`, giving worst-case ~34s total. The probe client's 5s SSE timeout fires first. Fix: add a total wall-clock bound in `resolver.py`. |
| OpenRewriteRecipe population | `populator.py` creates stub nodes via `MERGE (e:OpenRewriteRecipe {recipeId: $stub_id})` with no `description`/`displayName`. A dedicated recipe populator/loader is missing. |
| `fromVersion` persisted? | `upsert_version_artifact_paths` does not set `fromVersion` on the Version node. |
| Artifact filename pattern | `_paths.py:artifact_key` returns `<framework>-<from>-to-<to>`; the filtered file is `<...>-changes_filtered.md`. |

## Phase 1 — Design Detail

### Task 0 — Remove stepNotes map-property write (FR-001) ⚠️ FIRST TASK

**Why first**: The `_READ_STEP_NOTES`/`_WRITE_STEP_NOTES` code is the live bug causing `Neo4j TypeError`.
It must be removed before adding the `STEP_OUTCOME` relationship so no code path can trigger the error
during development.

**In `migration_oracle/mcp/graph/queries/context.py`**:
- Delete the `_READ_STEP_NOTES` constant (lines ~109–112).
- Delete the `_WRITE_STEP_NOTES` constant (lines ~113–117).
- In `record_step_outcome`: remove the `if reason:` block that calls both queries.

**In `migration_oracle/mcp/tools/context.py`**:
- Remove the docstring line: "The 'reason' parameter is persisted in ctx.stepNotes when non-empty."

---

### FR-001–FR-004 — update_step_status: STEP_OUTCOME relationship

**New Cypher in `migration_oracle/mcp/graph/queries/context.py`**:

```cypher
-- _VALIDATE_STEP_ON_PATH
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion > from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
WHERE elementId(s) = $step_id
RETURN count(s) > 0 AS on_path
```

```cypher
-- _MERGE_STEP_OUTCOME_REL
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (s:MigrationStep) WHERE elementId(s) = $step_id
MERGE (ctx)-[rel:STEP_OUTCOME]->(s)
SET rel.status   = $status,
    rel.reason   = $reason,
    rel.updatedAt = datetime()
RETURN elementId(rel) AS rel_id
```

**Updated `record_step_outcome` in `context.py` (query layer)**:

```python
def record_step_outcome(*, context_id, step_id, outcome, reason=""):
    # 1. Validate step is on path (FR-004)
    with read_session() as session:
        val = session.run(_VALIDATE_STEP_ON_PATH,
                          context_id=context_id, step_id=step_id).single()
    if not (val and val["on_path"]):
        return {"on_path": False}   # signals error to tool layer

    # 2. Advance completedSteps/skippedSteps/failedSteps (FR-003) AND write STEP_OUTCOME rel (FR-002)
    with write_session() as session:
        record = session.run(_RECORD_STEP_OUTCOME,
                             context_id=context_id, step_id=step_id,
                             outcome=outcome).single()
        session.run(_MERGE_STEP_OUTCOME_REL,
                    context_id=context_id, step_id=step_id,
                    status=outcome,
                    reason=reason or None)  # null when not supplied
    if record is None:
        raise ValueError(f"Context not found: {context_id}")
    return dict(record)
```

**Updated `update_step_status` in tools/context.py** — add step_not_on_path guard before calling query:

```python
result = context_queries.record_step_outcome(...)
if not result.get("on_path", True):   # on_path=False signals validation failure
    return {
        "status": "error",
        "error_code": "step_not_on_path",
        "step_id": step_id,
        "hint": f"Step {step_id} is not part of migration path for context {context_id}",
    }
```

Note: `{"on_path": False}` is the sentinel returned by `record_step_outcome` when validation fails.
Normal success returns a dict without `on_path`, so `result.get("on_path", True)` → `True` for success.

---

### FR-005–FR-008 — canonical_framework helper in upgrade.py

**Location**: module-level in `migration_oracle/mcp/tools/upgrade.py`. No new file.

```python
from typing import NamedTuple
import re

class _CanonicalFramework(NamedTuple):
    display: str   # e.g. "Spring Boot"  — used for graph queries
    slug: str      # e.g. "spring-boot"  — used for Maven coordinate lookup

_FRAMEWORK_ALIASES: dict[str, _CanonicalFramework] = {
    # keys: normalised (lowercase, no spaces/hyphens)
    "springboot": _CanonicalFramework(display="Spring Boot", slug="spring-boot"),
}

def _normalise_key(framework: str) -> str:
    return re.sub(r"[\s\-_]+", "", framework).lower()

def canonical_framework(framework: str) -> _CanonicalFramework:
    """Resolve any accepted framework spelling to the canonical record.

    Raises a structured dict (not an exception) when the framework is unknown.
    Call sites must check the return type: NamedTuple on success, dict on error.
    """
    cf = _FRAMEWORK_ALIASES.get(_normalise_key(framework))
    if cf is None:
        supported = sorted({v.display for v in _FRAMEWORK_ALIASES.values()})
        return {
            "status": "error",
            "error_code": "unsupported_framework",
            "exists_in_graph": False,
            "ga_available": False,
            "latest_patch": None,
            "hint": f"Unknown framework; supported: {', '.join(supported)}",
        }
    return cf
```

**Updated `_FRAMEWORK_MAVEN_COORDS`**: The existing dict uses `slug` → `(groupId, artifactId)`.
Rename to `_MAVEN_COORDS` and key by slug:

```python
_MAVEN_COORDS: dict[str, tuple[str, str]] = {
    "spring-boot": ("org.springframework.boot", "spring-boot"),
}
```

**Updated `check_version_availability`**:
```python
cf = canonical_framework(framework)
if isinstance(cf, dict):        # error sentinel
    return cf                   # no network call (FR-008)
normalised = to_minor_zero(version)

# Graph lookup uses .display (FR-006)
with read_session() as session:
    record = session.run(_CHECK_VERSION_IN_GRAPH,
                         framework=cf.display, version=normalised).single()
exists_in_graph = bool(record["found"]) if record else False

# Maven lookup uses .slug (FR-007)
coords = _MAVEN_COORDS.get(cf.slug)
if coords is None:
    # display name known but no Maven coords configured yet
    return {"status": "ok", "exists_in_graph": exists_in_graph,
            "ga_available": False, "latest_patch": None,
            "hint": f"No Maven coordinates configured for {cf.display}"}
# ... rest of Maven Central probe (unchanged from spec 010 FR-015–FR-020)
```

**`_CHECK_VERSION_IN_GRAPH`** query does not change — it already uses `$framework` as stored in the
graph. The fix is that it now receives `cf.display` ("Spring Boot") instead of the raw slug.

---

### FR-009–FR-012 — OpenRewriteRecipe population (ingestion-only)

**Problem**: `populator.py` creates `OpenRewriteRecipe` stub nodes with only `recipeId`
(`stub_id = f"stub:{rule_id}:{step.index}"`). No `description` or `displayName` is ever written.
The fulltext index exists but indexes empty/absent properties, so all searches return 0 hits.

**Confirmed data source**: No external OpenRewrite recipe catalog file exists in the repo. The
`AUTOMATED_BY` edges also have no real recipe metadata (`verifiedBy` is null on all stubs). The
step `summary` text IS in scope at stub-creation time in `_write_step` — it describes exactly
what the recipe would automate. This is the data to use.

**Fix in `migration_oracle/pipeline/populator.py`** — `_write_step` stub-creation block:

```cypher
MERGE (s)-[ab:AUTOMATED_BY]->(e:OpenRewriteRecipe {recipeId: $stub_id})
ON CREATE SET
  ab.auto = false,
  ab.confidence = 0.0,
  ab.method = 'deterministic',
  ab.missingRequiredParams = [],
  e.description  = $step_summary,     ← ADD: step summary as recipe description
  e.displayName  = $step_summary      ← ADD: same value for displayName (fulltext index covers both)
ON MATCH SET
  ab.auto = CASE WHEN e.verifiedBy IS NULL THEN false ELSE ab.auto END,
  ...
  e.description  = coalesce(e.description, $step_summary),   ← ADD: backfill if absent
  e.displayName  = coalesce(e.displayName, $step_summary)    ← ADD: backfill if absent
```

Pass `step_summary=step.summary` as a new parameter to the Cypher invocation.

The step `summary` is already an in-scope local variable (`step.summary`) in `_write_step`,
so no additional queries or data structures are needed.

**Validation gate** (run post-`populate_graph`):
```cypher
MATCH (r:OpenRewriteRecipe) RETURN count(r), count(r.description), count(r.displayName)
```
Must yield three equal counts. Log a warning (not an error) if counts differ; the ingestion
pipeline is not expected to crash on missing recipe metadata.

**ensure_indexes()** is already called on line 118 of `populator.py` — no change needed.

---

### FR-013–FR-014 — Deprecated-class seed (ingestion)

**New file**: `migration_oracle/pipeline/seeds/deprecated_classes.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class _DeprecatedClass:
    name: str
    framework: str
    deprecated_since_version: str   # e.g. "3.0.0"
    replacement: str | None         # None when no direct replacement

SPRING_BOOT_3X_DEPRECATED: list[_DeprecatedClass] = [
    _DeprecatedClass("RestTemplate",                 "Spring Boot", "3.0.0", "RestClient"),
    _DeprecatedClass("WebSecurityConfigurerAdapter", "Spring Boot", "3.0.0", None),
    _DeprecatedClass("WebMvcConfigurerAdapter",      "Spring Boot", "3.0.0", None),
    _DeprecatedClass("WebMvcConfigurer",             "Spring Boot", "3.0.0", None),
    _DeprecatedClass("EnvironmentPostProcessor",     "Spring Boot", "3.0.0", None),
]
```

**Seeding Cypher** (called in `populate_graph` or a dedicated `seed_deprecated_classes` function):

```cypher
MERGE (c:Class {name: $name, framework: $framework})
ON CREATE SET c.framework = $framework
WITH c
MATCH (v:Version {framework: $framework, version: $deprecated_since})
MERGE (c)-[:DEPRECATED_IN]->(v)
```

For RestTemplate (has replacement):
```cypher
WITH c
MERGE (r:Class {name: $replacement, framework: $framework})
MERGE (c)-[:REPLACED_BY]->(r)
```

All via MERGE for idempotency (FR-014).

---

### FR-015–FR-017 — analyze_upgrade_path + MigrationRule metadata

**Query fix in `migration_oracle/mcp/graph/queries/upgrade.py`**:

In the `collect(DISTINCT {...}) AS raw_rules` block, add `title: rule.title` AND change the
`reason` mapping from `rule.reason` (which is null on all nodes in the graph) to `rule.statement`
(which has content):

```cypher
WITH v, raw_lifecycle_events, collect(DISTINCT {
    rule_id: elementId(rule),
    rule_type: labels(rule)[0],
    title: rule.title,                                    ← ADD
    statement: rule.statement,
    action_step: rule.actionStep,
    source_url: rule.sourceUrl,
    reason: coalesce(rule.statement, rule.reason),        ← CHANGE (was rule.reason, always null)
    solution: rule.solution,
    change_type: rule.changeType,
    reason_type: rule.reasonType,
    entity_classification: rule.entityClassification,
    ...
    scopes: [x IN scopes WHERE x.scope IS NOT NULL],
    ...
}) AS raw_rules
```

> **Why `coalesce(rule.statement, rule.reason)`**: The graph stores the human-readable explanation
> in `rule.statement` (populated by the ingestion pipeline via `reason` parameter). `rule.reason`
> is a separate, currently-null property. Using `coalesce` preserves forward compatibility if
> `rule.reason` is ever populated independently, while ensuring non-null output today (SC-005
> requires non-null `reason`).

**Tool layer fix in `migration_oracle/mcp/tools/upgrade.py`** — post-process each rule to extract
top-level `severity` from the `scopes` list (the first non-null severity, if any):

```python
def _flatten_rules(rows: list[dict]) -> list[dict]:
    rules = []
    for row in rows:
        for rule in row.get("rules") or []:
            # Extract top-level severity from first non-null scope entry
            scopes = rule.get("scopes") or []
            rule["severity"] = next(
                (s["severity"] for s in scopes if s.get("severity")), None
            )
            rules.append(rule)
    return rules
```

**Ingestion fix** — `framework` property on `MigrationRule`:

In `populator.py` → `_write_entity`, add `rule.framework = $framework` to the `ON CREATE SET` and
`ON MATCH SET` blocks:
```cypher
MERGE (rule:MigrationRule {ruleId: $rule_id_key})
ON CREATE SET
  rule.framework = $framework,
  rule.statement = $reason,
  rule.title     = $title,
  ...
ON MATCH SET
  rule.framework = coalesce(rule.framework, $framework),
  ...
```

**Default BreakingScope** (FR-017) — see [contracts/default_breaking_scope.md](contracts/default_breaking_scope.md).
After the existing `_write_entity` scope-linking block, add:
```cypher
-- For rules where no BreakingScope was linked:
MATCH (rule:MigrationRule {ruleId: $rule_id_key})
WHERE NOT (rule)-[:HAS_SCOPE]->(:BreakingScope)
MERGE (bs:BreakingScope {scope: "general", severity: "low"})
MERGE (rule)-[:HAS_SCOPE]->(bs)
```

---

### FR-018–FR-019 — get_steps_for_scope_tier Cypher + Python fix

**Two bugs in `_GET_STEPS_FOR_SCOPE_TIER`**:

1. The `$scope` parameter is never passed to the Cypher query (no WHERE on `bs.scope`). All steps
   are returned regardless of scope, then filtered only by severity — which drops scopeless steps.
2. The Python post-filter uses `row.get("entity_name")` as a guard, dropping steps that have no
   matched scanned entity.

**Cypher fix** — add scope filter respecting the FR-018 semantics (match OR scopeless):

```cypher
_GET_STEPS_FOR_SCOPE_TIER = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion > from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
WITH ctx, v, r, s, bs
WHERE bs IS NULL OR bs.scope = $scope
OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE e.name IN ctx.scannedEntities
RETURN DISTINCT
       e.name AS entity_name,
       labels(e)[0] AS entity_type,
       elementId(s) AS step_id,
       elementId(r) AS rule_id,
       s.summary AS summary,
       bs.scope AS scope,
       bs.severity AS severity
"""
```

> **Why the explicit `WITH` is required**: `WHERE` that immediately follows `OPTIONAL MATCH` is
> interpreted as an OPTIONAL MATCH predicate. When `bs.scope = 'API'` but `$scope = 'build'`, the
> predicate is false, the optional match "fails", and Cypher sets `bs = null` — but the row is
> **not dropped**. The rule returns as a falsely scopeless row, violating the FR-018 contract that
> only genuinely scopeless rules may appear with `scope: null`. Adding `WITH ctx, v, r, s, bs`
> before the `WHERE` elevates it to a row-level filter: rows where `bs.scope ≠ $scope AND bs IS NOT
> NULL` are eliminated from the result set entirely.

**Python fix** — pass `scope` to Cypher; relax the entity_name guard; allow NULL severity through:

```python
def get_steps_for_scope_tier(*, context_id, scope, min_severity):
    with read_session() as session:
        rows = [dict(row) for row in session.run(
            _GET_STEPS_FOR_SCOPE_TIER,
            context_id=context_id,
            scope=scope,           # ← was missing
        )]
    return [
        row for row in rows
        if row.get("step_id")      # must have a valid step
        and (
            row.get("severity") is None          # scopeless steps always pass (FR-018)
            or severity_meets_threshold(row.get("severity"), min_severity)
        )
    ]
```

---

### FR-020–FR-022 — list_pipeline_runs: from_version fix

**Query fix in `migration_oracle/mcp/graph/queries/artifacts.py`**:

```cypher
_LIST_PIPELINE_RUNS = """
MATCH (v:Version) WHERE v.rawMdPath IS NOT NULL
RETURN v.framework      AS framework,
       v.version        AS version,
       v.fromVersion    AS from_version,     ← ADD
       v.rawMdPath      AS raw_md_path,
       v.filteredMdPath AS filtered_md_path,
       v.entitiesJsonPath AS entities_json_path
ORDER BY v.framework, v.sortableVersion
"""
```

**Tool fix in `migration_oracle/mcp/tools/artifacts.py`** — replace the hardcoded `""` with
stored value + filename-parse fallback (FR-022):

```python
import re
_FROM_VERSION_RE = re.compile(r"^.+-to-[^/\\]+-changes")  # anchors on -to- and -changes token

def _parse_from_version(raw_md_path: str) -> str:
    """Extract from_version from artifact filename pattern <fw>-<from>-to-<to>-changes[...].md."""
    filename = Path(raw_md_path).stem if raw_md_path else ""
    # filename looks like: spring-boot-3.5.0-to-4.0.0-changes_filtered
    # We want the segment between the framework prefix and -to-
    m = re.search(r"-to-([^-]+(?:\.\d+)*)-changes", filename)
    if not m:
        return ""
    # The from_version is the segment immediately before -to-<to>
    before_to = filename[:m.start()]       # e.g. "spring-boot-3.5.0"
    # from_version is the last version-looking segment
    v = re.search(r"(\d+\.\d+\.\d+)$", before_to)
    return v.group(1) if v else ""

records = [
    {
        "framework":        row.get("framework") or "",
        "from_version":     row.get("from_version") or _parse_from_version(row.get("raw_md_path") or ""),
        "to_version":       row.get("version") or "",
        "raw_md_path":      row.get("raw_md_path") or "",
        "filtered_md_path": row.get("filtered_md_path"),
        "entities_json_path": row.get("entities_json_path"),
    }
    for row in runs
]
```

**Ingestion fix** — `upsert_version_artifact_paths` in `migration_oracle/graph/queries/pipeline.py`:

Add `from_version: str` parameter:
```python
def upsert_version_artifact_paths(*, framework, version, from_version,
                                   raw_md_path, filtered_md_path, entities_json_path):
    merge_version(...)
    query = """
    MATCH (v:Version {framework: $framework, version: $version})
    SET v.rawMdPath        = $raw_md_path,
        v.filteredMdPath   = $filtered_md_path,
        v.entitiesJsonPath = $entities_json_path,
        v.fromVersion      = $from_version     ← ADD
    """
```

Update the call site in `populator.py` to pass `from_version`:
```python
pipeline_queries.upsert_version_artifact_paths(
    framework=framework_display,
    version=to_version,
    from_version=from_version,       # ← ADD (already available as a populate_graph parameter)
    raw_md_path=...,
    ...
)
```

---

### FR-023–FR-024 — LifecycleAlert seeding (ingestion)

**New file**: `migration_oracle/pipeline/seeds/lifecycle_alerts.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class _LifecycleAlert:
    framework: str
    version: str          # the Version node this alert is linked to
    message: str
    category: str         # "security" | "api" | "config" | "dependency" | "other"
    phase: str            # "pre-migration" | "migration" | "post-migration"

SPRING_BOOT_4X_ALERTS: list[_LifecycleAlert] = [
    _LifecycleAlert(
        framework="Spring Boot", version="4.0.0",
        message="Spring Security 7 changes the default CSRF policy — review all state-changing endpoints.",
        category="security", phase="pre-migration",
    ),
    _LifecycleAlert(
        framework="Spring Boot", version="4.0.0",
        message="Jakarta EE 10 namespace migration required (javax.* → jakarta.*) before compilation.",
        category="api", phase="pre-migration",
    ),
    _LifecycleAlert(
        framework="Spring Boot", version="4.0.0",
        message="Hibernate 6 removes deprecated HQL syntax — run schema validation after migration.",
        category="dependency", phase="migration",
    ),
    _LifecycleAlert(
        framework="Spring Boot", version="4.0.0",
        message="Spring Boot Actuator endpoints default to /actuator — update monitoring configs.",
        category="config", phase="post-migration",
    ),
]
```

**Seeding Cypher** in populator.py (dedicated `seed_lifecycle_alerts` function):
```cypher
MATCH (v:Version {framework: $framework, version: $version})
MERGE (v)-[:HAS_LIFECYCLE_ALERT]->(a:LifecycleAlert {message: $message})
ON CREATE SET a.category = $category,
              a.phase    = $phase
ON MATCH SET  a.category = $category,
              a.phase    = $phase
```

---

### FR-025–FR-026 — FindIt timeout (resolver.py)

**Problem**: `findit.py` has `_HTTP_TIMEOUT_SECONDS=10` per request with `_RETRIES=2` and
`_BACKOFF_SECONDS=[1.0, 3.0]`, giving worst-case ~34s total. The probe's 5s SSE timeout fires first.

**Fix in `migration_oracle/paysafe/resolver.py`**:

Add module-level constant:
```python
_FINDIT_TIMEOUT_SECONDS = 10
```

Wrap the `findit.lookup()` call with a `concurrent.futures.ThreadPoolExecutor` total-time bound:

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout

# Step 3: FindIt lookup — bounded by _FINDIT_TIMEOUT_SECONDS total wall-clock time
try:
    with ThreadPoolExecutor(max_workers=1) as _pool:
        _future = _pool.submit(findit.lookup, service_name)
        try:
            findit_record = _future.result(timeout=_FINDIT_TIMEOUT_SECONDS)
        except _FuturesTimeout:
            return _build_error(
                "findit_timeout",
                f"FindIt lookup for {service_name!r} timed out after {_FINDIT_TIMEOUT_SECONDS}s.",
                recoverable=True,
                actionable_hint="Retry the request or check network connectivity to FindIt.",
                details={"service_name": service_name},
            )
except _FindItError as exc:
    # existing error handling unchanged ...
```

This preserves all existing `_FindItError` handling paths (lines 122–151) while adding a hard
wall-clock ceiling independent of the per-request timeout in `findit.py`.

**No changes to `findit.py`**: the per-request timeout and retry logic there remain as-is. The
resolver-level total timeout is the correct place for a service-level bound.

---

## Cross-Spec Inheritance

- **spec 010 FR-015–FR-020** for `check_version_availability` (Maven probe logic, `latest_patch`
  computation, network-error handling) remain in force unchanged. FR-005–FR-008 from this spec amend
  only the framework-canonicalization and graph-lookup behaviour.
- **`credential_scrub.md`** (spec 010 FR-007): applies to any new network-error path introduced here,
  including the FindIt timeout error returned by `_build_error`.
- **`to_minor_zero_import.md`** (spec 010 FR-001): still authoritative; `to_minor_zero` continues to
  be imported from `upgrade.py` by `context.py`.

## repos= open question (carried from spec 010 §FR-008)

The Artifactory fallback from spec 010 uses `…?a={service_name}` without a `repos=` parameter.
If the Paysafe Artifactory instance requires `repos=` to scope results, add `ARTIFACTORY_REPO`
as an optional env var and append `&repos={ARTIFACTORY_REPO}` when set. Verify against the actual
instance before closing spec 010's Artifactory tests.

## Test Mock State

All tests use `unittest.mock.patch`. No live Neo4j instance required.

### tests/mcp/test_update_step_status.py

| Test | Mock target | Mock inputs | Expected |
|---|---|---|---|
| `test_step_outcome_rel_created` | `context_queries.record_step_outcome` | valid context_id + step_id on path | returns success; MERGE_STEP_OUTCOME_REL called with `status`, `reason`, `updatedAt` |
| `test_step_not_on_path_returns_error` | `context_queries.record_step_outcome` returns `{"on_path": False}` | step_id not on migration path | returns `{error_code: "step_not_on_path", step_id: ...}` |
| `test_no_map_property_written` | `context_queries.record_step_outcome` | any call with reason="foo" | `_WRITE_STEP_NOTES` is never called; `_READ_STEP_NOTES` is never called |
| `test_reason_null_when_not_supplied` | `_MERGE_STEP_OUTCOME_REL` | no `reason` arg | `reason=None` on the relationship |
| `test_completed_steps_preserved` | `_RECORD_STEP_OUTCOME` | `outcome="completed"` | `_RECORD_STEP_OUTCOME` still called; `completedSteps` advancement in Cypher confirmed |

### tests/mcp/test_check_version_availability.py

| Test | Mock inputs | Expected |
|---|---|---|
| `test_spring_boot_display_form` | `framework="Spring Boot"`, graph returns `found=True` | `exists_in_graph=True`; no unsupported_framework error |
| `test_spring_boot_slug_form` | `framework="spring-boot"`, same graph mock | same result |
| `test_spring_boot_no_space` | `framework="springboot"` | resolves to same canonical |
| `test_graph_query_uses_display_form` | inspect Cypher parameters | `framework` param == `"Spring Boot"` (not `"spring-boot"`) |
| `test_maven_uses_slug` | inspect Maven URL | contains `spring-boot` artifact id |
| `test_unsupported_framework_no_network_call` | `framework="angular"` | returns `unsupported_framework`; no `requests.get` called |

### tests/mcp/test_get_steps_for_scope_tier.py

| Test | Mock inputs | Expected |
|---|---|---|
| `test_matching_scope_returned` | row `{step_id:"s1", scope:"build", severity:"high"}` | row in result with `scope:"build"` |
| `test_scopeless_step_returned_as_null` | row `{step_id:"s2", scope:None, severity:None}` | row in result with `scope:null`; NOT dropped |
| `test_mismatched_scope_excluded` | row `{step_id:"s3", scope:"API", severity:"medium"}`, requested scope `"build"` | row NOT in result |
| `test_scope_param_passed_to_cypher` | any call | `$scope` is in Cypher params |
| `test_total_gt_zero_when_pending` | 3 rows returned from query | `total > 0` |

### tests/mcp/test_list_pipeline_runs.py

| Test | Mock inputs | Expected |
|---|---|---|
| `test_stored_from_version_used` | query returns `{from_version:"3.5.0", ...}` | `from_version:"3.5.0"` in output |
| `test_filename_fallback` | `from_version=None`, `raw_md_path="spring-boot-3.5.0-to-4.0.0-changes_filtered.md"` | `from_version:"3.5.0"` parsed |
| `test_graceful_empty_when_no_source` | `from_version=None`, `raw_md_path="bad-name.md"` | `from_version:""` |
| `test_filtered_md_suffix_handled` | path ends in `_filtered.md` | parse still works |

### tests/mcp/test_lifecycle_alert.py

| Test | Mock inputs | Expected |
|---|---|---|
| `test_alerts_returned_when_include_lifecycle_true` | `LifecycleAlert` node with `message`, `category`, `phase` | `lifecycle_alerts` non-empty |
| `test_empty_when_include_lifecycle_false` | same node in graph | `lifecycle_alerts == []` |
| `test_alert_properties_projected` | node in mock | each alert has `message`, `category`, `phase` |
| `test_idempotent_merge` | seeder called twice | count query returns same count both times |

### tests/mcp/test_analyze_upgrade_path.py (Issue 6 — SC-005)

| Test | Mock inputs | Expected |
|---|---|---|
| `test_title_projected` | row with `{title:"Remove X", changeType:"removal", statement:"Foo was removed."}` | `rule["title"] == "Remove X"` |
| `test_reason_from_statement` | row with `statement="Foo was removed.", reason=None` | `rule["reason"] == "Foo was removed."` (not null) |
| `test_reason_fallback_when_both_null` | `statement=None, reason=None` | `rule["reason"]` is `None` (no crash) |
| `test_severity_extracted_from_scopes` | row with `scopes=[{scope:"build", severity:"high"}]` | `rule["severity"] == "high"` |
| `test_severity_null_for_scopeless` | row with `scopes=[]` | `rule["severity"]` is `None` |
| `test_all_three_fields_non_null` | rule with all data present | `title`, `reason`, `severity` all non-null (SC-005) |

### tests/mcp/test_search_openrewrite_recipes.py (Issue 2 — SC-002)

| Test | Mock inputs | Expected |
|---|---|---|
| `test_description_set_on_stub` | `step.summary="Replace @MockBean with @MockitoBean"`, `step.automatable=True` | Cypher called with `step_summary=step.summary`; `e.description` and `e.displayName` set |
| `test_backfill_on_match` | existing node with `description=None` | `coalesce(e.description, $step_summary)` applied; no blank description remains |
| `test_search_returns_hits` | fulltext index mocked to return 1 node with `description="Replace @MockBean"` | `hits` list is non-empty |
| `test_zero_hits_when_description_absent` | fulltext index mocked with nodes lacking `description` | `hits` is empty (expected pre-fix state, confirms the diagnosis) |

### tests/mcp/test_resolve_deprecation.py (Issue 5 — SC-004)

| Test | Mock inputs | Expected |
|---|---|---|
| `test_rest_template_found` | seed applied; query mock returns `Class {name:"RestTemplate"}` | `status != "not_found"`; deprecating version returned |
| `test_rest_template_replaced_by_rest_client` | seed applied | `REPLACED_BY` edge to `RestClient` present |
| `test_web_mvc_configurer_found` | seed applied | `status != "not_found"` |
| `test_unknown_class_not_found` | class not in seed | `status == "not_found"` (existing behaviour preserved) |
| `test_seed_idempotent` | seeder called twice | second call returns same count (no duplicates) |

## Complexity Tracking

No constitution violations. All changes are targeted patches; no new abstractions, no new external
services beyond those already in spec 010.
