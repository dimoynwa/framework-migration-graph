# Applicability Semantics Contract

- **Three-state enum:** `applicability` can only be `"applicable"`, `"not_applicable"`, or `"unknown"`. No other values are permitted
- **"unknown" != "not applicable":** When `user_entities` is empty or absent, ALL steps MUST carry `applicability: "unknown"`. Agents MUST NOT interpret `"unknown"` as `"not_applicable"` — absence of context is not evidence of non-applicability
- **Determination rules (in evaluation order):**
  1. If `user_entities` is empty or absent → `"unknown"` regardless of step edges
  2. If the step has no `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, or `AFFECTS_DEPENDENCY` edges → `"unknown"` regardless of `user_entities`
  3. If `user_entities` is non-empty AND intersection with step's affected entities is non-empty → `"applicable"`, `matched_entities` = the intersected names
  4. If `user_entities` is non-empty AND intersection is empty → `"not_applicable"`, `matched_entities = []`
- **Deduplication:** Rule 4 of FR-012 applies before applicability scoring — duplicate `step_id` rows are removed first (first occurrence wins), then applicability is computed on the deduplicated set
- **`matched_entities` field:** always present, never null, `[]` when applicability is not `"applicable"`
- **Scope:** This contract applies to `build_recipe_plan` in `migration_oracle/mcp/tools/upgrade.py` and its backing query in `migration_oracle/mcp/graph/queries/upgrade.py`
