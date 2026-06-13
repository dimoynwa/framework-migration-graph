# Contract: `analyze_upgrade_path`

**Work-stream**: WS3 — Query Correctness
**FR**: FR-009
**File**: `migration_oracle/mcp/graph/queries/upgrade.py` (`_ANALYZE_UPGRADE_PATH` Cypher string)

---

## Purpose

Return migration rules and lifecycle alerts for a framework version range. When `include_recipes=True`, each rule's steps must include the recipes that automate them, joined through the step that has the `AUTOMATED_BY` edge.

---

## Inputs

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `framework` | string | yes | — |
| `current_version` | string | yes | — |
| `target_version` | string | yes | — |
| `user_entities` | list[string] | no | `[]` |
| `format` | string | no | `"json"` |
| `classification` | list[string] | no | `None` |
| `include_recipes` | bool | no | `False` |
| `include_lifecycle` | bool | no | `True` |
| `top_n` | int | no | `50` |
| `verbose` | bool | no | `False` |
| `scope_filter` | list[string] | no | `[]` |
| `min_severity` | string | no | `None` |

---

## Outputs — Success (json format)

```json
{
  "status": "ok",
  "framework": "<string>",
  "from_version": "<string>",
  "to_version": "<string>",
  "rules": [
    {
      "rule_id": "<element-id>",
      "rule_type": "<string>",
      "title": "<string|null>",
      "statement": "<string>",
      "action_step": "<string|null>",
      "source_url": "<string|null>",
      "reason": "<string|null>",
      "solution": "<string|null>",
      "change_type": "<string|null>",
      "reason_type": "<string|null>",
      "entity_classification": "<string|null>",
      "affected_entities": ["<string>"],
      "applicability": "<string>",
      "severity": "<string|null>",
      "scopes": [{"scope": "<string>", "severity": "<string>"}],
      "steps": [
        {
          "step_id": "<element-id>",
          "step_type": "<string>",
          "summary": "<string>",
          "instruction": "<string>",
          "effort": "<string>",
          "automatable": "<boolean>",
          "verification_hint": "<string|null>",
          "cli_operation": "<string|null>"
        }
      ],
      "recipes": [
        {
          "step_id": "<element-id>",
          "recipe_id": "<string>",
          "display_name": "<string|null>",
          "auto": "<boolean>",
          "missing_required_params": ["<string>"]
        }
      ]
    }
  ],
  "lifecycle_alerts": [
    {"message": "<string>", "category": "<string>", "phase": "<string>"}
  ],
  "format": "json"
}
```

---

## Recipe Join — Corrected Traversal (FR-009)

### Current bug

```cypher
-- WRONG: AUTOMATED_BY does not exist from MigrationRule
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
```

`AUTOMATED_BY` is defined in the schema as:
```
(MigrationStep)-[:AUTOMATED_BY]->(OpenRewriteRecipe)
```
This means the current query always returns `rec = null`, producing `recipes: []` for every rule.

### Corrected Cypher (in `_ANALYZE_UPGRADE_PATH`)

```cypher
OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)   -- ← fix: from s, not rule
```

### Recipe semantics after fix

| Case | `recipes` list for the rule |
|------|-----------------------------|
| Rule has no steps | `[]` |
| Rule has steps, none with `AUTOMATED_BY` | `[]` |
| Rule has steps, at least one with `AUTOMATED_BY` | Non-empty; one entry per step that has an automating recipe |

An empty `recipes` list is not an error. It means no step in this rule has an `AUTOMATED_BY` edge. This case is distinct from the rule having no steps at all (which produces `steps: []` and `recipes: []`).

### Recipe entry fields — attach to their step

Each entry in `recipes` corresponds to one `(MigrationStep, AUTOMATED_BY, OpenRewriteRecipe)` triple and **includes the step's element ID** so callers can associate the recipe with the step that requires it:

| Field | Source | Notes |
|-------|--------|-------|
| `step_id` | `elementId(s)` | Element ID of the `MigrationStep` this recipe automates |
| `recipe_id` | `rec.recipeId` | Fully-qualified recipe name |
| `display_name` | `rec.displayName` | Human-readable label |
| `auto` | `ab.auto` | Whether the recipe runs without manual intervention |
| `missing_required_params` | `coalesce(ab.missingRequiredParams, [])` | Recipe params the user must supply |

The `step_id` field is **required** — without it a caller receiving a rule with multiple steps cannot determine which step a given recipe automates.

**Corrected collect clause** (in `_ANALYZE_UPGRADE_PATH`):

```cypher
OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

-- In the per-rule collect:
collect(DISTINCT CASE WHEN rec IS NULL THEN null ELSE {
  step_id:                elementId(s),           -- ← new field
  recipe_id:              rec.recipeId,
  display_name:           rec.displayName,
  auto:                   ab.auto,
  missing_required_params: coalesce(ab.missingRequiredParams, [])
} END) AS recipes_raw
```

---

## Error Shapes (unchanged)

```json
{ "status": "error", "error_code": "unsupported_framework", "hint": "<string>" }
```

All existing error shapes are preserved by this fix (FR-018). The only change is to the Cypher traversal within the query; the tool function signature and return structure are otherwise unchanged.

## FR-019 Compliance

`analyze_upgrade_path` is read-only. No write is performed by this tool. `execute_custom_cypher` must not be used as an alternative to any part of this query.
