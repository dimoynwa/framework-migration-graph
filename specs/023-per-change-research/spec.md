# Feature Specification: Per-Change Research Before Step Generation

**Feature Branch**: `023-per-change-research`

**Created**: 2026-11-04

**Status**: Ready

**Scope**: Lightweight spec (no full SpecKit flow). New pipeline stage between filter and entity
extraction.

**Depends on**: `021-github-change-enrichment` (enriched raw statements), `022-system1-change-triage`
(kept-only filter input, filter-input cache invalidation FR-5.6).

## Problem

The entity LLM (`migration_oracle/pipeline/extractor.py`) receives the whole filtered Markdown
for a hop and must, in one call, research every change and write typed migration steps.

- `EXTRACTION_PROMPT` says **"INTERNET RESEARCH (mandatory)"**, but `get_llm()` binds no tools.
  The model cannot search, so "researched" instructions come from model memory. That is the
  main source of vague or invented steps.
- The filter output drops source URLs ("Do not include the original Source URLs"), so neither
  step can return to the issue, PR or commit behind a row.
- One call has to handle every row, so attention per change is low and the work requires a
  large frontier model.

Hops are now patch-level by default (`HOP_GRANULARITY=patch`, e.g. `3.5.0 → 3.5.1`). The
current major-hop artifacts hold about 30–90 filtered rows. A patch hop holds a handful. A call
per row is affordable.

## Goal

Split "find facts" from "write steps":

1. **Research (small model, per kept row).** Right after triage, for every row nimble kept, a
   small tool-calling model reads the row's sources and searches the web. It returns a **cited
   research dossier**: facts only, no steps.
2. **Migration document (filter LLM).** The filter LLM receives the kept rows plus their research
   and writes the consolidated document (sections, `Sources`, Summary by Priority). It decides
   sections and merges with facts instead of one-line titles.
3. **Step generation (entity LLM).** The entity LLM receives that document plus the research merged
   per document row and writes the graph entities.

```
extract ─▶ raw ─nimble triage─▶ kept rows ─research (per row, Qwen)─▶ runs/research/*.jsonl
                                    │                                        │
                                    └──────────▶ filter LLM ◀────────────────┘
                                                (rows + research)
                                                     │
                                                     ▼
                                        runs/nodes/*_filtered.md (migration document)
                                                     │
                                      entity LLM (document + merged research)
                                                     │
                                                     ▼
                                          runs/json/*-entities.json
```

Revised 2026-11-04: research originally ran after the filter LLM, on filtered rows. Moving it
before the filter lets the document be written from researched facts, and research starts from
each kept row's specific issue / PR / commit link instead of links the filter LLM copied.

## Key Principles

- **Facts, not steps.** The small model never writes migration steps. Every finding cites a
  URL it actually retrieved in this run. Uncited findings are discarded.
- **Fail toward today's behaviour.** Research off, failed or empty for a row → the entity LLM
  gets that row exactly as today. Research never removes a row.
- **"Not applicable" is a valid answer.** The dossier may say the change needs no user action;
  the entity LLM decides, research does not drop.

## Non-Goals

- Replacing the filter LLM (it still consolidates and dedups within a hop).
- Changing `MigrationEntity` / `MigrationStep` or graph population.
- Training or fine-tuning models.
- Using the System-1 classifier (`nimble`) for research: it returns distributions, not text.

---

## Requirements

### FR-1 Filter output keeps sources

- `FILTER_PROMPT` output tables gain a `Sources` column:
  `| # | JIRA | Title | Impact | Sources |`. `Sources` = comma-separated URLs that identify the
  specific change, for every raw row consolidated into that item: issue / PR / commit / JIRA links
  inside the `Statement` first, the row's `Source` URL only when the statement has none
  (`N/A` when no URL). Release-notes pages, release tags and changelog files are not listed when
  a specific link exists: most raw rows share one of those as `Source`. Replace the rule "Do not
  include the original Source URLs" with this one.
- `JIRA` keys are also taken from links inside the `Statement`; GitHub issue / PR numbers are not
  JIRA keys (they go to `Sources`).
- `EXTRACTION_PROMPT` maps the first `Sources` URL to `source_url` (today it is often empty).
- Old filtered files without `Sources` stay readable (research falls back to JIRA keys and the
  title).

### FR-2 Row model

- Research rows: `kept_rows(filter_md) -> list[FilteredRow]` (`research/rows.py`), one per kept
  triage row: `title` from the `Title:` prefix, `impact` = the statement (≤ 400 chars, links
  reduced to text, code fences removed), `sources` = issue / PR / commit / JIRA links in the
  statement (the row `Source` only when none), `jira_keys` from `/browse/` URLs, `section` = a
  hint from the triage `Category` (raw `Type` when untriaged). The filter LLM picks the final
  section.
- Document rows: `parse_filtered_markdown(md) -> list[FilteredRow]`: `section`, `index`,
  `jira_keys`, `title`, `impact`, `sources`.
- `row_key = sha256(section + title + sorted(jira_keys) + sorted(sources))`. The key does not
  depend on `#`, so reordering does not invalidate research.
- Raw context: the matching raw rows (`parse_raw_markdown`, statement enriched by 021) are
  attached to the research input. A raw row is indexed by its `Source` URL **and** by every URL
  inside its statement (issue, PR, commit, JIRA links).
  - Many raw rows share one `Source` (a release-notes wiki page, a release tag, Angular's
    `CHANGELOG.md`; e.g. 1470 of 2266 rows in `spring-boot-3.5.0-to-4.0.0`). A URL that
    identifies more than `RESEARCH_SHARED_URL_MAX_ROWS` (default 3) raw rows is not used for
    matching.
  - Attached statements are de-duplicated and capped at `RESEARCH_RAW_CONTEXT_MAX_CHARS`
    (default 8000) per row.

### FR-3 Research agent

- Module `migration_oracle/pipeline/research/` with
  `run_research(rows, framework, hop) -> list[ResearchDossier]`.
- Model: local vLLM, OpenAI-compatible `POST /v1/chat/completions` (verified 2026-11-04:
  `tools` + `tool_choice: auto` return `tool_calls`; `response_format: json_schema` returns
  valid JSON; `max_model_len` 262144; no auth needed today).

  | Variable | Default | Notes |
  |---|---|---|
  | `RESEARCH_BASE_URL` | `""` | e.g. `http://gpuserver2.neterra.skrill.net:8010/v1`; empty → research off. A trailing `/chat/completions` is stripped (both forms accepted) |
  | `RESEARCH_MODEL_ID` | `""` | e.g. `/models/Qwen3.6`; empty → research off |
  | `RESEARCH_API_KEY` | `""` | sent as `Authorization` only when set |
  | `RESEARCH_ENABLE_THINKING` | `false` | sent as `chat_template_kwargs.enable_thinking`. Verified with `true`: tool calls and json_schema both work, ~8–15 s per turn vs ~1–3 s without |
  | `RESEARCH_MAX_CONCURRENT` | `4` | |
  | `RESEARCH_MAX_TOOL_CALLS` | `8` | per row |
  | `RESEARCH_TIMEOUT_SEC` | `120` | per row |
  | `TAVILY_API_KEY` | `""` | optional. Empty → research runs **fetch-only** (no `web_search`, see FR-3.2) |

  Client: LangChain `ChatOpenAI(base_url=…, model=…, extra_body={"chat_template_kwargs": …})`,
  non-streaming. The final dossier is requested with `response_format: json_schema` (FR-4).
- `RESEARCH_BASE_URL` normalisation: the OpenAI client appends `/chat/completions` itself, so
  the setting is the API root. A value ending in `/chat/completions` (or `/chat/completions/`)
  is trimmed to the root once at load time, with one DEBUG line.
- Tools (tool-calling loop):
  - `web_search(query)` → Tavily Search, top `RESEARCH_SEARCH_RESULTS` (default 5)
    `{title, url, snippet}`. Results cached in `ARTIFACT_CACHE_DIR/research/search/`.
  - `fetch_url(url)` → readable text (HTML stripped, capped at `RESEARCH_FETCH_MAX_CHARS`,
    default 20k). Any public URL is allowed. GitHub URLs go through the 021 GitHub client
    (token, cache). Guard: URLs resolving to private, loopback or link-local addresses are
    refused, so page content cannot steer the agent into the internal network.
  - Fetched pages and search snippets are untrusted data: the system prompt tells the model
    to ignore instructions found in them.
- Budget per row: `RESEARCH_MAX_TOOL_CALLS` (default 8), `RESEARCH_TIMEOUT_SEC` (default 120).
  The model may return several `tool_calls` in one turn; each one counts against the budget.
  Using the budget exactly is not an error: the loop stops and requests the final dossier.
  A turn that asks for more calls than the budget has left is dropped (not executed) and the
  loop finalizes with the pages already fetched; it is not an error. After each tool turn the
  last tool message gets a `[System: n/budget tool calls used, k left …]` note so the model
  stops early (measured on Spring Boot 3.2.0→3.2.1 before this: every row used the full budget).
- The final dossier call appends a user message asking for the JSON dossier now. The model's
  last text answer (if any) is kept in the conversation. `row_key`, `model` and
  `prompt_version` are not in the response schema; the code sets them.
  Concurrency `RESEARCH_MAX_CONCURRENT` (default 4).
- Search priority in the prompt: row sources → official migration guide / release notes for
  the hop → API docs (Javadoc / TypeDoc) → GitHub issues/PRs → Stack Overflow.
- **Version anchoring**: every `web_search` query contains the framework name and the hop
  target version (`<Framework> <to_version>`). The tool wrapper appends it when the model
  omits it. Each `sources_used` entry records `version_match` (`true` when the page is for
  the hop's major.minor line or is version-neutral, e.g. an issue or PR). Findings sourced
  only from a `version_match = false` page are dropped.

#### FR-3.1 Tavily quota exhausted → stop the run

This is the one exception to fail-open: an exhausted quota would silently degrade every
remaining row.

- Tavily `432` (plan usage limit) or `433` (pay-as-you-go limit), or a `401` for the key → raise
  `ResearchQuotaExceeded`. `429` (rate limit) is retried with backoff (3 attempts), then treated
  the same way.
- On `ResearchQuotaExceeded`: in-flight rows are cancelled; dossiers already finished are kept
  in the row cache; nothing is written for the current hop (no `research.jsonl`, no entity LLM
  call, no graph write). Hops completed earlier keep their artifacts.
- The CLI exits with code `2` and one ERROR line:
  `Tavily quota exhausted at <framework> <from>→<to> (<done>/<total> rows researched). Re-run
  after the quota resets; finished rows are cached.`
- Re-running resumes: cached rows make no calls, the hop continues from the missing rows.

#### FR-3.2 Fetch-only mode (no `TAVILY_API_KEY`) — amendment 2026-11-05

- With an empty `TAVILY_API_KEY` research still runs. The model is offered only `fetch_url`;
  no Tavily client is built and FR-3.1 cannot trigger.
- The system prompt replaces the search rules with: start from the row's Sources, follow links on
  fetched pages (migration guide, release notes, API docs, issues/PRs), and build a URL only for an
  official page whose address is certain (e.g. the GitHub release tag of the target version).
  All other prompt rules are unchanged.
- A `web_search` call in this mode returns `web_search is not available; use fetch_url.` and
  counts against the budget.
- The row cache key gets `search=off`, so fetch-only and Tavily dossiers never share rows. The
  Tavily-mode key, prompt and tools are byte-for-byte unchanged, so existing caches stay valid.
- One INFO line per process: `Research without web search (TAVILY_API_KEY is empty) …`.

### FR-4 Dossier (free-text description, no JSON schema)

> Changed in prompt version 5. The dossier used to be a strict JSON schema (`findings`,
> `applicability`, `applies_when`, `sources_used`) requested with `response_format`. Every
> field was only rendered back to text for the filter and entity LLMs, and the strict final
> request was the main source of errors (14/23 `ReadTimeout` on Spring Boot 3.2.0→3.2.1).

The research model answers in Markdown. Its last turn without tool calls **is** the
description; only when the budget runs out (or it stopped without text) does the code send one
more request, still without `response_format`. The description covers: what changed (exact
identifiers copied from the pages), who is affected, whether upgrading applications must do
anything (stated explicitly, or "no user action is needed", or "unclear from the sources"),
short before/after snippets, inline source URLs. `NOT_FOUND` means nothing usable.

Fixed answer format (prompt version 6), appended to the row's Summary, so it must not repeat it;
about 200 words at most plus the snippet:

```
**What changed:** <old → new, exact identifiers> (<url>)
**Affects:** <conditions, or "all applications">
**Action:** <required: … | none | unclear from the sources>
**Before/after:**            (omitted when no page has a snippet)
<fenced snippet copied from a page, ≤ 30 lines>
```

Prompt version 7 tightens three rules after the first full run (3.2.0→3.2.1): the upgrade
itself is never the action; every identifier in **Action:** must appear verbatim in a fetched
page (the run had `<layout>CLASSIC</layout>` where the pages say
`<loaderImplementation>CLASSIC</loaderImplementation>`, and an unsourced `hibernate.version`
override); **Before/after:** is code or configuration only, not release-note or log text.

`summary.json` counts the `**Action:**` line of ok dossiers as
`action: {required, none, unclear, missing}` (`missing` = format not followed). Nothing branches
on it; the filter prompt reads `**Action:** none` as a drop signal.

```json
{
  "row_key": "…",
  "status": "ok | not_found | error",
  "text": "Markdown description written by the model",
  "sources": ["https://… fetched pages cited in text (all fetched pages if none cited)"],
  "model": "…", "prompt_version": 7,
  "error": "", "error_tool_calls": 0
}
```

Grounding is done by the code, not by a schema:
- URLs in `text` that were not fetched in this run are removed (a Markdown link keeps its label).
- `sources` is written by the code from the fetched set.
- Empty text, `NOT_FOUND`, or nothing fetched → `not_found`. `<think>` blocks are stripped.
- The per-fact "other version line" filter is gone; it is now a prompt rule.
- The filter and entity research blocks render `text` plus a `Fetched sources:` list. The filter
  prompt drops a row when its `**Action:**` line is `none` (was `Applicability: no_action`).

- Errors and timeouts → `status = "error"`, empty text (fail open). Error
  dossiers are **not cached** (they are usually transient: model or Tavily outage, timeout), so
  the next run researches the row again.
- The row cache key also includes `enable_thinking`, so thinking and non-thinking runs
  never share cached dossiers. (Adding it invalidated cache entries written before.)
- Error dossiers carry `error` (`"<stage>: <ExceptionType>: <message>"`, capped at 2000 chars,
  e.g. `final description request: RuntimeError: research model ReadTimeout after 120s (…)`,
  `timeout: …`) and `error_tool_calls`. Both are set by the code, never by the model. `summary.json` adds `errors`: counts per
  error category. Each error is also logged at WARNING with the row title.

### FR-5 Artifacts and cache

- **New folder `runs/research/`** (added to `ensure_runs_directories`):
  - `runs/research/<framework>-<from>-to-<to>-research.jsonl`: one dossier per kept triage row, in
    raw order. Human-readable source of truth for this stage.
  - `runs/research/<framework>-<from>-to-<to>-summary.json`: counts per status / applicability,
    tool calls, wall time.
- Row cache: `ARTIFACT_CACHE_DIR/research/sha256(prompt_version + model + framework_key + from +
  to + row_key)`. Framework and hop are part of the key because dossiers are anchored to the hop
  target version, and rows without Sources and JIRA keys share a `row_key`. Re-runs and a changed
  filtered file research only new or changed rows. Only `ok` / `not_found` dossiers are cached.
- Flags: `--skip-research` (entity step exactly as today), `--force-research` (ignore cache and
  existing `.jsonl`).
- Gating like 022 FR-5.5: research runs only when `RESEARCH_BASE_URL` and `RESEARCH_MODEL_ID`
  are set. Otherwise one INFO line, no research, no `runs/research/` file. `TAVILY_API_KEY` only
  decides whether `web_search` is offered (FR-3.2).

### FR-5.1 Prompt contracts (review 2026-11-04)

- **Filter prompt**: no stray `Developer:` prefix. The triage input column is `Impact score`
  (0–3 effort estimate, used only to order items), distinct from the output `Impact` text. An
  explicit `Category` → section mapping. When the kept table is split into category groups, each
  part keeps the document preamble (framework, range) and is told not to emit `Summary by
  Priority` / `Most Critical Items`. Substitution is plain `str.replace`, never `str.format`.
- **Research prompt** (`PROMPT_VERSION` 3): field guide for `status`, `applicability`, every
  finding `kind`, `old`/`new`, `applies_when`, `version_match`. The request carries
  `Version lines` (major.minor lines from the hop start to its target). A finding cited from a
  fetched row Source is kept regardless of `version_match`.
- **Entity prompt**: explains that `### <section> #<n> — <Title>` research blocks are evidence for
  that row and never entities; summary sections are not entities; "source text" rules read "the
  row and its research block". `subsystem` / `cli_operation` rules depend on the framework
  (filled for WildFly, empty otherwise).

### FR-5.3 (removed) Pluggable filter step

Removed the same day: research now always runs on the kept rows, so a filter mode that only
turned kept rows into filtered rows is redundant. The former text is kept below for history.

<details><summary>Former FR-5.3</summary>


`FILTER_MODE` (`--filter-mode` wins) selects the filter implementation; both write the same
`| # | JIRA | Title | Impact | Sources |` contract to `runs/nodes/*_filtered.md`:

| Mode | Behaviour |
|---|---|
| `llm` (default) | Today's filter LLM: consolidates related rows, dedups, rewrites `Title`/`Impact`, adds the summary sections. Needs `MODEL_*`. |
| `deterministic` | No LLM. One filtered row per kept row. Section from the triage `Category` (`breaking` → 🔴, `security` → 🟠 Security & CVE, `dependency_upgrade` → 🟠 Major Component, `behavior_change` / `config_change` → 🟡 Behavioral, `deprecation` → 🟡 Deprecations, `new_optional_feature` → 🔵, anything else → 🟡 Behavioral), or from the raw `Type` when untriaged. `Title` from the `Title:` prefix, `Impact` = the statement (links reduced to text, code fences removed, ≤ 600 chars), `Sources` = issue / PR / commit / JIRA links (the row `Source` only when none), JIRA keys from `/browse/` URLs. Rows ordered by `Impact score` within a section. No summary sections. |

- Trade-off: `deterministic` makes no filter LLM call and keeps every triaged row, but research
  and the entity step see more, unconsolidated rows (Spring Boot 3.2.0 → 3.2.1: 37 rows).
- The filter sidecar digest includes the mode (the `llm` digest is unchanged for compatibility),
  so switching modes regenerates the filtered file, the research rows that changed, and the
  entities.
- `MODEL_*` is validated only for steps that call it: `deterministic` + `--stop-after-research`
  needs no main LLM.

</details>

### FR-5.4 Research feeds the filter LLM

- Filter input = the kept-row table + a `## Research` appendix (`FilterResearch`): one block per
  `ok` dossier, `### <Title>`, `Row sources: …`, `Applicability: …`, summary, cited findings,
  `applies_when`. Blocks are tied to rows by Sources; a split (category-group) filter call gets
  only the blocks of its rows.
- `FILTER_PROMPT` explains the appendix: blocks are evidence, never items on their own; use them
  for the section (`no_action` + a confirming statement is a strong reason to drop), for
  merging, and for exact names in `Impact`. `Impact` names exact APIs only when the statement or
  the research states them.
- The filter sidecar digest covers table + appendix, so a changed dossier regenerates the
  document and the entities.
- Entity input: the document + `## Research` blocks per document row, built by
  `dossiers_for_filtered_rows`: the dossiers of every kept row sharing a `Sources` URL with the
  document row, merged (findings, `applies_when`, sources; `action_required` wins).
- A Tavily quota exit happens before the filter LLM, so a stopped hop writes no filtered file.

### FR-5.2 Stop after research

`--stop-after-research` runs extraction, triage and research, then stops: no filter LLM, no
entity LLM call and no graph writes, so `MODEL_*` is not needed. It requires research to be configured and cannot be
combined with `--extract-only` or `--skip-research`.

### FR-6 Entity step consumes dossiers

- `run_extraction` input = filtered Markdown + a `## Research` appendix: one block per document
  row (`### <section> #<index> — <title>`), containing `Applicability`, the merged dossier
  summary, findings with their URLs, and `applies_when` (FR-5.4). Rows without an `ok` merged
  dossier get no block.
- `EXTRACTION_PROMPT`: replace the "INTERNET RESEARCH (mandatory)" section with:
  *"Use the Research appendix as your evidence. Prefer its cited facts over memory. Do not invent
  APIs, properties or coordinates absent from the row and its research. When research says
  `no_action`, emit the entity with no steps unless the row text clearly requires one."*
- Entity cache follows its input (same mechanism as 022 FR-5.6): a sidecar
  `*-entities.json.input.sha256` over filtered Markdown + appendix. A changed dossier
  regenerates the entities JSON.
- If the combined input exceeds `ENTITY_MAX_INPUT_TOKENS` (default 60k), run the entity LLM per
  filtered section and concatenate `entities`. Only sections with a `Title | Impact` change table
  are sent; `Summary by Priority` and `Most Critical Items` restate other rows and would produce
  duplicate entities.

---

## Acceptance Criteria

**Unit (fake model, fake tools)**

1. **AC-1** Filter output with `Sources` parses into `FilteredRow`s. A file without `Sources`
   parses with empty `sources`.
2. **AC-2** `row_key` is stable when only `#` changes and changes when sources change.
3. **AC-3** A finding citing a URL that was not fetched, or only a `version_match = false`
   page, is dropped. A search query without the hop version gets it appended. `fetch_url` to
   `127.0.0.1` / `10.x` / `169.254.x` is refused. A dossier made only of
   such findings ends with `status = "not_found"`.
4. **AC-4** Tool budget exceeded / timeout / invalid JSON → `status = "error"`, the row still
   reaches the entity step unchanged.
5. **AC-5** Research not configured or `--skip-research` → no model or tool calls. The entity
   prompt input is byte-for-byte today's.
5b. **AC-5b** Fake Tavily returns `432` on the 3rd search → exit code 2, the ERROR line above,
   no `research.jsonl` / entities for that hop, earlier hops intact. Re-run with a working fake
   makes calls only for rows not cached.
5c. **AC-5c** `RESEARCH_BASE_URL=…/v1/chat/completions` and `…/v1` produce the same request URL.
5d. **AC-5d** Review regressions (`tests/pipeline/test_research_review_fixes.py`): error
   dossiers are re-researched on the next run; the cache is per framework and hop; using the
   tool budget exactly yields a dossier; a shared Source URL attaches no unrelated raw rows;
   the section split skips summary sections.
6. **AC-6** Second run: zero research calls. Changing one kept row → exactly one research
   call, and the entities JSON is regenerated.

**Quality**

7. **AC-7** On one patch range per framework (Angular 19.x, Spring Boot 3.5.x, WildFly 3x),
   compared manually with today's entities:
   - ≥ 80% of `breaking` / `deprecation` / `mandatory_migration` steps name an exact class,
     property or coordinate backed by a cited source;
   - no entity present today is lost;
   - zero steps reference an API that the cited source does not mention (spot check of 20).
8. **AC-8** With research on, the entity step produces AC-7 quality with a smaller model
   (`MODEL_ID` one tier down) than today's frontier default. Record both runs.

**Performance (informational)**

9. **AC-9** `summary.json` records research wall time and tool calls per hop.

## Implementation Notes

- Files: `migration_oracle/pipeline/research/{__init__,agent,tools,schema,run}.py`,
  `migration_oracle/pipeline/_paths.py` (`RUNS_RESEARCH`, path helpers),
  `migration_oracle/pipeline/filters.py` (prompt `Sources` column),
  `migration_oracle/pipeline/extractor.py` (appendix, prompt, input digest),
  `migration_oracle/config.py` (`RESEARCH_*`), `migration_oracle/cli.py` (flags, wiring).
- Tests: `tests/pipeline/test_research_*.py` with `FakeResearchModel` and fake tools.
- Docs: "Research" phase in `docs/02-extraction-pipeline/export-extract-populate-framework-pipeline.md`,
  `CHANGELOG.md`, `.env.example` `RESEARCH_*`.

## Open Questions

1. ~~Small model~~ — resolved: `/models/Qwen3.6` on `gpuserver2:8010` (vLLM), tool calling and
   json_schema verified 2026-11-04.
2. ~~Search provider~~ — resolved: Tavily (`TAVILY_API_KEY`).
3. ~~Fetch allowlist~~ — resolved: any public URL; only private/internal addresses are refused.
4. ~~Version anchoring~~ — resolved: yes, see FR-3.
5. ~~Tavily quota~~ — resolved: an exhausted quota stops the run (FR-3.1); re-runs resume from
   the cache.

## Estimate

~3 days:

| Work | Effort |
|---|---|
| Filter `Sources` column + filtered parser + row key | 3 h |
| Tools (fetch, search adapter) + agent loop + schema validation | 6 h |
| Cache, artifacts, flags, gating | 3 h |
| Entity appendix, prompt, input digest, per-section split | 3 h |
| Tests | 4 h |
| Quality run (AC-7/AC-8) on three patch ranges | 4 h |
| Docs | 1 h |
