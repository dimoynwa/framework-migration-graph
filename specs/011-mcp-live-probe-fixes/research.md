# Research — Spec 011: MCP Live-Probe Fixes

Phase 0 research artifact. Resolves the technical unknowns that gate the fixes for the ten
defects found by the `2026-06-11` live probe (`ISSUES.md`). Each spike below corresponds to a
decision that is *not* obvious from the code and would otherwise force a guess during
implementation.

The probe was run against the partially-implemented `010-mcp-defect-fixes` branch. Two of its
findings **contradict 010's own design** and supersede it — those are called out explicitly.

---

## Spike 1 — How to persist per-step outcomes without a Neo4j map property (Issue 1)

### Decision

Persist each step outcome as a **relationship**, not a node property:

```
(ctx:MigrationContext)-[:STEP_OUTCOME {status: $status, reason: $reason, updatedAt: $ts}]->(s:MigrationStep)
```

`MERGE` on the `(ctx)-[:STEP_OUTCOME]->(s)` pair so a repeated `update_step_status` call for the
same step updates the existing relationship rather than creating duplicates.

### Rationale

The live probe proved the current implementation throws on **every** call:

```
Neo.ClientError.Statement.TypeError
Property values can only be of primitive types or arrays thereof. Encountered:
Map{4:c474cace-...:1795 -> String("Already handled in migration")}.
```

The current code (`migration_oracle/mcp/graph/queries/context.py`) does
`current_notes[step_id] = reason` then `SET ctx.stepNotes = $step_notes`, passing a Python dict.
Neo4j stores node/relationship properties as primitives or arrays-of-primitives **only** — a map
value is rejected at write time. This is the same approach spec 010 mandated in its FR-005
("`stepNotes` is a Neo4j map property"), so **010's FR-005 is the defect**; 011 supersedes it.

A relationship is the natural model: the reason and status belong to the *edge* between a context
and a step, not to the context node. It is also directly queryable (`MATCH (ctx)-[o:STEP_OUTCOME]->(s)`)
when reconstructing session state on a later run, which a serialised-string property would not be.

### Alternatives Considered

- **JSON-serialised string property** (`ctx.stepNotesJson = json.dumps(map)`) — works and is a
  one-line change, but the notes become opaque to Cypher; you cannot query "which steps were
  skipped and why" without deserialising in Python. Rejected as a regression in queryability.
- **Two parallel arrays** (`ctx.outcomeStepIds[]`, `ctx.outcomeReasons[]`) — primitive arrays are
  legal, but keeping two arrays index-aligned under updates is fragile. Rejected.
- **APOC `apoc.create.setRelProperty` / `apoc.map.*`** — APOC is **not installed** (Neo4j Community,
  confirmed in spec 010 research Spike 3). Not available.

### Implementation Notes

`completedSteps` (a String array on the context) already advances correctly today — the probe
confirmed the step IS appended before the failing SET. Keep that array; only the reason/status
storage moves to the relationship. The `update_step_status` Cypher must therefore: (1) append to
`completedSteps` as today, and (2) `MERGE` the `STEP_OUTCOME` relationship. No node-property map
write remains anywhere in the tool.

---

## Spike 2 — Why `search_openrewrite_recipes` returns 0 hits despite 333 nodes (Issue 2)

### Decision

The fulltext index DDL exists; the gap is in the **data**, not the search code. Two conditions must
hold and currently do not:

1. `OpenRewriteRecipe` nodes must carry populated `description` and `displayName` properties (the
   two fields the `openrewrite_recipe_description` fulltext index covers).
2. The vector index `openrewrite_recipe_vector` must have embeddings written for each recipe node
   if hybrid search is to contribute vector hits.

The fix is in the **ingestion pipeline**: it must create real recipe nodes with these properties
(and embeddings), and `ensure_indexes()` must run before/at populate time so the fulltext +
vector indexes are present and populated.

### Rationale

`migration_oracle/graph/indexes.py:28-29` already declares:

```cypher
CREATE FULLTEXT INDEX openrewrite_recipe_description IF NOT EXISTS
FOR (r:OpenRewriteRecipe) ON EACH [r.description, r.displayName]
```

and the search path (`queries/search.py`) correctly calls
`db.index.fulltext.queryNodes("openrewrite_recipe_description", ...)`. So the search query and the
index definition agree. The probe found 333 nodes but 0 hits — that pattern means the indexed
properties are empty/absent on the nodes. The populator only ever creates **stub** recipe nodes
(`stub_id=f"stub:{rule_id}:{step.index}"` in `_write_step()`), which do not carry a real
`description`/`displayName`, so the fulltext index has nothing to match. A fulltext index over
null/absent properties returns no documents.

### Alternatives Considered

- **Rebuild the index on different properties** — unnecessary; the index targets the right
  properties. The properties are simply unpopulated. Rejected.
- **Fall back to a substring `CONTAINS` scan when fulltext returns 0** — masks the data gap and is
  O(n) over 333 nodes per query. Rejected as a band-aid; the data must be fixed.

### Implementation Notes

Validation query to confirm the diagnosis before/after the fix:

```cypher
MATCH (r:OpenRewriteRecipe)
RETURN count(r) AS total,
       count(r.description) AS withDescription,
       count(r.displayName) AS withDisplayName
```

If `withDescription` ≪ `total`, the data gap is confirmed. After the fix, all three counts must be
equal. Also verify the index is `ONLINE` via `SHOW INDEXES`.

---

## Spike 3 — Framework-name canonicalization across all tools (Issues 3 & 4)

### Decision

Introduce **one shared canonicalization helper** (e.g. `canonical_framework(value) -> Framework`)
used by every tool that accepts a `framework` argument. It maps any accepted spelling to a single
canonical record exposing both representations the system needs:

- `display` — the title-case form stored on graph nodes (`"Spring Boot"`).
- `slug` — the hyphenated key used for Maven-coordinate lookup (`"spring-boot"`).

Accepted inputs (case-insensitive, space/hyphen-insensitive): `"Spring Boot"`, `"spring boot"`,
`"spring-boot"`, `"springboot"` all resolve to the same record. Unknown frameworks return a
structured `unsupported_framework` error listing the supported display names.

### Rationale

The probe showed the inconsistency is twofold:

- **Issue 3**: `check_version_availability` accepts only `"spring-boot"` and rejects `"Spring Boot"`
  with `unsupported_framework`, while ten other tools accept `"Spring Boot"`.
- **Issue 4**: even when called with `"spring-boot"`, its internal graph query filters
  `Version {framework: "spring-boot"}`, but graph nodes store `framework: "Spring Boot"`, so the
  lookup never matches and `exists_in_graph` is always `false`.

The exploration confirmed there is **no shared normalization helper today** — every tool passes
`framework` straight through, and the two representations (graph display name vs Maven slug) are
conflated. A single canonicalizer that yields *both* forms fixes Issue 3 (accept any spelling) and
Issue 4 (query the graph with `display`, query Maven with `slug`) at once, and prevents the class
of bug recurring in future tools.

### Alternatives Considered

- **Normalize inline in each tool** — duplicates the mapping table N times; the next tool added
  will get it wrong again. This is exactly how the current divergence arose. Rejected.
- **Store both forms on Version nodes and match on either** — pushes the inconsistency into the
  data layer and requires re-ingestion. Rejected; canonicalize at the API boundary instead.

### Implementation Notes

The canonical table is small and additive (one row per supported framework). It must live in one
module imported by all tools. The Maven-coordinate table from spec 010 (FR-017) should be keyed by
the same `slug` so the two tables stay aligned.

---

## Spike 4 — Source of `from_version` for pipeline runs (Issue 8)

### Decision

Persist `from_version` on the `Version` node at ingestion time (add a `fromVersion` property via
`upsert_version_artifact_paths`), and have `list_pipeline_runs` return it. As a **defensive
fallback** for already-ingested data, parse `from_version` from the artifact filename when the
node property is absent.

### Rationale

`from_version` is currently **hardcoded to `""`** in the tool response builder
(`tools/artifacts.py`), and it is never stored on the Version node — only `to_version` (the node's
own `version`) is. The value is, however, always recoverable: the CLI receives it as an argument
and the artifact filename encodes it deterministically as
`<framework>-<from>-to-<to>-changes_filtered.md` (`pipeline/_paths.py: artifact_key`). Storing it at
ingestion is the correct fix; the filename-parse fallback avoids a full re-ingestion to backfill
the 20 existing runs.

### Alternatives Considered

- **Filename parse only (no node property)** — zero ingestion changes, but couples the MCP layer to
  a filename convention and breaks if the convention changes. Acceptable only as the fallback, not
  the primary source. Rejected as primary.

### Implementation Notes

Filename-parse regex (POSIX-safe): capture group between the framework prefix and `-to-`. Guard
against frameworks whose display name contains a hyphen by anchoring on the known `-to-` separator
and the trailing `-changes` token.

---

## Spike 5 — Populating deprecated-class edges and LifecycleAlert nodes (Issues 5 & 9)

### Decision

Two ingestion-layer changes, both seeded from a **curated static list** rather than relying solely
on free-text extraction:

- **Deprecated classes (Issue 5)**: seed a known-deprecated-class registry for each framework
  major version (e.g. Spring Boot 3.x → `RestTemplate`, `WebSecurityConfigurerAdapter`,
  `WebMvcConfigurerAdapter`, `EnvironmentPostProcessor`) and create `Class` nodes plus
  `DEPRECATED_IN` / `REPLACED_BY` edges for each, in addition to the entities the extractor finds.
- **LifecycleAlert (Issue 9)**: introduce a new `LifecycleAlert` node label, created during
  ingestion and linked to the relevant `Version` node, seeded from a curated per-version list of
  phase-level signals (e.g. "Spring Security 7 changes the default CSRF policy").

### Rationale

The exploration confirmed `DEPRECATED_IN`/`REPLACED_BY` edges are created **only for entities
explicitly named with `REMOVED`/`REPLACEMENT` roles** in the extracted document. Classes referenced
obliquely ("all classes extending X are deprecated") are never materialised, which is why
`RestTemplate`, `WebMvcConfigurer`, and `EnvironmentPostProcessor` are all `not_found`. A curated
seed list is the only reliable way to guarantee the common, well-known deprecations are present —
extraction quality cannot be depended on for them.

`LifecycleAlert` has **zero references** in the ingestion code; the node type does not exist. The
MCP tool (`analyze_upgrade_path`) already reads `lifecycle_events` and returns an empty array. A new
seeded node type is required to give the tool anything to return.

### Alternatives Considered

- **Improve the LLM extraction prompt to catch implicit deprecations** — higher recall in theory,
  but non-deterministic and unverifiable per-run; would still miss classes not mentioned at all in
  the source doc. Use as a complement, not the guarantee. Rejected as the primary mechanism.
- **Compute lifecycle alerts dynamically from rules at query time** — conflates rule-level and
  phase-level signals; phase alerts apply *before* any specific rule. Rejected.

### Implementation Notes

The seed lists are framework + major-version keyed and additive. They should live alongside the
ingestion code as static data so they are version-controlled and reviewable. Idempotency: use
`MERGE` for both the seeded nodes and their edges so re-running ingestion does not duplicate them.

---

## Spike 6 — `MigrationRule` metadata surfaced by `analyze_upgrade_path` (Issue 6)

### Decision

The fix is split: (a) the **query** must project the rule properties that already exist
(`title`, `changeType`, `statement`) and the linked `BreakingScope.severity` into the
`title`/`change_type`/`reason`/`severity` response fields; (b) **ingestion** must set a `framework`
property on `MigrationRule` nodes and guarantee every rule has a `HAS_SCOPE → BreakingScope` edge so
`severity` is reachable.

### Rationale

The exploration showed the populator **does** write `title`, `changeType`, `reasonType`, and
`statement` on `MigrationRule` (`populator.py:164-203`), but: (1) `severity` lives on the linked
`BreakingScope` node, not the rule; (2) the rule has **no `framework` property**; and (3) the probe
saw the response fields as `null`, which means `analyze_upgrade_path` is not mapping the stored
property names (`title`, `changeType`, `statement`) onto the response keys
(`title`, `change_type`, `reason`). So the data is partly present but unprojected, and partly
missing (severity reachability, framework). Fixing both layers is required for the tool to return
populated metadata.

### Alternatives Considered

- **Copy `severity` onto the rule node too** — denormalises and risks the two going out of sync.
  Prefer projecting it through `HAS_SCOPE` at query time. Rejected.

### Implementation Notes

Confirm with `MATCH (mr:MigrationRule) RETURN keys(mr) LIMIT 5` after ingestion: the key set must
include `title`, `changeType`, `statement`, `framework`. Confirm
`MATCH (mr:MigrationRule)-[:HAS_SCOPE]->(bs) RETURN count(*)` is non-zero.

---

## Spike 7 — Timeout/hang in `resolve_paysafe_dependency_by_service_name` (Issue 10)

### Decision

Bound **every** network call in the resolver with an explicit timeout and convert the FindIt
lookup — currently unbounded — to a timed call. On timeout or unavailability, return a structured
error/empty result rather than hanging.

### Rationale

The exploration found that `findit.lookup(service_name)` (`resolver.py:121`) has **no timeout**,
while the GitLab (`30s`×retries), GitLab-API (`15s`), and Artifactory (`10s`) calls do. The probe
saw "no response (timeout after 5s)" because the unbounded FindIt call can hang indefinitely; the
5s was the *probe client's* timeout, not the server's. The only missing guard is on FindIt.

### Alternatives Considered

- **Wrap the whole tool in an asyncio timeout** — blunt; loses the ability to distinguish which
  backend stalled and to fall back. Prefer per-call timeouts with graceful degradation. Rejected.

### Implementation Notes

Match the existing convention (a module-level `_HTTP_TIMEOUT_SECONDS`-style constant). The tool must
return the same structured error shape the resolver already uses on other failures, so callers get a
clean error instead of a hang.
