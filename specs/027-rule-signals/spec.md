# Feature Specification: Rule Detection Signals (Nimble Classification)

**Feature Branch**: `027-rule-signals`

**Created**: 2026-11-06

**Status**: Draft

**Scope**: Lightweight spec (no full SpecKit flow). New **ingestion** stage after MigrationRule
generation. Nimble (System-1) classifies every rule by **how a service shows that the rule
applies to it**. The result is written as properties on each `MigrationRule` node. Code adds
the keys a scanner can look for, and checks the result.

**Depends on**:
- `022-system1-change-triage`: Nimble client, settings, cache pattern, question versioning.
- `024-dossier-entities`: `runs/json/*-entities.json`.
- `025-entity-canonicalization`: canonical keys and `verified` per entity.

**Used by**: the migration planner (`026` scanner, `028` matcher). The planner never calls
Nimble for this question. It reads the result from the graph.

## Problem

The planner must decide per service whether a rule applies. That decision depends on what kind
of rule it is, and the graph does not say so today:

- `TestBed.get removed`: applies **iff** the code calls `TestBed.get`. A name search decides it.
- `engines.node raised to 20.19`: decided by `package.json`.
- `@angular/animations deprecated`: decided by a dependency.
- `DestroyRef.onDestroy runs immediately when the view is destroyed`: `DestroyRef` in the code
  is **not** enough. Only code that registers after destroy is affected, so the planner must
  look at the code (028).
- `Minimum TypeScript 5.8`: applies to every service on the hop.

Measured on `runs/json/*-entities.json` (2026-11-06): 715 rules, **233 (33%) with no entity at
all**. For them nothing can be searched by name, but many are still decidable (universal
version floors, builder changes, SSR-only behaviour). Rules that have entities often name only
the **replacement** (`use X instead`), and finding `X` in the code means the service already
migrated. So "has entities" is not the same as "can be searched by name".

The planner also needs to know **which feature a rule needs** (SSR, zoneless, animations,
Karma, Spring Security…). Then it can rule out whole groups from the manifest, and ask a
person one question ("Do you use SSR?") instead of one question per rule.

## Goal

```
entities.json ─▶ canonicalize (025) ─▶ signals (027)                         ─▶ populate
                                        │ Nimble: signal type + feature tags
                                        │ code:   signal keys + contract guard
                                        └─▶ runs/signals/*-signals.jsonl + summary

(:MigrationRule { signal, signalConfidence, signalSource, signalKeys, features, … })
```

## Key Principles

- **The wrong error is exclusion.** If a rule is wrongly marked `symbol` and the symbol is not
  found, the planner excludes a rule that applies. Every rule that is uncertain therefore falls
  back to `behavioral`. The planner then looks at the code or asks, and never drops it on a
  missing name.
- **Nimble classifies, code checks.** Nimble picks the type and the features. Code derives the
  keys and rejects a type that has nothing to search for (FR-4).
- **Rule-level, service-independent.** One call per rule per question version, cached. No service
  data is involved.
- **Additive.** Existing properties, edges and MCP tools do not change.

## Non-Goals

- Matching services (028), Nimble questions with code excerpts (029).
- Per-step signals. Rules whose steps have different conditions are handled at rule level here;
  see Open Questions.
- Changing triage (022), research (023) or the entity prompt (024 / 025).

---

## Requirements

### FR-1 Signal types

| `signal` | Meaning | Planner (028) decides with | Example |
|---|---|---|---|
| `symbol` | Applies iff the code uses a named API: class, function, member, decorator option | profile `symbols` / `members` | `TestBed.get` removed |
| `config` | Applies iff a config key is set (or set to a value) | profile `config` | `angularCompilerOptions.strictStandalone` default changed |
| `dependency` | Applies iff a package is declared, optionally in a version range | profile `dependencies` | `@angular/animations` deprecated |
| `syntax` | Applies iff template syntax is used | profile `templates` | `in` in expressions is an operator |
| `behavioral` | The API name is not enough; whether the code relies on the old behaviour decides it | code excerpts → Nimble (029), else ask | `onDestroy` timing |
| `universal` | Applies to every service on the hop | nothing | minimum Node / TypeScript |

### FR-2 Feature vocabulary

Per framework, versioned with the questions (FR-3). Each feature has an id, the question text,
and **evidence keys**: profile keys from which the planner can tell, without asking, that the
service has the feature. The evidence keys are data for 028; this spec only stores them.

Angular (initial set):

| id | Question | Evidence keys (any) |
|---|---|---|
| `ssr` | Server-side rendering or prerendering | `npm:@angular/ssr`, `npm:@angular/platform-server` |
| `hydration` | Client hydration | `npm:@angular/platform-browser#provideClientHydration` |
| `zoneless` | Zoneless change detection | `npm:@angular/core#provideZonelessChangeDetection`, `…#provideExperimentalZonelessChangeDetection` |
| `zone` | Zone.js-based change detection | `npm:zone.js` |
| `animations` | `@angular/animations` | `npm:@angular/animations` |
| `router` | Angular Router | `npm:@angular/router` |
| `forms` | Template-driven or reactive forms | `npm:@angular/forms` |
| `http` | `HttpClient` | `npm:@angular/common/http#provideHttpClient`, `…#HttpClientModule` |
| `i18n` | `@angular/localize` | `npm:@angular/localize` |
| `service-worker` | `@angular/service-worker` | `npm:@angular/service-worker` |
| `testbed` | Unit tests with `TestBed` | `npm:@angular/core/testing#TestBed` |
| `karma` | Karma test runner | `npm:karma`, `cfg:angular.json#projects.*.architect.test.builder` = `…:karma` |
| `ngmodule` | NgModule-based (non-standalone) components | `npm:@angular/core#NgModule` |
| `elements` | Angular Elements | `npm:@angular/elements` |
| `upgrade` | AngularJS hybrid (`@angular/upgrade`) | `npm:@angular/upgrade` |
| `cli-build` | Angular CLI build / dev-server config | `cfg:angular.json#projects.*.architect.build.builder` |

Spring Boot (initial set): `web-mvc`, `webflux`, `security`, `data-jpa`, `data-mongodb`,
`data-redis`, `kafka`, `actuator`, `observability`, `jackson`, `batch`, `testing`, `cloud`,
`gradle`, `maven`. Evidence keys are the starter coordinates
(`maven:org.springframework.boot:spring-boot-starter-security`, …).

WildFly: subsystems (`undertow`, `ejb3`, `messaging-activemq`, `elytron`, `jpa`, …). Evidence
keys come later, with a WildFly scanner.

Stored in `migration_oracle/pipeline/signals/features.py` as plain data, so `migration_keys/`
(026) can export it to the planner unchanged.

### FR-3 Nimble questions

Request format as in 022 (`{model, state, questions}`), answers as probability distributions.
`SIGNAL_QUESTIONS_VERSION` covers the wording, criteria and feature vocabulary. Any change bumps
it, so cached answers are not reused.

**State** (capped at `SIGNAL_STATE_MAX_CHARS`, default 4 000):

```
Framework: Angular · Hop: 19.2.0 → 20.0.0
Rule: DestroyRef.onDestroy callbacks run immediately when view is already destroyed
Type: behavior_change · Section: behavioral
Reason: <reason>
Entities (role · canonical key · verified):
  mentioned · npm:@angular/core#DestroyRef · true
  mentioned · npm:@angular/core/rxjs-interop#takeUntilDestroyed · true
Steps:
  0 verify · Audit code paths where DestroyRef.onDestroy() or takeUntilDestroyed can run after …
```

**Questions**:

```json
{
  "signal": {
    "type": "choice",
    "instructions": "What in an application's code or build shows that this rule applies to that application?",
    "criteria": {
      "symbol":     "Using a specific API named in the rule (class, function, method, decorator option) is enough: every application that uses it must act, and no other application must.",
      "config":     "A specific key in angular.json, tsconfig.json, package.json or another config file decides it.",
      "dependency": "Declaring a specific package, or a version of it, decides it.",
      "syntax":     "Using specific template syntax decides it.",
      "behavioral": "Using the named API is not enough; only code that relies on the old behaviour is affected, which needs reading the code.",
      "universal":  "Every application upgrading across this version hop is affected."
    }
  },
  "feature.ssr":       { "type": "noul", "instructions": "Does this rule only matter for applications that use server-side rendering or prerendering?" },
  "feature.zoneless":  { "type": "noul", "instructions": "Does this rule only matter for applications that use zoneless change detection?" },
  "feature.testbed":   { "type": "noul", "instructions": "Does this rule only matter for applications with unit tests that use TestBed?" }
}
```

One `feature.<id>` `noul` question per vocabulary entry (Nimble has no multi-select type), all in
the same request, so the state is sent once per rule.

### FR-4 Signal keys and contract guard (code)

After Nimble answers, code derives what the planner searches for and checks that it is possible.

1. **Signal keys**: canonical keys (025) of the rule's entities, by role:
   - `removed` and `mentioned` count. `replacement` and `co-required` do not: finding the
     replacement means the service has already migrated.
   - `symbol` → `class` / `member` keys; `config` → `property` keys with a known `file`;
     `dependency` → `dependency` keys; `syntax` → `syntax` keys.
   - Keys with `verified: false` are kept but flagged. Keys with an unresolved package
     (`npm:?#…`) are not searchable by key, so they are kept as name-only signals.
2. **Guard**: the chosen type must have at least one signal key. Otherwise `signal` becomes
   `behavioral` with `signalSource: guard` and the reason in the artifact. Examples: `symbol`
   for a rule that names only its replacement; `config` without a property entity.
3. **Confidence floors** (the excluding error is the expensive one):
   - `symbol`, `config`, `dependency`, `syntax` need `P ≥ SIGNAL_SEARCHABLE_MIN_PROB`
     (default `0.70`);
   - `universal` needs `P ≥ SIGNAL_UNIVERSAL_MIN_PROB` (default `0.60`; a wrong `universal`
     only adds a rule);
   - below the floor → `behavioral`, `signalSource: low_confidence`.
4. **Features**: `features` = ids with `P ≥ SIGNAL_FEATURE_MIN_PROB` (default `0.50`). All
   probabilities go to the artifact.
5. **Deterministic shortcut** (no Nimble call, `signalSource: rule`):
   - every entity is a `dependency` and `change_type` is `component_upgrade` → `dependency`;
   - features are still asked, in the same request; only `signal` is fixed.

### FR-5 Graph properties

Written on `MigrationRule` by `ruleId`:

| Property | Type | Example |
|---|---|---|
| `signal` | string | `behavioral` |
| `signalConfidence` | float | `0.87` (probability of the chosen type, after the guard) |
| `signalSource` | string | `model` · `rule` · `guard` · `low_confidence` |
| `signalKeys` | list<string> | `["npm:@angular/core#DestroyRef", …]` |
| `features` | list<string> | `["testbed"]` |
| `signalQuestionsVersion` | int | `1` |
| `signalModel` | string | `nimble` |

- A rule without these properties (not classified yet, or Nimble unavailable) is treated by the
  planner as `behavioral`. A missing classification never excludes anything.
- `populate_graph` writes them for new hops in the same session as the rule.

### FR-6 Stage, CLI and backfill

- **In the pipeline**: runs after canonicalization (025) and before graph writes, inside
  `populate_graph`. `--dry-run` runs it and writes the artifacts.
- **Skip / force**: `--skip-signals` writes the rules without signal properties.
  `--force-signals` ignores the cache.
- **Backfill** for hops already in the graph, which are not repopulated:
  `scripts/classify_signals.py --framework angular [FROM TO | --all] [--dry-run]`. It reads
  `runs/json/*-entities.json`, canonicalizes, classifies, and runs
  `MATCH (r:MigrationRule {ruleId: $id}) SET r += $props`. It only sets the FR-5 properties, is
  idempotent, and reports rules whose `ruleId` is not in the graph.
- **Nimble unavailable** (as in 022: `TRIAGE_BASE_URL` / `TRIAGE_MODEL` empty, or unreachable):
  the stage logs once, writes no signal properties, and populate continues. The summary records
  `nimble: unavailable`, and the backfill can be run later.
- **Settings**: reuse `TRIAGE_BASE_URL`, `TRIAGE_ENDPOINT_PATH`, `TRIAGE_MODEL`,
  `TRIAGE_API_KEY`, `TRIAGE_TIMEOUT_SEC`, `TRIAGE_MAX_CONCURRENT` (same service). New:
  `SIGNAL_STATE_MAX_CHARS`, `SIGNAL_SEARCHABLE_MIN_PROB`, `SIGNAL_UNIVERSAL_MIN_PROB`,
  `SIGNAL_FEATURE_MIN_PROB`.

### FR-7 Artifacts and cache

- **`runs/signals/<framework>-<from>-to-<to>-signals.jsonl`**: one line per rule: `ruleId`,
  title, the rendered state, raw answers (all probabilities), chosen `signal`, `signalSource`,
  guard / floor reason, `signalKeys`, `features`, cache hit, input tokens.
- **`…-summary.json`**: rules per `signal` and `signalSource`, rules per feature, guard and
  low-confidence counts, `nimble` status, calls / cache hits / tokens, wall time.
- **Cache**: `ARTIFACT_CACHE_DIR/signals/sha256(SIGNAL_QUESTIONS_VERSION + model + framework +
  state)`. The state contains the canonical keys, so a canonicalization change re-asks only the
  rules it affects. Error results are not cached.

---

## Acceptance Criteria

**Unit (fake Nimble client)**

1. **AC-1** Request shape: one request per rule with `signal` and one `feature.<id>` per
   vocabulary entry, the 022 body format, state ≤ `SIGNAL_STATE_MAX_CHARS`.
2. **AC-2** Guard:
   - `symbol` for a rule with only `replacement` entities → `behavioral` / `guard`;
   - `config` without a property entity → `behavioral` / `guard`;
   - `symbol` with a `removed` member key → stays `symbol`, `signalKeys` = that key only.
3. **AC-3** Floors: `symbol` at `0.65` → `behavioral` / `low_confidence`; `universal` at `0.65` →
   `universal`; features at `0.49` / `0.51` → excluded / included.
4. **AC-4** Shortcut: an all-dependency `component_upgrade` rule → `dependency` / `rule`, and its
   features are still requested.
5. **AC-5** Cache: second run → zero calls. A changed canonical key in one rule → exactly one
   call. A version bump → all rules re-asked.
6. **AC-6** Nimble unavailable → no signal properties, populate succeeds, summary says
   `unavailable`.
7. **AC-7** Backfill: sets only the FR-5 properties on existing rules; a second run changes
   nothing; unknown `ruleId`s are reported.

**Quality (manual, before defaults are final)**

8. **AC-8** Hand-label `signal` and features for **80 rules**, 40 per framework, then compare
   per framework:

   | Framework | Hops | Rules in the hops | Labelled |
   |---|---|---|---|
   | Angular | 19.2.0 → 20.0.0, 20.0.0 → 21.0.0 | 69 + 43 | 40 |
   | Spring Boot | 3.5.0 → 4.0.0, 4.0.0 → 4.1.0 | 54 + 51 | 40 |

   - The 40 per framework are a stratified sample: every `change_type` present, and at least 10
     rules without entities.
   - The labels are stored in `eval/signals/<framework>-labels.jsonl`
     (`ruleId`, `signal`, `features`, note), so the check can be re-run after a question or
     vocabulary change (`scripts/eval_signals.py`, like `scripts/eval_triage.py`).
   - Each framework on its own must reach:
     - `signal` agrees on ≥ 85% of rules;
     - **≤ 1 rule** labelled `behavioral` or `universal` by hand ends as a searchable type
       (`symbol` / `config` / `dependency` / `syntax`); this is the excluding error;
     - feature precision ≥ 80% and recall ≥ 70%.
   - Record per framework: the distribution per `signal`, and how many rules the guard and the
     floors changed.
   - Tune `SIGNAL_*_MIN_PROB` on these sets only. If the two frameworks need different floors,
     the settings take a per-framework override (`SIGNAL_SEARCHABLE_MIN_PROB_SPRING_BOOT`, …)
     instead of one compromise value.

## Implementation Notes

- New package `migration_oracle/pipeline/signals/`:
  - `features.py` (FR-2 vocabulary + evidence keys)
  - `questions.py` (FR-3, `SIGNAL_QUESTIONS_VERSION`)
  - `contract.py` (FR-4 keys, guard, floors, shortcut)
  - `run.py` (calls, cache, artifacts)
  - `settings.py` (thresholds)
- Reuse `pipeline/triage/client.py` (`System1HttpClient`, retries, `notify_once`) and its cache
  helpers. If they are triage-specific, lift them to `pipeline/system1/` without behaviour
  change.
- `populator.py`: call the stage after `canonicalize_batch`, write FR-5 in `_write_entity`.
- `scripts/classify_signals.py` (FR-6 backfill).
- `_paths.py`: `RUNS_SIGNALS` and path helpers.
- Tests: `tests/pipeline/test_signals_*.py`.
- Docs: new stage in `docs/02-extraction-pipeline/export-extract-populate-framework-pipeline.md`,
  `MigrationRule` properties in `docs/01-foundation/graph-schema.md`, `.env.example`, `CHANGELOG.md`.

## Open Questions

1. **Per-step signals.** Some rules mix conditions (SSR step + hydration step). Is a rule-level
   `features` list enough for 028, or do steps need their own `features`? Measure on AC-8: how
   many rules have steps that apply to different features.
2. **Value conditions.** `dependency` and `config` rules often depend on a value
   (`engines.node < 20.19`, `typescript < 5.8`). Should this stage also extract a machine-checkable
   condition (`{key, op, value}`)? That is extraction, not classification, so it would come from
   the entity LLM. It may belong to a later spec.
3. **`universal` vs. `dependency`.** "Minimum TypeScript 5.8" is universal for Angular but checkable
   against `npm:typescript`. With a value condition (OQ-2) it becomes `dependency`, which is more
   precise. Until then it is `universal`.
4. **Feature vocabularies.** The Spring Boot list must be reviewed by someone who knows the
   target services **before** the AC-8 labelling, since the labels use it. WildFly is reviewed
   when a WildFly scanner exists; it is not part of AC-8.
5. ~~**Spring property rules.**~~ Settled 2026-11-06: the scanner reads `application*` and
   `bootstrap*` `.properties` / `.yml` (026 FR-8a), so Spring property rules are `config` and
   searchable under `cfg:application.properties#<key>`. AC-8 still records how many Spring rules
   are `config`.

## Estimate

~3 days:

| Work | Effort |
|---|---|
| Feature vocabulary (Angular, Spring Boot) + questions | 3 h |
| Stage: state rendering, Nimble calls, cache, artifacts | 4 h |
| Contract guard, floors, shortcut | 2 h |
| Populator wiring, graph properties, backfill script | 3 h |
| Unit tests | 3 h |
| AC-8 labelling (80 rules, two frameworks), eval script, threshold tuning | 7 h |
| Docs, `.env.example` | 1 h |
