# Feature Specification: Graph Entities from Research Dossiers (No Filter LLM)

**Feature Branch**: `024-dossier-entities`

**Created**: 2026-11-05

**Status**: Draft

**Scope**: Lightweight spec (no full SpecKit flow). Replaces the filter LLM step between research
and entity extraction when research is enabled.

**Depends on**: `022-system1-change-triage` (kept rows, `Category`, thresholds),
`023-per-change-research` (dossiers in `runs/research/*-research.jsonl`, `**Action:**` line).

## Problem

Since 023, every kept row has a research dossier with `**What changed:**`, `**Affects:**`,
`**Action:**` and an optional `**Before/after:**` snippet, all cited from fetched pages. The filter
LLM then reads the kept table plus all dossiers and writes `runs/nodes/*_filtered.md`. After that
the entity LLM reads that document plus the dossiers again.

Measured on the Angular artifacts (2026-11-05):

- **The filter adds little the graph uses.** The graph stores per rule: `title`, `change_type`,
  `reason`, `scopes`, `entities` (class / property / dependency + role) and `steps`. Rules are
  not linked to each other directly. `REQUIRES` is step → step inside one rule, `REPLACED_BY`
  is built from one rule's own `removed` / `replacement` entities, and rules meet only through
  shared entity nodes merged by name. The filter's outputs map as follows:
  - noise removal: already given by `**Action:** none`
  - section: triage `Category` + `Action`; the entity LLM reassigns `change_type` anyway
  - one-line `Impact`: a lossy copy of `What changed` / `Affects`
  - `Summary by Priority` / `Most Critical Items`: skipped by the entity step
  The only cross-row work is **consolidation** (several rows describing one change).
- **The filter input is too large and is split badly.**
  - 19.0.0 → 20.0.0: 364 kept rows, 361 dossiers. The prompt is split into 4 parts of
    37k / 150k / 8k / 154k tokens, against `FILTER_MAX_INPUT_TOKENS` = 60k.
  - The size check runs on the table before the research appendix is added.
  - `FilterResearch.appendix` attaches a block when any of its row Sources appears in the chunk.
    `…/main/CHANGELOG.md` is the Source of 40 kept rows, so a 27-row chunk carried 62 blocks.
- **Split outputs are concatenated, not merged.** The parts lose the summary sections. A section
  can be repeated when the model overrides a category. Deduplication runs only inside one call.
  `build_extraction_input` keys research blocks by section heading, so a repeated heading gets
  the blocks of both copies.
- **Most kept rows end as `**Action:** none`.** In 19.0.0 → 20.0.0 that is 198 of 364 rows. Of
  the 61 kept `internal_fix` rows across six hops, 51 are `none`. They are paid for twice: once in
  the filter input, once in the entity input.

## Goal

Build graph entities from the dossiers directly, one small entity call per **change cluster**:

```
kept rows ─research─▶ dossiers ─gate (FR-1)─▶ actionable rows ─cluster (FR-2)─▶ clusters
                                                                                 │
                                         entity LLM, one call per cluster (FR-3) ◀┘
                                                         │
                     runs/json/*-entities.json  +  rendered runs/nodes/*_filtered.md (FR-5)
```

Measured cluster counts with FR-1 and FR-2 on existing artifacts:

| Hop | Kept | After gate | Clusters | Largest | Today's entities |
|---|---|---|---|---|---|
| 19.0.0 → 20.0.0 | 364 | 163 | 125 | 11 (see FR-2.3) | — |
| 20.0.0 → 20.1.0 | 36 | 10 | 10 | 1 | — |
| 20.3.0 → 21.0.0 | 108 | 68 | 54 | 3 | 43 for 20.0.0 → 21.0.0 |
| 21.2.0 → 22.0.0 | 146 | 68 | 66 | 2 | 43 for 21.0.0 → 22.0.0 |

Each entity call sees 1–4 dossiers (~2–8k tokens). No call needs splitting, and calls run in
parallel.

## Key Principles

- **Dossier is the evidence.** The entity call gets the member rows and their dossiers. It gets
  nothing else from the hop, so it cannot borrow facts from unrelated rows.
- **Deterministic before LLM.** Dropping and clustering are code with logged reasons. An LLM
  is used only to write the entity.
- **Fail toward keeping.** Ambiguous action, missing dossier or research error never silently
  removes a row (FR-1, FR-4).
- **Same output contract.** `MigrationEntitiesBatch` / `MigrationEntity`, the populator and the
  graph schema do not change. `runs/nodes/*_filtered.md` still exists for `Version.filteredMdPath`
  and the MCP `artifacts` tool.

## Non-Goals

- Changing the graph schema, `MigrationEntity` or the populator.
- Cross-hop deduplication (the same change in a minor hop and in a major range).
- Changing the research stage or its prompt (023).
- Removing the filter LLM code: it stays as the path for runs without research (FR-6).

---

## Requirements

### FR-0 Triage drop threshold

- The default for `TRIAGE_DROP_MAX_ACTION_PROB` changes from `0.10` to `0.20` in
  `triage/settings.py` and `.env.example`.
- On the saved Angular distributions this drops 23 more rows: 12 `new_optional_feature`,
  10 `internal_fix` and 1 `noise`.
- Applied to existing raw files with `--retriage-from-cache`.

### FR-1 Action gate

The gate runs after research, per kept row, using its dossier and triage columns.

| Dossier | Triage `Category` | Decision |
|---|---|---|
| `ok`, `**Action:** none` | `internal_fix`, `noise`, `new_optional_feature`, `behavior_change`, `config_change`, `dependency_upgrade`, `—` (rule-kept) | **drop** (`research_none`) |
| `ok`, `**Action:** none` | `breaking`, `deprecation`, `security` | keep |
| `ok`, `required` / `unclear` / `missing` | any | keep |
| `not_found` / `error` / no dossier | any | keep, marked `evidence: row_only` (FR-4) |

- Protected categories are kept even when the dossier says `none`, because a wrong `none` there
  is costly. On Angular that is 12 `breaking` and 2 `security` rows. The entity call decides,
  and may return no entity (FR-3.4).
- Rule-kept rows (`Triage source = rule`, `Category` = `—`) with `none` are dropped. On Angular
  these are 51 rows, mostly `fix(migrations): …` fixes to schematics.
- Every decision is written to the cluster artifact (FR-5) with its reason.
- `GATE_PROTECTED_CATEGORIES` (default `breaking,deprecation,security`) overrides the protected
  set.

### FR-2 Clustering

Rows that describe the same change are grouped so that they produce one entity.

#### FR-2.1 Specific URLs

A URL is **specific** when it matches `/pull/`, `/commit/`, `/issues/`, `/browse/<KEY>` or a
`/compare/` anchor of one change. Release pages (`/releases/tag/`), `CHANGELOG.md`, docs and blog
pages are never specific. URLs are compared after `normalize_url`. GitHub pull, commit and issue
URLs collapse to `https://github.com/<owner>/<repo>/<kind>/<id>` (lower-case), so `.patch`, `.diff`,
`/files`, `/commits/<sha>` and `patch-diff.githubusercontent.com/raw/…` variants meet the plain
URL (review 2026-11-05: ~160 fetched sources on Angular were such variants).

#### FR-2.2 Edges

Two kept rows A and B are linked when a specific URL is in A's **row sources** and in B's row
sources **or** B's dossier `sources`. In plain terms: B's research fetched the PR, commit or
issue that A comes from. Clusters are the connected components (union-find), in raw order.

#### FR-2.3 Size cap

- A component larger than `CLUSTER_MAX_ROWS` (default 4) is split back using row-source edges
  only. Whatever is still larger stays split into single rows.
- The 11-row component in 19.0.0 → 20.0.0 is such a chain. It joins rows through one widely
  fetched PR.
- The split is logged with the URLs that caused it.

#### FR-2.4 Optional merge check

- `CLUSTER_CONFIRM=llm` (default `off`) sends each multi-row cluster to the research model with
  only titles plus `What changed` lines. The model answers `same` or `split`.
- `split` breaks the cluster into single rows.
- Off by default until AC-7 shows over-merging.

#### FR-2.5 Cluster key

`cluster_key = sha256(sorted(member row_key))`. It is stable while membership is unchanged.

### FR-3 Entity extraction per cluster

#### FR-3.1 Input

One request per cluster:

```
Framework: <display> · Hop: <from> → <to>
Triage: <Category>, impact <score>        (per member)

## Row <n>
Type | Source | Statement                (the kept row, links kept)
Research:
<dossier text>
Fetched sources:
- <url>
```

Rows marked `row_only` (FR-4) have no `Research:` part.

#### FR-3.2 Prompt

The prompt is `DOSSIER_ENTITY_PROMPT`, derived from `EXTRACTION_PROMPT`. It keeps the field
rules (`source_section`, `change_type`, `reason_type`, `scopes`, `entities`, `steps`,
`subsystem` / `cli_operation` per framework). It replaces the document and appendix wording with:

- *"All rows below are one change. Produce at most one entity."*
- *"Use only identifiers that appear in the rows or their research. Prefer `**Before/after:**`
  snippets for `instruction`."*
- *"When the research says `**Action:** none` and the row text does not require action, return
  `{"entities": []}`."*

#### FR-3.3 `source_section`

The model chooses `source_section`. The prompt gives the default mapping from the triage
`Category`, the same as the former filter mapping: `breaking` → `breaking_change`, `security` →
`security_fix`, `dependency_upgrade` → `component_upgrade`, `config_change` / `behavior_change` →
`behavioral`, `deprecation` → `deprecation`, `new_optional_feature` → `new_capability`. The model
may override the default when the research contradicts it.

#### FR-3.4 Output

- The output is `MigrationEntitiesBatch` with 0 or 1 entities. More than one is a validation
  error and is retried once.
- `source_url` is the first specific row source of the cluster, otherwise the first row source.
- `jira_keys` is the union of the members' keys.

#### FR-3.5 Model and concurrency

- `MODEL_*`, as today. `ENTITY_CONCURRENCY` (default 4) sets the parallel calls.
- `invoke_with_retry` is reused.
- A cluster that still fails after retries is logged, written to the cluster artifact with
  `status: error`, and left out of the entities file. Other clusters continue. The hop exits
  non-zero only when every cluster failed.
- Amended 2026-11-05 (review): a hop with **any** failed cluster still writes its artifacts but is
  **not populated**, because an existing `Version` node is never repopulated and the missing rules
  could not be added later. `ExtractionResult.failed_clusters` carries the count; the CLI skips
  `populate_graph` for that hop, continues with the next hops, and exits 3 at the end. A re-run
  retries only the failed clusters (the rest are cached).

#### FR-3.6 Title uniqueness

`ruleId` is `pipeline://<framework>/<to>/<title>`. When two entities of one hop share a title,
the later one gets ` (<first specific URL tail>)` appended, so `MERGE` does not fold distinct
changes together. The rename is logged.

### FR-4 Rows without research

- Rows with `not_found`, `error` or no dossier form their own clusters (FR-2 still applies by
  row sources), with `evidence: row_only`.
- The prompt tells the model: *"No research is available; use only the row text; leave steps
  empty unless the row names the exact identifiers to change."*
- `summary.json` counts these clusters.

### FR-5 Artifacts and cache

- **`runs/clusters/<framework>-<from>-to-<to>-clusters.jsonl`**: one line per kept row, with
  `row_key`, gate decision and reason, `cluster_key`, `evidence`. A second record type per
  cluster holds members, the entity title or `null`, and `status`. Human-readable audit trail
  for FR-1 and FR-2.
- **`runs/clusters/…-summary.json`**: rows per gate reason, cluster size histogram, entities
  written, empty results, errors, wall time, model.
- **`runs/json/…-entities.json`**: unchanged format. Entities follow cluster order, which is the
  raw order of their first member.
- **`runs/nodes/…_filtered.md`**: rendered by code from the entities. One section per
  `source_section` in the existing order and headings, a `| # | JIRA | Title | Impact | Sources |`
  table, `Impact` = first sentence of `reason`, `Sources` = member row sources. No summary
  sections. The file stays readable and keeps `filteredMdPath` working.
- **Per-cluster cache**: `ARTIFACT_CACHE_DIR/entities/sha256(DOSSIER_ENTITY_PROMPT_VERSION + model
  + framework_key + hop + cluster_key + member material)`. Member material is everything
  `render_cluster_input` sends: triage category and impact, type, source, statement, dossier
  status, text and sources (review 2026-11-05: a re-triage can change the category while `row_key`
  stays the same). A changed dossier or membership
  re-runs only that cluster. Error results are not cached.
- `entities.json` gets an `.input.sha256` sidecar over all cluster cache keys, for inspection.
  Zero entity calls on a re-run come from the per-cluster cache.
- A dossier run deletes `_filtered.md.input.sha256`. Otherwise a later `--entity-source filter` run
  with unchanged kept rows would treat the rendered document as filter LLM output and skip the
  filter call (review 2026-11-05).

### FR-6 Mode selection and CLI

- `ENTITY_SOURCE` = `dossier` | `filter` (env), overridden by `--entity-source`.
- Default is `dossier` when research is enabled and not skipped, otherwise `filter`.
- `filter` is today's path: filter LLM, then the entity LLM on the document. It is byte-for-byte
  unchanged.
- `--skip-research` forces `filter`. `--entity-source dossier --skip-research` is an error.
- `--stop-after-research` is unchanged.
- New `--stop-after-clusters`: runs gate and clustering, writes `runs/clusters/`, makes no
  entity calls and no graph writes, and needs no `MODEL_*`.
- `--force-llm` in `dossier` mode ignores the per-cluster cache.

---

## Acceptance Criteria

**Unit (fake model)**

1. **AC-1** Gate: `none` + `internal_fix` → drop. `none` + `breaking` → keep.
   `unclear` / `missing` → keep. `not_found` → keep with `row_only`. Each decision is written
   with its reason.
2. **AC-2** Clustering:
   - Two rows whose row sources share a PR URL → one cluster.
   - Two rows sharing only `CHANGELOG.md` or a release tag → two clusters.
   - Row B's dossier fetched row A's commit → one cluster.
   - A 6-row chain with `CLUSTER_MAX_ROWS=4` → split, and the split is logged.
3. **AC-3** One call per cluster. A fake returning two entities is retried once, then the
   cluster gets `status: error`. Other clusters are still written.
4. **AC-4** Duplicate titles in one hop get distinct `ruleId`s (FR-3.6).
5. **AC-5** Second run: zero entity calls. Changing one dossier → exactly one entity call, and
   `entities.json` plus `_filtered.md` are rewritten.
6. **AC-6** `--entity-source filter`, or research disabled → prompts and outputs are
   byte-for-byte the 023 path. `--stop-after-clusters` → no `MODEL_*` needed, no entity calls.
   `--entity-source dossier --skip-research` → usage error.

**Quality**

7. **AC-7** On Angular 20.0.0 → 20.1.0 and 20.3.0 → 21.0.0, compared manually with the
   `filter` path run on the same dossiers:
   - every `breaking` / `deprecation` / `mandatory_migration` entity of the `filter` path has a
     counterpart in `dossier` mode, or the cluster audit shows why not;
   - spot check of 20 multi-row clusters: ≥ 18 are truly one change, and no single-row cluster
     pair is an obvious duplicate;
   - ≥ 80% of steps in those sections name an identifier present in the cluster's dossiers;
   - zero steps reference an API absent from the cluster input (spot check of 20).
8. **AC-8** Input tokens summed over entity calls are lower than filter + entity input tokens
   for the same hop. Record both, plus wall time.

## Implementation Notes

- New package `migration_oracle/pipeline/entities/`:
  - `gate.py` (FR-1)
  - `clusters.py` (FR-2)
  - `prompt.py` (`DOSSIER_ENTITY_PROMPT`, version)
  - `run.py` (calls, cache, artifacts)
  - `render.py` (`_filtered.md`)
- `migration_oracle/cli.py`: `_research_filter_extract` branches on `ENTITY_SOURCE`, plus the new
  flags. `_paths.py`: `RUNS_CLUSTERS` and its path helpers.
- Reuse `ResearchDossier`, `action_of`, `normalize_url`, `kept_rows`, `attach_raw_context`, and
  `MigrationEntitiesBatch` validation from `extractor.py`.
- Tests: `tests/pipeline/test_dossier_entities_*.py` with a fake LLM.
- Docs: new phase in `docs/02-extraction-pipeline/export-extract-populate-framework-pipeline.md`
  (filter phase marked as the `filter` mode path), `CHANGELOG.md`, and `.env.example`
  (`ENTITY_SOURCE`, `ENTITY_CONCURRENCY`, `CLUSTER_MAX_ROWS`, `CLUSTER_CONFIRM`,
  `GATE_PROTECTED_CATEGORIES`, new `TRIAGE_DROP_MAX_ACTION_PROB` default).
- The 023 filter-chunk research leak (Sources-based block matching, size check before the
  appendix) only affects `filter` mode. It is tracked separately and is not fixed here.

## Open Questions

1. Should `behavior_change` with `**Action:** none` be protected too? It is the largest dropped
   group: 156 rows on Angular. The AC-7 spot check decides.
2. Is `CLUSTER_MAX_ROWS=4` right for Spring Boot and WildFly? There, one JIRA issue often has a
   PR, a forward port and a release note. Check on one hop each before the default is final.
3. Should the entity call use the research model (Qwen) instead of `MODEL_*`? Inputs are now
   small enough. Answer with an AC-8-style comparison after AC-7 passes with `MODEL_*`.

## Estimate

~2.5 days:

| Work | Effort |
|---|---|
| Gate + clustering + cluster artifact + `--stop-after-clusters` | 4 h |
| Dossier entity prompt, per-cluster calls, cache, concurrency | 5 h |
| `_filtered.md` renderer, title uniqueness, mode wiring | 3 h |
| Tests | 4 h |
| Quality run (AC-7/AC-8) on two Angular hops | 3 h |
| Docs, `.env.example`, triage default | 1 h |
