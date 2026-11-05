# Changelog

## [023-per-change-research] — 2026-11-04

### New features

- **Default hop granularity is now `minor`**: `HOP_GRANULARITY` / `--hop-granularity` default to one hop per minor line (`19.0.0 → 19.1.0 → 19.2.0 → 20.0.0`) instead of every patch release. Pass `--hop-granularity patch` (or set `HOP_GRANULARITY=patch`) for the old behaviour.
- **Fetch-only research**: `TAVILY_API_KEY` is now optional. Without it research still runs when `RESEARCH_BASE_URL` and `RESEARCH_MODEL_ID` are set. The model gets only `fetch_url` and reads the row Sources and the pages they link to. With a key, prompt, tools and cache are unchanged. Fetch-only rows use their own cache key.
- **Per-change research** runs after the filter and before the entity LLM. A small tool-calling model reads each filtered row, searches with Tavily, and fetches the cited pages. It writes a fact dossier (`runs/research/*-research.jsonl`) and does not write migration steps. The entity prompt receives those dossiers as a Research appendix and is told to prefer cited facts over memory.
- Filtered tables gain a `Sources` column (comma-separated source URLs, or `N/A`). The entity step copies the first of those URLs into `source_url`. Older filtered files without the column still parse.
- Research stays off unless `RESEARCH_BASE_URL` and `RESEARCH_MODEL_ID` are set (`TAVILY_API_KEY` only enables `web_search`). `--skip-research` leaves the entity input unchanged. `--force-research` ignores the row cache. A row that times out, exceeds its tool budget, or returns invalid JSON is passed through to the entity step unchanged.
- An exhausted Tavily quota (HTTP 432, 433, 401, or 429 after three attempts) stops that hop with exit code 2. Finished rows stay cached, and a re-run continues from the rows that were not finished. Fetches to private, loopback, or link-local addresses are refused.
- Error dossiers are not cached, so a model or Tavily outage does not hide rows from later runs. The research cache is keyed per framework and hop (prompt version 2). Using the full tool budget now yields a dossier instead of an error. Raw statements are attached by issue/PR/commit links and skip Source URLs shared by many rows (`RESEARCH_SHARED_URL_MAX_ROWS`, `RESEARCH_RAW_CONTEXT_MAX_CHARS`). The per-section entity split skips summary sections.
- Prompt review: the filter's `Sources` column now lists the issue/PR/commit/JIRA links inside each statement instead of the shared release-notes page; the triage input column is `Impact score`; `Category` maps explicitly to sections; split filter parts keep the framework header and omit summaries. The research prompt documents every dossier field and the hop's version lines (`PROMPT_VERSION` 3), and a row's own Sources are always trusted. The entity prompt explains research blocks and fills `subsystem` / `cli_operation` only for WildFly.
- `--stop-after-research` stops a run after the research stage (no entity LLM, no graph writes).
- Research now runs right after triage, on every kept row, and before the filter LLM. The filter LLM writes the migration document from the kept rows plus a Research appendix (blocks tied to rows by Sources), and the entity LLM receives that document plus the research merged per document row. `--stop-after-research` stops before the filter LLM, so it needs no `MODEL_*`. `MODEL_ID` is now required and checked only for steps that call the main LLM; `langchain-openai` is a dependency for `MODEL_PROVIDER=openai`.
- Triage and research show a `tqdm` progress bar per hop on a terminal (stderr; `keep/drop/error` and `ok/not_found/error/cached` counts). Bars are off when output is not a TTY or with `TQDM_DISABLE=1`.

### Changed

- Research budgets: `RESEARCH_MAX_TOOL_CALLS` defaults to `12` (was `6`) and `RESEARCH_TIMEOUT_SEC` to `240` (was `120`). The per-request model timeout is now its own setting, `RESEARCH_MODEL_TIMEOUT_SEC` (`60`), so one hung completion no longer consumes the whole row budget.

## [022-system1-change-triage] — 2026-11-04

### New features

- **System-1 change triage** runs after extraction and before the filter LLM. A fast local classifier (`TRIAGE_BASE_URL` + `TRIAGE_MODEL`, contract `POST /v1/systemone`) labels every raw row. Only rows that are confidently noise are dropped; low confidence, errors, timeouts, and an unreachable endpoint keep the row. With triage off, the raw file and the filter input stay the historical 4-column table.
- Raw files gain triage columns and a `Triage:` summary line. `runs/triage/*-triage.jsonl` stores full probability distributions so `--retriage-from-cache` can retune thresholds without another model call. `--skip-triage` and `--force-triage` control the stage. Answers are cached by questions version, model, and state.
- The filter prompt uses `Category` and `Impact` when those columns are present, and splits an oversized kept table into category groups.
- `runs/nodes/*.md` follows the kept rows. A `*.input.sha256` file next to it records the filter input. When triage changes which rows are kept, the cached filtered Markdown and entities JSON are regenerated instead of being silently reused.

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
