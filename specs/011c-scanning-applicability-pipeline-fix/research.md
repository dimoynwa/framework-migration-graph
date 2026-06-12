# Research — Spec 011c: Scanning & Applicability Pipeline Fix

Phase 0 research artifact. Resolves the technical unknowns that gate the five
defects documented in [`GAPS.md`](GAPS.md). Each spike below corresponds to a decision that
is *not* obvious from the code and would otherwise force a guess during
implementation.

The defects were confirmed against the live server on 2026-06-12 by reading the
Cypher in `migration_oracle/mcp/graph/queries/upgrade.py` and
`migration_oracle/mcp/graph/queries/context.py` and cross-checking the
applicability logic in `migration_oracle/mcp/graph/queries/upgrade.py`.

---

## Spike 1 — Why `CONTAINS` matching fails and what replaces it

### Decision

Replace the `CONTAINS`-based predicate with **per-kind exact matching** keyed on
entity type. The scanner emits entities into four typed lists; matching is
performed with `IN` (set membership) or `last(split(…))` equality, never
substring containment.

| Kind | Tier `strong` | Tier `weak` |
|---|---|---|
| Class | `e.name IN $scanned_classes` | `last(split(e.name,'.')) IN $scanned_class_simple` |
| Dependency | `(split(e.name,':')[0]+':'+split(e.name,':')[1]) IN $scanned_deps_ga` | `last(split(e.name,':')) IN $scanned_dep_artifacts` |
| Property | `e.name IN $scanned_props` | — |

A rule is **matched** when any affected entity hits at `strong` or `weak` tier.

### Rationale

The current predicate in `_ANALYZE_UPGRADE_PATH` (lines 16–17 and 34–37) and
`_BUILD_RECIPE_PLAN` (lines 116–118) of `upgrade.py` is:

```cypher
toLower(e) CONTAINS toLower(u)
```

This is asymmetric in two failure modes:

**False positives** — A scanned entity `"spring-boot-starter-web"` matches any
graph node whose name contains the short token `"web"` — i.e. every rule linked
to `spring-boot-starter-webflux`, `spring-web`, `spring-webmvc`, etc. Every
short token the user supplies inflates the matched-rule set.

**False negatives** — A scanned FQCN `"org.springframework.boot.env.EnvironmentPostProcessor"`
does not contain the graph-stored simple name `"EnvironmentPostProcessor"` because
the containment direction is `graph CONTAINS user`, not `user CONTAINS graph`. The
scanner produces long FQCNs; the graph stores short names. The predicate direction
means FQCNs will never match stored simple names — the most common case.

There is also an inconsistency within `build_recipe_plan` today: the Cypher uses
`CONTAINS` to pre-filter the rule rows, but the Python post-processor at line 310
applies `e.lower() in user_ents_lower` which is exact membership in the other
direction. These two filters do not agree; the Cypher may pass rules the Python
then silently excludes, and vice versa.

Per-kind exact matching with a strong/weak tier removes both failure modes without
requiring Cypher full-text search or graph schema changes. The two tiers handle
the FQCN-vs-simple-name asymmetry directly: strong matches FQCN-to-FQCN, weak
matches FQCN-to-simple by comparing only the last dotted segment.

### Alternatives Considered

- **Bidirectional `CONTAINS`** (`e CONTAINS u OR u CONTAINS e`) — reduces false
  negatives for FQCN/simple mismatches but makes false positives worse (any shared
  substring now matches in both directions). Rejected.
- **Lucene full-text on entity names** — overkill for a finite lookup set; requires
  an index on `Class.name`, `Dependency.name`, `ApplicationProperty.name`.
  Rejected.
- **Normalise graph entity names to simple form** — loses the FQCN disambiguation
  needed for packages with colliding simple names (e.g. `jackson.databind.ObjectMapper`
  vs hypothetical `tools.jackson.databind.ObjectMapper`). Rejected.

### Implementation Notes

The four typed Cypher params are:
```
$scanned_classes        — FQCNs extracted from import lines
$scanned_class_simple   — simple names (star imports / unresolved refs)
$scanned_deps_ga        — "groupId:artifactId" without version
$scanned_dep_artifacts  — bare artifactId only (fallback)
$scanned_props          — canonical dotted property keys
```

All four must be passed to every query that currently accepts `$user_entities`.
The Python tool layer must split the flat `user_entities` list into these five
buckets before calling the query functions, using the normalization rules in
§3 of `GAPS.md`.

---

## Spike 2 — How to store kind-separated entity sets on `MigrationContext`

### Decision

Store five new primitive-array properties on `MigrationContext` at creation time:
`scannedClasses`, `scannedClassSimple`, `scannedDepsGa`, `scannedDepArtifacts`,
`scannedProps`. The existing `scannedEntities` flat list is kept for backwards
compatibility but is no longer the authoritative input for queries.

### Rationale

`MigrationContext` currently stores a flat `scannedEntities` string array on the
node (`context.py:22`). The `_GET_PENDING_STEPS` query (`context.py:56–91`) reads
*nothing* from the context for entity filtering — the query applies zero applicability
logic and returns every step on the migration path regardless of which entities are
present in the project.

This means the rule set shown to the developer via `analyze_upgrade_path` (entity-
filtered, possibly under-inclusive due to substring bugs) and the step queue they
execute via `get_pending_steps` (entirely unfiltered) come from different rule sets.
A critical rule with no entity match is excluded from the plan but its steps still
appear in the execution queue.

To fix `get_pending_steps` the query must read entity sets from the context node
(not from a separate call parameter — the tool signature has no `user_entities`
argument and adding one would break the session-resumption contract). Neo4j
primitive arrays are the correct storage type; map properties are not supported
(confirmed by spec 011 Spike 1).

The five-property split is necessary for the per-kind `IN` matching in the Cypher.
A single flat list cannot distinguish FQCNs from artifact IDs from property keys, so
the correct tier (strong/weak class, dependency, property) cannot be determined
inside Cypher without the kind tag.

### Alternatives Considered

- **Store kind as a prefixed string in a single array** (`"class:org.springframework…"`) —
  works but requires `split(item, ':')[0]` to recover the kind inside Cypher, making
  queries harder to read and auditing harder. Rejected in favour of separate arrays.
- **Store JSON-serialised string** — Neo4j rejects map properties; a JSON string is
  a primitive but is opaque to Cypher. Rejected (same rationale as spec 011 FR-001
  for stepNotes).
- **Pass entity sets as tool parameters to `get_pending_steps`** — breaks the session
  API (the context already holds the scan; callers should not need to resupply it on
  every call). Rejected.

### Implementation Notes

`create_migration_context` must receive the normalized typed lists and write all
five arrays. The `MERGE` key (`projectId + fromVersion + toVersion`) is unchanged;
`ON CREATE` must set all five new properties; `ON MATCH` must update them so
a resumed session refreshes the entity scan (per Loop I step 4 in the skill).

Migration path for existing contexts: the five new properties will be absent;
`get_pending_steps` must treat absent/empty arrays as "no entity filter" (equivalent
to the current unfiltered behaviour) so existing contexts degrade gracefully rather
than returning empty step queues.

---

## Spike 3 — The breaking-change safety net: why and how

### Decision

A rule with any `BreakingScope` whose `severity` is `"high"` or `"critical"` is
**always included** in query results even when no entity matches, carrying
`applicability = "uncertain"`. This is a hard guarantee: no breaking change is
silently dropped.

### Rationale

The current Cypher in `_ANALYZE_UPGRADE_PATH` (`upgrade.py:31–42`) is:

```cypher
WHERE rule IS NULL
   OR (
       size($user_entities) = 0
    OR size(affected_entities) = 0
    OR ANY(e IN affected_entities WHERE ANY(u IN $user_entities
               WHERE toLower(e) CONTAINS toLower(u)))
      AND …
   )
```

A rule with `affected_entities = ["spring-boot-starter-web"]` and
`user_entities = ["RestTemplate"]` passes neither the empty-list guard nor the
CONTAINS predicate. It is dropped silently — even if its `BreakingScope.severity`
is `critical`. The Python `_enrich()` post-processor does assign
`applicability="not_applicable"` in theory, but those rows never reach it because
the Cypher discards them before the Python layer sees them.

The fix: move the applicability decision inside the Cypher WITH chain (as GAPS.md
§6.1 prescribes), compute `sev_rank` from `HAS_SCOPE → BreakingScope`, and keep
rows where `applicability <> 'excluded'`. Rules with no entity match and
`sev_rank <= 1` (high/critical) fall into `uncertain` instead of `excluded`.

`uncertain` rules are returned to the caller with `applicability = "uncertain"`.
This signals that the rule may or may not affect the project (the entity scan
didn't confirm it) but the severity is high enough that the developer must
explicitly dismiss it rather than having it omitted automatically.

### Alternatives Considered

- **Return all rules regardless of entity match** — removes applicability filtering
  entirely; a large rule set for a minor upgrade becomes unworkably noisy. Rejected.
- **Post-process safety-net re-query**: after the main query, run a second query
  for high/critical rules and union the results — two round-trips, more complex
  dedup. The Cypher `CASE WHEN … THEN 'uncertain' ELSE 'excluded' END` gate
  handles this in one pass. Rejected.

### Implementation Notes

The Cypher shape follows GAPS.md §6.1 closely. The severity rank is computed from
`OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)` with:

```cypher
min(CASE bs.severity
      WHEN 'critical' THEN 0 WHEN 'high' THEN 1
      WHEN 'medium'   THEN 2 WHEN 'low'  THEN 3 ELSE 4 END) AS sev_rank
```

Rules with no `HAS_SCOPE` edge get `sev_rank = 4` and are treated as `informational`
(no entities linked → `informational`, regardless of sev_rank).

The Python `analyze_upgrade_path` function must stop re-implementing the applicability
logic (`_enrich()`) once the Cypher handles it. The Cypher returns `applicability`
directly; Python only needs to forward it.

---

## Spike 4 — How `get_pending_steps` reads entity sets from the context

### Decision

`_GET_PENDING_STEPS` must read the five kind-separated arrays from the context node
(`ctx.scannedClasses`, etc.) and apply the same per-kind exact matching and safety-
net logic as `analyze_upgrade_path`. Steps belonging to `"excluded"` rules are
dropped; steps belonging to `"uncertain"` rules are returned with
`applicability = "uncertain"` so the executor can surface them for confirmation.

### Rationale

`get_pending_steps` currently has no entity filter whatsoever (confirmed by reading
`context.py:56–91`). The execution queue therefore includes steps for every rule
on the migration path, including rules that the `analyze_upgrade_path` plan excluded
for the same entities. This divergence means an agent following the plan would skip
a step that `get_pending_steps` then re-surfaces as pending — an infinite retry loop.

Sourcing entity lists from the context node (not a tool parameter) preserves the
tool's single-argument signature. The five arrays are written at `create_migration_context`
time (Spike 2) so they are always available when `get_pending_steps` is called.

Context rows created before this spec lack the new arrays; the Cypher must treat
`coalesce(ctx.scannedClasses, [])` etc. as empty-list inputs, which triggers the
"empty → no filter → return all" short-circuit, reproducing the current unfiltered
behaviour for legacy contexts.

### Alternatives Considered

- **Add `user_entities` parameter to `get_pending_steps`** — breaks session
  resumption (callers would need to re-supply the scan on every call after
  context load). Rejected.
- **Re-run `analyze_upgrade_path` inside `get_pending_steps` and intersect** —
  double the queries, no guarantee of consistency if rule set changes between calls.
  Rejected.

### Implementation Notes

The Cypher shape is given in GAPS.md §6.3. The key additions versus the current
query are the `OPTIONAL MATCH (r)-[:AFFECTS_…]->(e)` and the per-kind `CASE`
block reading `ctx.scannedClasses` etc., followed by the
`CASE … 'informational'/'matched'/'uncertain'/'excluded' END` gate.

`_pending_step()` in `tools/context.py` must forward the new `applicability` field.

---

## Spike 5 — Coverage diagnostics: what to return and where

### Decision

Every query that applies entity filtering returns a `diagnostics` block alongside
the results:

```json
{
  "scanned_total": 412,
  "matched_entities": ["spring-boot-starter-data-redis", "ObjectMapper"],
  "unmatched_entities": ["spring.redis.host"],
  "rules_included": 37,
  "rules_excluded_by_entity_filter": 121,
  "rules_via_safety_net": 4
}
```

`diagnostics` is present whenever `user_entities` (or the context's scanned lists)
is non-empty. It is absent (or `null`) when no entity filter was applied.

### Rationale

Without diagnostics, a developer who receives a 5-rule plan has no way to know
whether 200 rules were considered and 195 excluded, or whether only 5 rules exist
for this version range. Silent omission is how the current substring-matching bugs
went undetected in production — the plan looked reasonable even while discarding
genuinely applicable rules.

`matched_entities` and `unmatched_entities` let the developer spot extraction
failures: if `spring.redis.host` is in `unmatched_entities` it means the graph
has no rule linked to that property key (a potential data gap), not that the
property was silently ignored.

`rules_via_safety_net` surfaces the uncertain count separately so developers can
quickly see how many rules they need to manually confirm.

### Implementation Notes

Diagnostics are computed as aggregates inside the Cypher `WITH` chain in the same
query that computes `applicability`. They do not require a second query.

`analyze_upgrade_path` and `build_recipe_plan` tool responses add a top-level
`diagnostics` key. `get_pending_steps` adds a `diagnostics` key to the
`get_pending_steps` response alongside `pending_steps`.

---

## Spike 6 — `DISCOVERED_IN` dead relationship branch in `hydrate_nodes`

### Decision

Remove `DISCOVERED_IN` from the `hydrate_nodes` traversal in
`migration_oracle/mcp/graph/queries/search.py:75`. The correct traversal for
linking a `MigrationRule` to a `Version` is `INCLUDES_RULE`, which is already
present and is the only relationship type used by the ingestion pipeline.

### Rationale

`hydrate_nodes` at line 75 has:

```cypher
OPTIONAL MATCH (n)-[:INCLUDES_RULE|DISCOVERED_IN]-(v:Version)
```

`DISCOVERED_IN` does not exist in the graph schema (confirmed by the ingestion
pipeline and the schema reference in `docs/graph-schema.md` — no `DISCOVERED_IN`
edge type is defined or written anywhere). Including a non-existent relationship
type in a traversal is silently a no-op in Neo4j (it matches zero rows), so this
does not cause errors. However:

1. It is misleading to future readers of the code.
2. If a future schema revision introduces a `DISCOVERED_IN` relationship for a
   different purpose, the search query would begin traversing it unexpectedly.
3. The `search_migration_knowledge` docstring references
   "`INCLUDES_RULE|DISCOVERED_IN`" as if both are valid paths — this creates a
   false contract for callers.

### Implementation Notes

Single-line edit: change
`[:INCLUDES_RULE|DISCOVERED_IN]` → `[:INCLUDES_RULE]`.
No query behaviour changes (the `DISCOVERED_IN` branch matches nothing today);
this is a correctness/readability fix only.

---

## Spike 7 — `top_n` output cap and `search_openrewrite_recipes` docstring mismatch

### Decision

**`top_n` cap**: The `top_n=50` default in `analyze_upgrade_path` (`tools/upgrade.py:98`)
silently drops applicable rules when the total rule count exceeds 50. The cap must
remain (unbounded responses are impractical) but must be made visible: when the
cap is reached, the `diagnostics` block (Spike 5) must include a
`"rules_capped_at": top_n` field so callers know the list is truncated. The cap
itself should be applied *after* sorting by applicability tier then severity, so
the highest-priority rules survive.

**`search_openrewrite_recipes` docstring**: The tool docstring
(`tools/search.py:199`) states that `only_composite` and `require_no_params`
are "accepted but not yet applied". In fact `hydrate_openrewrite_recipes`
(`graph/queries/search.py:116–119`) *does* apply both via Cypher:

```cypher
AND (NOT $only_composite OR r.composite = true)
AND (NOT $require_no_params OR NOT EXISTS { … })
```

The docstring is wrong, not the code. The fix is to update the docstring to
accurately state that both filters are applied at the Cypher layer.

### Rationale

The output cap concern (Spike 7 part 1) is distinct from the input-cap concern in
GAPS.md §2. GAPS.md §2 described an agent-side skill that capped `user_entities`
to 200 before sending them to the server. That specific cap is not present in the
current `framework_migration_main.md` skill. The *output* cap (`top_n=50`) is a
server-side issue: rules 51+ are silently dropped with no indication in the
response. Adding the `rules_capped_at` diagnostics field addresses this without
removing the cap.

The rule ordering before capping must be: `uncertain` first (safety-net items the
developer must review), then `matched` ordered by descending severity, then
`informational`. This ensures the most important rules survive truncation.

### Alternatives Considered

- **Remove `top_n` entirely** — responses for broad version ranges could contain
  hundreds of rules; impractical for agent context windows. Retained with diagnostics.
- **Raise the default** — arbitrary; diagnostics make the cap visible regardless of
  its value. Rejected as the sole fix.
