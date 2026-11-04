# Changelog

## [021-github-change-enrichment] — 2026-11-04

### New features

- Spring Boot GitHub release rows that cite an issue or pull request are enriched from the GitHub Issues API (title, cleaned body, labels, close reason) so later filter and entity steps see more than the one-line release note. A short backport or forward-port pointer is replaced with the original issue body, one level only.
- Angular release and changelog rows that cite a commit are enriched from the commit message (scope, body, breaking and deprecation footers, linked issue, schematic files). A row with only a pull or issue link uses the issue path. Requires `GITHUB_TOKEN`. Disable with `SPRING_BOOT_GITHUB_ENRICHMENT=false` or `ANGULAR_GITHUB_ENRICHMENT=false`. A primary rate-limit response stops further issue and commit fetches for the rest of the run without dropping the hop.

## [hop-granularity] — 2026-11-04

### New features

- **Configurable ingestion step size**: `export-extract-populate-framework` accepts `--hop-granularity patch|minor` (env `HOP_GRANULARITY`, default `patch`). `minor` collapses each minor line into one hop while keeping patch endpoints (`3.3.12 → 3.4.0 → 3.4.2`).
- **`--hop-by-hop` / `--no-hop-by-hop`** (env `HOP_BY_HOP`, default off): runs filter LLM, entity LLM, and graph population once per version hop, so each hop gets its own raw/filtered/entities artifacts and its own `Version` node carrying only that hop's rules. Cache resolution and `--skip-existing` apply per hop, so an interrupted range resumes at the first missing hop; `--output-*` overrides are rejected because paths are derived per hop.
- **Per-hop BOM diff** under `--hop-by-hop` (`BaseExtractor.extract_contexts(per_hop_range_metadata=True)`) — patch-level dependency and CVE movement was previously flattened into one range-level diff.
- **Prereleases are ordinary versions**: `4.1.0-RC1`, `4.1.0-M1`, `22.0.0-rc.2`, `20.0.0-next.3` and the JBoss `26.1.2.Final` spelling now parse. Prerelease `sortableVersion` sits below the GA release it precedes (`4.1.0-M1` → 4000901, `4.1.0-RC1` → 4000951, `4.1.0` → 4001000), so **GA integers are unchanged** and no backfill is required. New `Version` properties: `preRelease`, `preReleaseLabel`.
- **`scripts/run_spring_boot_patch_ingest.sh`**: GA-only patch-level Spring Boot ingestion by default (extract-only unless `full`), with `SPRING_INCLUDE_PRERELEASE=1` to include milestone/RC hops.

### Bug fixes

- `version_key()` ignored prerelease suffixes, so `4.1.0-M1`, `4.1.0-RC1` and `4.1.0` compared equal: discovery order decided hop sequences, and a range ending at `4.1.0-RC1` also swallowed the GA release.
- Spring Boot minor-line wiki pages (`Spring-Boot-{major}.{minor}-Release-Notes`) were attached to every hop that landed inside the line — measured 57 duplicated rows in each of the 13 hops of a 3.3.x range. They are now attached only to the hop that **enters** the line. `extract()` calls without a `hop_context` keep the previous behaviour.

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
