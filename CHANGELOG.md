# Changelog

## [013a-live-probe-fixes] — 2026-06-15

### Behavioural change (breaking for callers that persist rule_id)

- `analyze_upgrade_path`, `build_recipe_plan`, and `get_pending_steps` now return `rule_id` as the stable `MigrationRule.ruleId` property (`pipeline://…` for pipeline rules, `community://…` for community insights), falling back to `elementId(rule)` only when no `ruleId` property exists. Callers that persisted the previous element-ID-based `rule_id` must re-key their stored values.

### New features

- **Server build provenance**: `get_graph_schema` now includes a `server_build` block (`git_sha`, `branch`, `feature_tags`, `started_at`). Set `GIT_SHA`, `GIT_BRANCH`, `FEATURE_TAGS` env vars at deploy time.
- **`matched_entities`** added to `analyze_upgrade_path` rule objects (exact-string matching against scanned entities).
- **Recipe coverage diagnostic**: `build_recipe_plan` now returns `diagnostics.recipes_loaded` (bool) and `diagnostics.recipe_count` (int), making the zero-recipe state visible.
- **`context_id` parameter** added to `build_recipe_plan` (optional); when provided, version range is derived from the context's resolved `UPGRADES_FROM`/`UPGRADES_TO` bounds.
- **`reused`, `entityCount`, `droppedCount`** always present on `create_migration_context` response (both create and resume paths).
- **`solution` field** added to `search_migration_knowledge` hit objects.
- Community insights now receive a stable `ruleId` of the form `community://{framework}/{version}/{uuid}` at create time.

### Bug fixes

- Zombie context guard: if `create_migration_context` resumes a context whose `UPGRADES_FROM`/`UPGRADES_TO` edges point to wrong nodes, it deletes and re-creates the context.
- `search_migration_knowledge` hits now include `solution` field (was missing from serializer).
- `_ANALYZE_UPGRADE_PATH` Cypher now includes the package-prefix bridge for Dependency-only rules (matching scanned class FQCNs against dependency groupId prefix), consistent with `_GET_PENDING_STEPS`.
- `build_recipe_plan` entity matching now uses exact-string comparison (was using `.lower()`, diverging from how typed buckets are populated).

### Follow-up (FU-1 — out of scope)

- Community rule `ruleId` was previously not written at all by `submit_migration_insight`. Now set to `community://…` at create time. Existing community rules created before this release still have no `ruleId` and rely on the `coalesce(rule.ruleId, elementId(rule))` fallback, which remains rebuild-unstable for those nodes. Owner: TBD.
