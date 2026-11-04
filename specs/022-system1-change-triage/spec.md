# Feature Specification: System-1 Change Triage Before the Filter LLM

**Feature Branch**: `022-system1-change-triage`

**Created**: 2026-11-04

**Status**: Draft

**Scope**: Lightweight spec (no full SpecKit flow). New pipeline stage between extract and filter.

**Depends on**: `021-github-change-enrichment` (enriched statements and metadata give the
classifier enough signal per row).

## Problem

`run_filter` (`migration_oracle/pipeline/filters.py`) sends the **entire raw Markdown file in a
single LLM call**, which must filter noise, consolidate, deduplicate and rewrite at once:

| Raw file | Rows | ~Tokens |
|---|---|---|
| angular 19→20 (enriched) | 376 | ~75k |
| angular 21→22 (enriched) | 444 | ~92k |
| spring-boot 3.5→4.0 | 2266 | ~145k (grows several times once enriched) |
| wildfly 31→32 | 897 | ~58k |

Most rows are not migration-relevant (Angular 19→20: 264 of 332 commits are `fix`). The
large model spends its context on noise and misses relevant rows in the middle of the file.

## Goal

Classify every raw row with a fast, calibrated **System-1 classifier** (a locally deployed
model with the same contract as Jev: `state` + typed questions → probability distributions,
no free text). Drop only rows that are confidently noise, and pass the remaining rows to the
existing filter LLM (System 2) annotated with their category, so it produces fewer, more
accurate migration steps.

## Key Principle: Fail Toward Keeping

A missed breaking change is far more costly than an extra noisy row. Therefore:

- The question is **"does an upgrading user need to change anything?"**, not "is this a bug fix?".
  Bug fixes that change behaviour, defaults or output (e.g. `fix(core): correctly perform lazy
  routes migration…`) must be kept.
- A row is dropped only when **every** drop condition holds (FR-4). Low confidence → keep.
- Any classifier error, timeout or unavailability → keep the row (fail open).

## Non-Goals

- Replacing the filter or entity LLM steps.
- Training or fine-tuning the classifier.
- Using the hosted Jev API (we use the local deployment; the client is pluggable).
- Changing the entity schema or graph population.

---

## Requirements

### FR-1 Deterministic pre-triage (no model call)

Applied first; resolves rows that need no model:

**Hard keep** (`triage_source = "rule"`, `decision = keep`):
- `metadata` has an Angular `BREAKING CHANGE:` / `DEPRECATED:` footer, `!` in the commit header,
  or `has_schematic = True`.
- Row type is `breaking`, `deprecation` or `mandatory_migration` with `confidence = confirmed`.
- Statement matches `(?i)\b(removed|no longer|renamed|deprecat|breaking|must|requires?)\b` in the
  *title* line (cheap safety net).

**Hard drop** (`decision = drop`):
- Angular `angular_commit_type` ∈ {`docs`, `test`, `ci`, `build`} **and** all changed files are
  outside `packages/*/src/` (i.e. docs/tests/tooling only).
- Spring Boot `github_issue_type` ∈ {`type: documentation`, `type: task`}.
- Spring Boot `github_not_planned = True`.
- Rows that are only links to "full changelog" / compare pages (`/compare/…`, "For all changes
  since…", "Changes in the underlying WildFly Core … releases are listed in…").

All other rows go to the classifier.

### FR-2 Classifier client (pluggable)

`migration_oracle/pipeline/triage/client.py`:

```python
class TriageClient(Protocol):
    async def classify(self, state: str, questions: dict[str, Question]) -> dict[str, Answer]: ...
```

Default adapter `System1HttpClient`, matching the local deployment (verified 2026-11-04 against
`http://gpuserver1.neterra.skrill.net:8002/v1/systemone`, model `nimble`).

**Config** (nothing hard-coded):

| Variable | Default | Notes |
|---|---|---|
| `TRIAGE_BASE_URL` | `""` | e.g. `http://gpuserver1.neterra.skrill.net:8002`; empty → triage off |
| `TRIAGE_ENDPOINT_PATH` | `/v1/systemone` | |
| `TRIAGE_MODEL` | `nimble` | sent as `model` |
| `TRIAGE_API_KEY` | `""` | sent as `Authorization: Bearer …` only when set |
| `TRIAGE_TIMEOUT_SEC` | `30` | per request |
| `TRIAGE_MAX_CONCURRENT` | `2` | server processes requests ~serially (see below) |

**Request** — `POST {TRIAGE_BASE_URL}{TRIAGE_ENDPOINT_PATH}`, `Content-Type: application/json`:

```json
{
  "model": "nimble",
  "state": "<string>",
  "questions": {
    "<id>": {"type": "noul",   "instructions": "..."},
    "<id>": {"type": "choice", "instructions": "...", "criteria": {"<option>": "<description>", "...": "..."}},
    "<id>": {"type": "score",  "instructions": "...", "criteria": ["<level 0>", "<level 1>", "..."]}
  }
}
```

- Question types are exactly `noul` (boolean), `choice`, `score`; anything else → HTTP 400.
- `choice.criteria` is an **object** option → description; `score.criteria` is an **array**
  ordered from lowest to highest (an object → HTTP 400).

**Response** (200):

```json
{
  "model": "nimble",
  "answers": {
    "requires_action": {"type": "noul", "noul": 0.8495},
    "category": {"type": "choice", "choice": "behavior_change",
                 "probabilities": {"breaking": 0.022, "behavior_change": 0.815, "internal_fix": 0.161, "noise": 0.002},
                 "confidence": 0.599},
    "impact": {"type": "score", "score": 1.127,
               "legend": {"0": "...", "1": "...", "2": "...", "3": "..."},
               "probabilities": {"0": 0.051, "1": 0.772, "2": 0.174, "3": 0.002},
               "confidence": 0.517}
  },
  "usage": {"input_tokens": 1537, "output_tokens": 4}
}
```

- `noul` is P(true). `confidence` is **not** the max probability (0.599 vs 0.815 above): it is a
  separate certainty measure. Both are stored; the decision rule uses probabilities (FR-4).
- Errors come back as `{"error": "..."}` with 4xx; a 4xx is a bug in our request → log ERROR once
  per run and disable triage for the run (all rows `triage_source = "error"`, kept).
- 5xx/timeout: 2 retries with backoff, then the row is kept with `triage_source = "error"`.
- `usage.input_tokens` is summed into `summary.json`.

**Measured behaviour** (2026-11-04): single request ~0.6–0.7 s; 16 parallel requests finished
in 3.7 s with latencies increasing in ~0.2 s steps, i.e. the server serialises requests at
~4–5 req/s. Concurrency above 2 only adds queueing; ~2.3k model-classified rows ≈ 8–10 min.
The question set alone costs ~1.4k input tokens per request.

A `FakeTriageClient` (deterministic, driven by fixtures) is used in tests.

### FR-3 State and questions

**State** is a **string** (the API takes a string). Rendered as labelled lines, only fields
present for the framework, truncated to `TRIAGE_STATE_MAX_CHARS` (default `6000`):

```
Framework: Angular
Hop: 19.0.0 → 19.0.1
Raw type: behavioral (inferred)
Package: core
Commit type: fix
Labels: type: bug
Has ng-update schematic: no
Files: packages/core/src/render3/…, packages/core/test/…
Change:
Title: fix(core): …
Commit: …
Issue: #58793 …
```

The `Release:` line is omitted (it repeats the title).

**Questions** — fixed, versioned as `TRIAGE_QUESTIONS_VERSION = 1`, kept in
`triage/questions.py`:

| id | type | Instructions | Criteria |
|---|---|---|---|
| `requires_action` | `noul` | Would a typical application upgrading across this version hop need to change code, configuration, dependencies, build, deployment or runtime environment, or re-verify a behaviour it relies on? | — |
| `category` | `choice` | Which best describes the effect of this change on an upgrading user? | object: `breaking`, `behavior_change`, `deprecation`, `config_change`, `dependency_upgrade`, `security`, `new_optional_feature`, `internal_fix`, `noise` → one-line definition each (a bug fix that changes observable behaviour is `behavior_change`; one users need not react to is `internal_fix`) |
| `impact` | `score` | Rate the migration effort this change forces on applications that use the framework. Documentation, test, build and typo changes force no effort. | `["none", "low", "medium", "high"]` |

**Wording matters for `score`** (measured): with instructions "How much migration effort does this
change imply for an affected application?" and criteria `"none: no effort", …` a docs-typo row
scored **2.94 (≈ high)**; with the wording above it scored **0.01** and the Tomcat row 1.09.
Question wording is therefore part of the evaluation (AC-7) and any change bumps
`TRIAGE_QUESTIONS_VERSION`.

### FR-4 Decision rule

A classified row is **dropped** only if all hold (thresholds configurable):

- `requires_action.noul < TRIAGE_DROP_MAX_ACTION_PROB` (default `0.10`)
- `category.choice ∈ {internal_fix, noise, new_optional_feature}`
- `category.probabilities[category.choice] ≥ TRIAGE_DROP_MIN_CATEGORY_PROB` (default `0.80`)
- `impact.score < TRIAGE_DROP_MAX_IMPACT_SCORE` (default `1.0`, i.e. below "low")

`category.confidence` / `impact.confidence` are recorded but not used in the rule until AC-7
shows they add signal.

Otherwise the row is **kept**. Every row (kept or dropped) records in `metadata`:
`triage_decision`, `triage_source` (`rule` | `model` | `error` | `disabled`),
`triage_category`, `triage_category_prob`, `triage_category_confidence`, `triage_action_prob`,
`triage_impact_score`, `triage_questions_version`, `triage_model`.

### FR-5 Pipeline integration

- New module `migration_oracle/pipeline/triage/` with `run_triage(changes, framework, hop) ->
  TriageResult(kept, dropped)`.
- Runs in `cli.py` on the extracted `DocumentedChange` objects **before** the raw Markdown is
  written, so triage sees the full `metadata` (labels, commit type, package, schematic flag)
  and its results land in the raw file. Also runs with `--extract-only`.

#### FR-5.1 Triage results in `runs/raw/` (source of truth)

When triage ran, `render_raw_markdown` writes **all rows (kept and dropped)** to
`runs/raw/<framework>-<from>-to-<to>-changes.md` with six extra columns:

```
| Type | Confidence | Source | Statement | Triage | Category | Cat. prob | P(action) | Impact | Triage source |
|------|------------|--------|-----------|--------|----------|-----------|-----------|--------|---------------|
| behavioral | inferred | https://github.com/…/issues/39942 | Title: … | keep | behavior_change | 0.82 | 0.85 | 1.09 | model |
| behavioral | inferred | https://github.com/…/commit/ab12… | Title: docs(…) … | drop | — | — | — | — | rule |
```

- `Triage` ∈ {`keep`, `drop`}; `Cat. prob` = probability of the chosen category, `Impact` = `impact.score` (0–3); numbers rendered with 2 decimals; the server `confidence` values go to the `.jsonl` only; `Triage source` ∈
  {`rule`, `model`, `error`}; for `rule` rows the model columns are `—`.
- Row order is unchanged (dropped rows are not moved), so diffs against previous runs stay readable.
- The header block gains a line
  `- **Triage:** <model> · questions v<N> · kept <k> / dropped <d> / error <e>`.
- When triage did not run (disabled, `--skip-triage`, no `TRIAGE_BASE_URL`), the raw file is
  rendered exactly as today (4 columns, byte-for-byte).

#### FR-5.2 Derived artifacts

- `runs/triage/<framework>-<from>-to-<to>-triage.jsonl`: one line per row with the full
  probability distributions for all three questions (for `scripts/eval_triage.py` and
  threshold tuning).
- `runs/triage/<framework>-<from>-to-<to>-summary.json`: counts per decision/category/source.
- The filter input is derived from the raw file in memory: `Triage = keep` rows only, columns
  `Type | Confidence | Source | Statement | Category | Impact` (confidence/probability columns
  are stripped to save tokens). No separate kept/dropped Markdown files.

#### FR-5.3 Re-use of an existing raw file

The CLI re-uses `runs/raw/*.md` when extraction is skipped. Therefore:

- Add `parse_raw_markdown(md) -> list[RawRow]` that reads both the 4-column and the 10-column
  table formats.
- Raw file **with** triage columns and no `--force-triage` → reuse its decisions, no classifier calls.
- Raw file **without** triage columns and triage enabled → classify the parsed rows with a
  statement-only state (metadata is not in the Markdown), log one WARNING recommending
  `--force-extract` for best signal, and rewrite the raw file with the triage columns.
- Threshold changes (FR-4) can be re-applied without calling the model via
  `--retriage-from-cache`: decisions are recomputed from the cached distributions and the raw
  file is rewritten.

#### FR-5.4 Cache and flags

- Cache: results keyed by `sha256(questions_version + model + state)` in
  `ARTIFACT_CACHE_DIR/triage/`, so re-runs and overlapping ranges do not re-classify.
- Flags: `--skip-triage` (raw file and filter input as today), `--force-triage`
  (ignore cache and existing triage columns), `--retriage-from-cache`.
  Config `TRIAGE_ENABLED` (default `false` until AC-7 passes, then `true`).
- If `TRIAGE_BASE_URL` is unset or the health check fails: one WARNING, behave as `--skip-triage`.

### FR-6 Filter prompt adaptation

- `FILTER_PROMPT` input table gains `Category | Impact` columns. Add one rule: *"Rows were
  pre-classified; use Category to choose the output section, but override it when the
  statement clearly contradicts it."* The rest of the prompt is unchanged.
- If the kept table exceeds `FILTER_MAX_INPUT_TOKENS` (default `60k`), run the filter per
  category group (`breaking`+`deprecation`, `behavior_change`+`config_change`+`security`,
  `dependency_upgrade`, rest) and concatenate the sections. Deduplication across groups is
  left to the entity step.

---

## Acceptance Criteria

**Unit (fake client)**

1. **AC-1** Angular row with a `BREAKING CHANGE:` footer is kept by rule and never sent to the
   client.
2. **AC-2** Angular `docs(...)` commit touching only `adev/` files is dropped by rule.
3. **AC-3** Answer `noul=0.05`, `choice=internal_fix` with probability 0.9, `score=0.4` → dropped.
   Same with probability 0.7 → kept; same with `score=1.2` → kept.
3a. **AC-3a** `System1HttpClient` serialises questions exactly as the API expects (`noul` type,
   `choice.criteria` object, `score.criteria` array) and parses the recorded response from FR-2;
   a recorded `{"error": "..."}` 400 disables triage for the run with one ERROR log.
4. **AC-4** Client timeout/5xx after retries → row kept, `triage_source = "error"`.
5. **AC-5** `TRIAGE_BASE_URL` unset → no HTTP calls; the raw file and the filter input equal
   today's output byte-for-byte (4 columns).
6. **AC-6** Cached result is reused: the second run makes zero classifier calls; changing
   `TRIAGE_QUESTIONS_VERSION` invalidates the cache.
7. **AC-6a** With triage enabled, `runs/raw/*-changes.md` contains every extracted row (kept and
   dropped) in the original order, with the 10-column header and the `Triage:` header line;
   `parse_raw_markdown` round-trips it to identical decisions.
8. **AC-6b** Filter input built from that raw file contains only `keep` rows and exactly the
   columns `Type | Confidence | Source | Statement | Category | Impact`.
9. **AC-6c** Re-running with an existing triaged raw file makes zero classifier calls;
   `--retriage-from-cache` with a changed threshold rewrites `Triage` values without HTTP calls.

**Quality (silver labels from existing runs)**

7. **AC-7** Evaluation script `scripts/eval_triage.py` maps every entity in
   `runs/json/*-entities.json` back to its raw row(s) via `source_url` / `jira_keys` / issue
   number / commit sha, and treats those rows as "relevant". On Angular 18→22, Spring Boot
   3.3→4.1 and WildFly 28→30:
   - recall of relevant rows whose entity `change_type` is breaking / deprecation / mandatory
     migration ≥ **98%**;
   - recall of all relevant rows ≥ **95%**;
   - drop rate ≥ **50%** of all raw rows.
   The script prints the missed relevant rows for manual review.
8. **AC-8** For one range per framework, the filter output after triage is reviewed manually
   against the current output: no migration item present today is lost, and at least
   as many items carry concrete steps.

**Performance**

9. **AC-9** Filter input token count drops by ≥ 50% on Spring Boot 3.5→4.0. Triage wall time
   is recorded in `summary.json` (informational; expected ~8–10 min for ~2.3k model-classified
   rows at `TRIAGE_MAX_CONCURRENT=2`, not a gate).

## Implementation Notes

- Files: `migration_oracle/pipeline/triage/{__init__,client,questions,rules,run}.py`,
  `migration_oracle/config.py`, `migration_oracle/cli.py`, `migration_oracle/pipeline/filters.py`,
  `migration_oracle/pipeline/extractors/__init__.py` (`render_raw_markdown` triage columns,
  new `parse_raw_markdown`), `scripts/eval_triage.py`.
- Tests: `tests/pipeline/test_triage_rules.py`, `test_triage_decision.py`,
  `test_triage_cache.py`, and a CLI test with `FakeTriageClient`.
- Docs: new "Triage" section in `docs/export-extract-populate-framework-pipeline.md`;
  `CHANGELOG.md` entry; `.env.example` gains the `TRIAGE_*` variables.

## Open Questions

1. ~~Local deployment API~~ — resolved, see FR-2 (verified with live calls 2026-11-04).
2. ~~Auth~~ — resolved: the endpoint needs no auth in any environment. `TRIAGE_API_KEY` stays
   optional (unused today).
3. ~~Limits~~ — resolved: input size is not a practical concern; `TRIAGE_STATE_MAX_CHARS` is a
   safety net only. The server will not get more workers; throughput (~4–5 req/s) is accepted
   because extraction speed is not critical — AC-9 is informational, not a gate.
4. **Calibration** (open): the server `confidence` differs from the top probability; thresholds
   in FR-4 must be tuned with AC-7 before `TRIAGE_ENABLED` defaults to `true`.
5. ~~Other models~~ — resolved: only `nimble` for now. `TRIAGE_MODEL` stays configurable and is
   part of the cache key, so a future model is evaluated by re-running AC-7.

## Estimate

~2 days:

| Work | Effort |
|---|---|
| Rules + decision + artifacts + cache | 4 h |
| Client adapter + fake client | 2 h |
| CLI wiring + filter prompt / chunking | 2 h |
| Tests | 3 h |
| Eval script + threshold tuning on existing runs | 4 h |
| Docs | 1 h |
