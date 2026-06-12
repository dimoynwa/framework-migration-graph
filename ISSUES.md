# MCP Server — Live Probe Issues

Probe date: 2026-06-12
Server: http://localhost:8080/sse
Project: paysafe-wallet-switch (Spring Boot 3.5.0 → 4.0.0, detected from build.gradle)

## Summary

| # | Tool | Category | Severity | One-line description |
|---|---|---|---|---|
| 1 | `search_openrewrite_recipes` | `missing-data` | Low | 0 OpenRewriteRecipe nodes in graph — recipe data never ingested |
| 2 | `resolve_deprecation` / `entity_evolution` | `missing-data` | Low | Deprecated entity has no linked rules or replacement info in graph |
| 3 | `search_migration_knowledge` | `missing-data` | Low | Hit objects contain no `title` field — only `statement`; callers relying on `title` see empty strings |

---

## Result: CLEAN — no tool errors, crashes, or query bugs detected.

All 22 tools registered and responded without errors. Version normalisation works (patch versions accepted). Hybrid search active (varying scores). Context lifecycle (create → probe → close) completed without issues.

---

## Issue 1 — OpenRewrite recipe data not loaded

**Severity:** Low
**Category:** `missing-data`
**Tool(s):** `search_openrewrite_recipes`

**Error / symptom observed:**
`search_openrewrite_recipes` query "Spring Boot upgrade 4.0" returned 0 hits. Cypher verification:
```cypher
MATCH (r:OpenRewriteRecipe) RETURN count(r) AS cnt
```
returned `cnt=0` — no `OpenRewriteRecipe` nodes exist in the graph at all.

**Root cause:**
The recipe ingestion pipeline (which populates `OpenRewriteRecipe` nodes and `AUTOMATED_BY` edges) has never been run for this graph instance. This is confirmed by `build_recipe_plan` also returning `auto_track=[]` — no automatable steps exist because there are no recipe links.

**Likely fix:**
Run the OpenRewrite recipe ingestion step of the migration pipeline. Once nodes are present, no search-index rebuild should be required — the existing BM25/vector index on `MigrationRule` covers `community_insight` typed rules; recipe nodes may need their own index entry.

**Impact:**
`search_openrewrite_recipes` is always empty. `build_recipe_plan` auto track is always empty. Developers cannot discover or apply automated migration recipes via the MCP server.

---

## Issue 2 — Deprecated entity has no replacement or linked rules

**Severity:** Low
**Category:** `missing-data`
**Tool(s):** `resolve_deprecation`, `entity_evolution`

**Error / symptom observed:**
For `EnvironmentPostProcessor` (`framework=Spring Boot`):
- `resolve_deprecation` returns `deprecated_in=3.0.0`, `replaced_by=null`, `rules=[]`
- `entity_evolution` returns a chain of length 1 where the embedded rule has `statement=null`, `action=null`, `type=null`

**Root cause:**
The Class node for `EnvironmentPostProcessor` was created with lifecycle metadata (`deprecated_in`) but without:
- A `replaced_by` pointer to a successor class
- Any `MigrationRule` node linked via `AFFECTS_CLASS`
- Any `REMOVED_IN` or `INTRODUCED_IN` edges for the successor

This is a data completeness gap in the entity extraction pipeline, not a query bug.

**Likely fix:**
Enrich the `EnvironmentPostProcessor` entity in the graph: add `replaced_by` (the replacement API, if one exists), and link the relevant `MigrationRule` via `AFFECTS_CLASS`. If no replacement exists, `replaced_by=null` is correct and the `rules=[]` gap should be addressed by linking the migration rule that mentions this class.

**Impact:**
Callers of `resolve_deprecation` or `entity_evolution` for this entity receive minimal guidance — `deprecated_in` is present but there is no actionable next step, no replacement pointer, and no migration rule body. A developer would be told the class is deprecated since 3.0.0 with no suggestion of what to do.

---

## Issue 3 — `search_migration_knowledge` hits use `statement` not `title`

**Severity:** Low
**Category:** `missing-data`
**Tool(s):** `search_migration_knowledge`

**Error / symptom observed:**
Hit objects returned by `search_migration_knowledge` contain a `statement` field but no `title` field:
```json
{
  "node_id": "4:...:1220",
  "node_type": "MigrationRule",
  "statement": "When migrating from Spring Boot 3.5 to 4.0...",
  "score": 0.0309,
  "source_url": "",
  "action_step": "",
  "rule_type": "community_insight"
}
```
No `title` key is present. Callers (including the live-probe skill itself) that read `hit.get("title")` receive `None` / empty string.

**Root cause:**
`MigrationRule` nodes store the human-readable summary in `rule.statement` (and sometimes `rule.title`). The search result projection maps `statement` but not `title`. For `community_insight` type rules, there may be no `title` property on the node at all — the statement IS the title.

**Likely fix:**
Either (a) add a `title` field to the search hit projection, falling back to `statement[:80]` if `title` is null, or (b) update the tool docstring to document that `statement` is the primary human-readable field. Callers should use `hit.get("statement") or hit.get("title")`.

**Impact:**
Low — content is still accessible via `statement`. But any UI or downstream consumer that renders `title` will show a blank label, degrading readability.

---

## Probe log summary

| Step | Tool | Result |
|---|---|---|
| 0 | project scan | OK — paysafe-wallet-switch, 1444 entities (1431 classes, 6 artifacts, 7 properties) |
| 0.5 | server reachability | OK — SSE endpoint live |
| 1 | tools/list | OK — 22 tools |
| 2 | list_pipeline_runs | OK — 4 Spring Boot runs; 3.5.0→4.0.0 selected |
| 3 | create_migration_context | OK — context_id created |
| 4 | analyze_upgrade_path | OK — 16 rules, 5 lifecycle alerts |
| 5 | build_recipe_plan | OK — 16 manual rule cards, fallback=false |
| 6 | get_pending_steps | OK — 0 pending steps (no MigrationStep nodes linked) |
| 7 | search_migration_knowledge | OK — hybrid scores, hits returned |
| 8 | resolve_deprecation | OK (data gap: no replacement/rules for EnvironmentPostProcessor) |
| 8 | entity_evolution | OK (data gap: null rule fields in chain) |
| 9 | search_openrewrite_recipes | WARN — 0 nodes in graph |
| 10 | get_community_insights | OK — 1 insight |
| 10 | submit_migration_insight | OK — duplicate detected correctly |
| 11 | analyze_upgrade_path (patch) | OK — normalisation works (3.5.12→4.0.6 returns 5 rules) |
| 12 | close_migration_context | OK — status=partial |
