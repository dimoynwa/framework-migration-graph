# Contract: Default BreakingScope

**Spec**: 011-mcp-live-probe-fixes | **FR**: FR-017

## Purpose

Guarantees that every `MigrationRule` node has at least one `HAS_SCOPE → BreakingScope` edge
after ingestion. Without this guarantee, `analyze_upgrade_path` returns `null` for `severity` on
every rule whose source breaking-change carried no explicit scope classification, and
`get_steps_for_scope_tier` may silently drop steps.

---

## Default Node

When a `MigrationRule` has no explicit `BreakingScope` from its source data, the ingestion
pipeline MUST link it to the following default node:

```
(:BreakingScope {scope: "general", severity: "low"})
```

This node is shared across all rules that have no explicit scope (MERGE ensures a single node).

---

## Cypher Pattern

Applied in `migration_oracle/pipeline/populator.py` after `_write_entity` has run:

```cypher
MATCH (rule:MigrationRule {ruleId: $rule_id_key})
WHERE NOT (rule)-[:HAS_SCOPE]->(:BreakingScope)
MERGE (bs:BreakingScope {scope: "general", severity: "low"})
MERGE (rule)-[:HAS_SCOPE]->(bs)
```

The `WHERE NOT (rule)-[:HAS_SCOPE]->(:BreakingScope)` guard ensures rules that already have an
explicit scope are never linked to the default — the default is only a fallback.

---

## Idempotency

Both the `BreakingScope` node and the `HAS_SCOPE` edge are created with MERGE, so re-ingestion
never creates duplicates.

---

## Semantics

| Field    | Value       | Meaning |
|----------|-------------|---------|
| `scope`  | `"general"` | The rule applies across all scope tiers; it is not scoped to a specific migration area (e.g. `"build"`, `"API"`, `"config"`). |
| `severity` | `"low"`   | Conservative default. Rules whose actual severity is unknown are treated as low-priority until reclassified by the source data. |

---

## Impact on get_steps_for_scope_tier

With every rule having a `HAS_SCOPE` edge, the `_GET_STEPS_FOR_SCOPE_TIER` WHERE clause
`WHERE bs IS NULL OR bs.scope = $scope` behaves as follows:

- Rules with `scope="general"` are EXCLUDED when the caller requests `scope="build"` (different
  scope value) — by design. The default scope is not a wildcard.
- Rules with `scope="general"` ARE returned when the caller requests `scope="general"`.
- Truly scopeless rules (no `BreakingScope` edge at all — only possible before re-ingestion) are
  returned with `scope: null` (FR-018 safety net).

After re-ingestion with this fix applied, all rules have at least the default scope and the
`bs IS NULL` branch should never fire. It is retained as a defensive fallback.

---

## Prohibition

No code path in the MCP server tools or ingestion pipeline MUST assume a `MigrationRule` has no
`HAS_SCOPE` edge. After spec 011 is implemented, every rule is guaranteed at least the default.
Queries that use `OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs)` remain valid but the `bs IS NULL` branch
represents the pre-ingestion state only.
