# Export → Extract → Filter → JSON → Graph Pipeline
 
This document explains, in full detail, how the **export-extract-populate-framework** command works: from fetching upstream release data, through LLM-based filtering and entity extraction, to optional graph population. Everything is described by behavior and data flow — not by internal source layout.
 
---
 
## Table of contents
 
1. [Purpose and scope](#purpose-and-scope)
2. [High-level architecture](#high-level-architecture)
3. [Command-line interface](#command-line-interface)
4. [Supported frameworks](#supported-frameworks)
5. [Phase 0 — Bootstrap and configuration](#phase-0--bootstrap-and-configuration)
6. [Phase 1 — Version resolution and chunking](#phase-1--version-resolution-and-chunking)
7. [Phase 2 — Raw release extraction (upstream fetch)](#phase-2--raw-release-extraction-upstream-fetch)
8. [Phase 3 — JBoss / WildFly Jira enrichment](#phase-3--jboss--wildfly-jira-enrichment)
9. [Phase 4 — Storing raw release nodes (Markdown)](#phase-4--storing-raw-release-nodes-markdown)
10. [Phase 5 — Filter and group (raw → filtered nodes)](#phase-5--filter-and-group-raw--filtered-nodes)
11. [Phase 5b — Per-change research](#phase-5b--per-change-research)
12. [Phase 5c — Dossier entities](#phase-5c--dossier-entities)
13. [Phase 6 — Entity extraction (filtered → JSON)](#phase-6--entity-extraction-filtered--json)
14. [Phase 7 — Optional graph population](#phase-7--optional-graph-population)
15. [Caching, idempotency, and force flags](#caching-idempotency-and-force-flags)
16. [Environment variables and model configuration](#environment-variables-and-model-configuration)
17. [Failure modes and retries](#failure-modes-and-retries)
18. [End-to-end example walkthrough](#end-to-end-example-walkthrough)
---
 
## Purpose and scope
 
The pipeline answers one question for any supported framework:
 
> **What must a developer change when upgrading from version A to version B?**
 
It does this in four materialized stages:
 
| Stage | Artifact | Description |
|-------|----------|-------------|
| **Raw** | Markdown report | Every extracted change record, one row per upstream item, grouped by version hop |
| **Filtered** | Structured Markdown | Noise removed, related items merged, categorized by migration severity |
| **Entities** | JSON | Machine-readable migration entities with reasons, action steps, and affected artifacts |
| **Graph** | Neo4j / Memgraph nodes | Optional persistence of migration rules linked to a framework version |
 
The command is **framework-agnostic**: the same orchestration runs for Spring Boot, Angular, WildFly, and the rest; only the upstream fetch logic differs per framework.
 
---
 
## High-level architecture
 
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CLI: --framework, from, to                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. RESOLVE VERSIONS                                                        │
│     Normalize inputs → find available releases → compute version hops       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │  (skip if cached raw MD exists    │
                    │   and --force-extract not set)    │
                    └─────────────────┬─────────────────┘
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. EXTRACT (per version hop)                                               │
│     Framework-specific HTTP fetch → parse → classify → (Jira enrich)        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. RENDER RAW MARKDOWN  →  runs/raw/<framework>-<from>-to-<to>-changes.md  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │  (skip LLM if cached JSON exists  │
                    │   and --force-llm not set)        │
                    └─────────────────┬─────────────────┘
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. PER-CHANGE RESEARCH (optional)  →  runs/research/...-research.jsonl     │
│     One small tool-calling model call per kept triage row. Facts only.     │
│     Off unless RESEARCH_BASE_URL and RESEARCH_MODEL_ID are set. No        │
│     TAVILY_API_KEY = fetch_url only. A failed row stays unchanged.         │
│     --stop-after-research ends the run here.                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. ENTITIES                                                                │
│     dossier (default when research ran): gate → cluster → one entity call  │
│       per cluster → rendered runs/nodes/*_filtered.md and entities JSON.   │
│       --stop-after-clusters stops after runs/clusters/.                    │
│     filter (research off, --skip-research, or --entity-source filter):     │
│       filter LLM document, then one entity call on that document.          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │  (skip if --dry-run)              │
                    └─────────────────┬─────────────────┘
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6. GRAPH WRITE (optional)                                                  │
│     MigrationRule nodes + precomputed entity properties → Neo4j/Memgraph    │
└─────────────────────────────────────────────────────────────────────────────┘
```
 
Key design choices:
 
- **Separate LLM calls**: when research ran, each change cluster gets its own entity call. The filter call remains the path for runs without research (`--entity-source filter`, research disabled, or `--skip-research`).
- **Whole-document filter and entity calls** (`filter` mode): those two steps send the Markdown for the hop in one request (the entity call is split by section only when the input exceeds `ENTITY_MAX_INPUT_TOKENS`). Research is the per-row step. Dossier mode never sends the whole hop to the entity model.
- **Incremental caching**: raw Markdown, filtered Markdown, research dossiers, and entities JSON are persisted independently. Re-runs skip expensive steps when artifacts already exist.
---
 
## Command-line interface
 
### Required arguments
 
| Argument | Meaning |
|----------|---------|
| `--framework <key>` | Which registered framework extractor to use (see [Supported frameworks](#supported-frameworks)) |
| `from_version` | Start of the upgrade range (inclusive lower bound) |
| `to_version` | End of the upgrade range (inclusive upper bound) |
 
### Optional flags
 
| Flag | Effect |
|------|--------|
| `--dry-run` | Run extraction and LLM steps but **do not write to the graph database**. Cached artifacts are still reused unless forced. |
| `--force-extract` | Always re-fetch upstream data and overwrite the raw Markdown report, even if one already exists. |
| `--force-llm` | Always call both LLM steps and overwrite filtered Markdown and entities JSON, even if they already exist. In dossier mode, ignore the per-cluster entity cache. |
| `--force` | Shorthand for `--force-extract` **and** `--force-llm`. |
| `--hop-granularity patch\|minor` | Version step size between ingestion hops. `minor` (default) collapses each minor line into one hop (`3.1.12 → 3.2.0 → 3.2.4`); `patch` walks every released version. Env fallback: `HOP_GRANULARITY`. |
| `--hop-by-hop` / `--no-hop-by-hop` | Run the filter LLM, entity LLM, and graph population **once per version hop** instead of once per range, so every hop becomes its own `Version` node holding only its own rules. Implies one raw/filtered/entities artifact triple per hop and rejects `--output-*` overrides. Env fallback: `HOP_BY_HOP` (default off). |
| `--skip-triage` | Keep every extracted row. Do not call the System-1 classifier and do not apply triage drop rules. The raw file stays a 4-column table. |
| `--force-triage` | Ignore the answer cache and any triage columns already stored in the raw file, and classify again. |
| `--retriage-from-cache` | Recompute keep/drop from `runs/triage/*-triage.jsonl` using the current thresholds. No classifier HTTP calls. |
| `--skip-research` | Do not research filtered rows. The entity step sees the filtered Markdown only, as it did before this stage. |
| `--force-research` | Ignore the per-row research cache and any existing `research.jsonl` for the hop. Without it, rows found in the hop's `research.jsonl` are reused first. |
| `--stop-after-research` | Run extraction, triage, and per-row research, then stop. No filter LLM, no entity LLM, and no graph writes, so no `MODEL_*` is needed. Needs research configured. |
| `--entity-source dossier\|filter` | `dossier` builds entities from the research dossiers (the default when research is enabled and was not skipped). `filter` is the filter LLM, then the entity LLM. Env: `ENTITY_SOURCE`. `--skip-research` forces `filter`. `--entity-source dossier --skip-research` is an error. |
| `--stop-after-clusters` | Run the action gate and clustering, write `runs/clusters/`, then stop. No entity calls and no graph writes, so no `MODEL_*` is needed. |
| `--skip-signals` | Do not classify rules with System-1. Rules are written without the signal properties, which the planner reads as `behavioral`. |
| `--force-signals` | Ignore the signal answer cache and ask System-1 again. |
| `--output-md <path>` | Override default path for the raw Markdown report. |
| `--output-filtered-md <path>` | Override default path for the filtered Markdown report. |
| `--output-json <path>` | Override default path for the entities JSON file. |
 
### Example invocations
 
```bash
# WildFly 29 → 30: full pipeline including graph write
uv run python scripts/export_extract_populate_framework.py --framework wildfly 29.0.0 30.0.0
 
# Spring Boot 3.5 → 3.6: extract and LLM only, no graph
uv run python scripts/export_extract_populate_framework.py --framework spring-boot 3.5.0 3.6.0 --dry-run
 
# Angular 18 → 19: force complete refresh of all artifacts
uv run python scripts/export_extract_populate_framework.py --force --framework angular 18.0.0 19.0.0
```
 
---
 
## Supported frameworks
 
Nine framework keys are registered. Each has a display name (used in LLM prompts) and a registry key (used on the CLI).
 
| CLI key | Display name | Version source | Primary upstream data |
|---------|--------------|----------------|----------------------|
| `spring-boot` | Spring Boot | Maven Central (`spring-boot-dependencies`) | GitHub releases + BOM diff |
| `angular` | Angular | npm registry (`@angular/core`) | GitHub releases + optional blog insights |
| `wildfly` | WildFly | Maven Central (`org.wildfly:wildfly-dist`) | GitHub releases + migration guide + Jira enrichment |
| `eap` | JBoss EAP | Fixed version table (7.0–8.0) | Red Hat access.redhat.com HTML docs |
| `hibernate` | Hibernate ORM | Maven Central (`org.hibernate.orm:hibernate-core`) | GitHub releases + AsciiDoc migration guide (6+) |
| `resteasy` | RESTEasy | Maven Central (`org.jboss.resteasy:resteasy-core`) | GitHub releases |
| `infinispan` | Infinispan | Maven Central (`org.infinispan:infinispan-core`) | GitHub releases + upgrading guide fallback |
| `elytron` | WildFly Elytron | Maven Central (`org.wildfly.security:wildfly-elytron`) | GitHub releases (wildfly-security org) |
| `jakarta-ee` | Jakarta EE | Static spec version list (8–11) | Deterministic javax→jakarta namespace rules (no HTTP) |
 
All JBoss-ecosystem keys except `jakarta-ee` share the same downstream LLM prompts and entity schema (including WildFly-specific fields like `cli_operation` and `subsystem`).
 
---
 
## Phase 0 — Bootstrap and configuration
 
When the command starts:
 
1. **Environment loading** — A `.env` file (if present) is loaded so API keys, model provider settings, and SSL options are available.
2. **SSL verification** — If `SSL_VERIFY=false`, HTTP clients disable certificate validation (common behind corporate proxies). This applies to all outbound HTTP: GitHub, Maven Central, npm, Jira, Red Hat docs, and LLM provider endpoints.
3. **Framework lookup** — The `--framework` key is normalized (lowercased, spaces → hyphens) and looked up in a central registry. An unknown key exits immediately with a list of supported keys.
4. **Artifact directory creation** — Sibling directories under `runs/` are ensured to exist:
   - `runs/raw/` — raw Markdown reports
   - `runs/nodes/` — filtered/grouped Markdown
   - `runs/json/` — entities JSON
   - `runs/triage/` — System-1 triage distributions
   - `runs/research/` — per-row research dossiers
   - `runs/canonical/` — canonical entity audit
   - `runs/signals/` — rule detection signals (spec 027)
Default artifact naming pattern:
 
```
<framework-key>-<resolved-from>-to-<resolved-to>-changes.md          → raw
<framework-key>-<resolved-from>-to-<resolved-to>-changes_filtered.md → filtered
<framework-key>-<resolved-from>-to-<resolved-to>-entities.json       → JSON
```
 
Slashes in framework keys (none today, but supported) become hyphens in filenames.
 
---
 
## Phase 1 — Version resolution and chunking
 
Before any HTTP fetch, the pipeline resolves the requested version range against the framework's known release list.
 
### Resolution steps
 
1. **Fetch available versions** from the framework's canonical source (Maven metadata, npm registry, or a static table).
2. **Normalize** both endpoints to a comparable semver triple (e.g. `3.5` → `3.5.0`, `29` → `29.0.0`).
3. **Validate** that both endpoints exist in the available list (or can be resolved via wildcard rules).
4. **Compute chunk boundaries** — the range is split into consecutive hops through every intermediate release. For example, `3.3.0 → 3.5.0` with releases `[3.3.0, 3.3.1, 3.4.0, 3.5.0]` produces hops: `(3.3.0→3.3.1)`, `(3.3.1→3.4.0)`, `(3.4.0→3.5.0)`.
### Why chunking matters
 
Each hop triggers a separate call to the framework extractor. This mirrors how real upgrades happen (one release at a time) and keeps per-hop Markdown sections aligned with individual release notes. The final raw report contains one `## from → to` section per hop.
 
For JBoss Maven-based frameworks, prerelease artifacts (versions not ending in `.Final`) are filtered out by default unless `JBOSS_SKIP_PRERELEASE` is set to disable filtering.

### Hop granularity (`--hop-granularity`)

The hop boundaries above are selectable, because the ingestion step size — not
just the raw text — is what operators tune when a version range turns out to be
too coarse:

| Value | Hop boundaries | Typical use |
|-------|----------------|-------------|
| `patch` (default) | every released version in range | patch-level ingestion: each release gets its own `Version` node, rules, and BOM/CVE delta |
| `minor` | `X.Y.0` releases plus the requested endpoints (`3.3.12 → 3.4.0 → 3.4.2`) | one hop per minor line while still allowing patch endpoints |

`--hop-by-hop` then runs **the filter LLM, the entity LLM, and graph population
per hop** instead of once per range:

- Each hop writes its own `runs/raw/<fw>-<from>-to-<to>-changes.md`,
  `runs/nodes/..._filtered.md`, and `runs/json/...-entities.json` triple, and
  cache reuse is resolved per hop, so an interrupted range resumes at the first
  hop with missing artifacts.
- Each hop's `to_version` becomes its own `Version` node holding only that hop's
  rules, instead of one node at the range endpoint holding the whole range.
- Per-hop metadata means the BOM diff is computed hop-to-hop, which is where
  patch-level dependency and CVE movement becomes visible.
- `--output-md/--output-filtered-md/--output-json` are rejected in this mode
  because artifact paths are derived per hop.

Cost follows hop count: a minor line with 13 patch releases costs ~13 filter and
~13 entity LLM calls. `scripts/run_spring_boot_patch_ingest.sh` wraps the
Spring Boot patch-level run (`--skip-existing`, extract-only by default, GA-only
unless you set `SPRING_INCLUDE_PRERELEASE=1`).
Per-hop artifacts keep the `runs/json/<framework>-<from>-to-<to>-entities.json`
naming, so `python scripts/populate_graph.py --all` re-populates them hop by hop
without further changes.

#### Milestones and release candidates

Prereleases are ordinary versions: with `SPRING_INCLUDE_PRERELEASE=1` a
`4.0.9 → 4.1.0-RC1` patch-granularity run produces
`4.0.9→4.1.0-M1, M1→M2, M2→M3, M3→M4, M4→RC1`, each with artifacts, a
`Version` node, and rules. The run plan marks such hops with `*`.

- Their `sortableVersion` sits below the GA release they precede, so
  `4.1.0-M1 < 4.1.0-RC1 < 4.1.0` while `4.1.0` keeps its historical value — see
  [graph-schema.md](../01-foundation/graph-schema.md) and the `preRelease`
  property.
- A `4.0.6 → 4.1.0` path therefore includes the 4.1 milestone rules as early
  warning; a path ending at `4.1.0-M2` excludes later builds.
- `--hop-granularity minor` ignores milestones as hop boundaries (they are not
  line starts) but honours one when it is the requested endpoint, so
  `4.0.6 → 4.1.0-RC1` stays a single hop.
- A minor hop still **reads** the release notes of every release it covers
  (`HopContext.covered_versions`): all releases after `from` up to `to` on the
  target's `major.minor` line. `4.0.0 → 4.1.0` reads `4.1.0-M1 … 4.1.0-RC1` and
  `4.1.0`; `4.1.0 → 4.1.2` reads `4.1.1` and `4.1.2`. The GA notes alone only
  list changes since the last RC. Earlier-line patches (`4.0.x`) are not read —
  their fixes appear as forward ports in the new line's notes. Rows repeated
  across releases are kept once. Spring Boot only for now.

#### Version aliases

`FROM`/`TO` accept aliases, resolved against the discovered release list before
any artifact path or `Version` node is derived (the CLI prints
`Resolved latest → 4.2.0-RC2`):

| Alias | Resolves to |
|-------|-------------|
| `latest` | Newest discovered release (milestones/RCs included when discovered) |
| `latest-ga`, `latest-stable` | Newest GA release |
| `X.Y.Z-SNAPSHOT` | Newest published build of `X.Y.Z` — GA if released, else its newest milestone/RC. Errors if none is published. Snapshots have no release notes. |

#### Stale raw files

In `--hop-by-hop` mode a raw file whose `Resolved range` or hop sections do not
match exactly that hop (files from the old whole-range layout, e.g.
`4.0.0 → 4.1.0-RC1` with one section per milestone) is re-extracted
automatically, as if `--force-extract` were given for that hop.

#### Minor-line document attribution

Some sources describe a whole minor line rather than a release — Spring Boot
wiki pages are `Spring-Boot-{major}.{minor}-Release-Notes`. Such documents are
attached only to the hop that **enters** the line (`enters_new_minor_line`), so a
`3.1.0 → 3.2.4` patch-granular run attributes the 3.2 wiki content to
`3.1.12 → 3.2.0` once, instead of duplicating it onto all 13 hops of the 3.1 line
(the pre-granularity behaviour, measured at 57 duplicated rows per patch hop).
 
---
 
## Phase 2 — Raw release extraction (upstream fetch)
 
This phase produces **structured change records** before any LLM is involved. Each framework implements the same contract: given `(from_version, to_version)` for one hop, return a list of **documented changes**, each with:
 
| Field | Meaning |
|-------|---------|
| `type` | Classification: `breaking`, `mandatory_migration`, `deprecation`, `dependency_upgrade`, `behavioral`, `potential_breaking`, etc. |
| `confidence` | `confirmed` or `inferred` |
| `source_url` | Canonical URL for the change (release page, Jira issue, BOM POM, etc.) |
| `statement` | Human-readable description of the change |
 
Below is a per-framework breakdown of **where data is fetched**, **exact URLs**, **parameters**, and **authorization**.
 
---
 
### Spring Boot
 
#### Version discovery
 
| Item | Value |
|------|-------|
| URL | `https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-dependencies/maven-metadata.xml` |
| Method | GET |
| Auth | None |
| Response | XML listing all published Spring Boot versions |
 
#### Per-hop extraction
 
For each scanned version in the range, the extractor:
 
1. **Fetches GitHub release notes**
   - URL pattern: `https://api.github.com/repos/spring-projects/spring-boot/releases/tags/{tag}`
   - Tag candidates tried in order: `v{version}`, then `{version}` (e.g. `v3.4.0`, then `3.4.0`)
   - Headers:
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `Authorization: Bearer {GITHUB_TOKEN}` — **optional but strongly recommended** to avoid rate limits
   - Response field used: `body` (Markdown release notes)
2. **Parses release body** into individual statements (headings, bullet lists, categorized sections like "Deprecations", "Breaking Changes").
3. **Classifies** each statement into a change type and confidence level based on section headers and keyword heuristics.
3a. **Enriches GitHub issues** on those release-note rows when `GITHUB_TOKEN` is set and `SPRING_BOOT_GITHUB_ENRICHMENT` is not `false` (the default is on). Each row that cites `#NNNN` or a `spring-projects/spring-boot` issue/pull URL is filled from `GET /repos/spring-projects/spring-boot/issues/{n}`: the statement becomes a Title / Issue / Release block (same shape as WildFly Jira enrichment), `source_url` becomes the issue URL, and labels, issue type, and close reason are stored on metadata. Bodies lose the HTML-comment issue template, fenced code longer than 10 lines, and stack traces, then are collapsed and truncated to `GITHUB_ENRICH_BODY_MAX_CHARS` (default 1500). A body shorter than 200 characters that only says `Backport of #NNNN` or `Forward port of issue #NNNN` is replaced with that original issue's body, one level deep. Fetches run `GITHUB_ENRICH_MAX_CONCURRENT` at a time (default 8). HTTP 403/429 with `X-RateLimit-Remaining: 0` stops further GitHub enrichment requests for the rest of the run; a single issue failure never drops the hop. Without a token the rows stay as the one-line release text. Wiki rows are not enriched.
3b. **Fetches the minor-line wiki page** (`https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-{major}.{minor}-Release-Notes`) for bullets and the "Upgrading from" prose — **only when the hop enters that minor line** (see [Minor-line document attribution](#minor-line-document-attribution)). Direct `extract()` calls without a hop context still fetch it.
4. **Computes BOM dependency diff** (range-level, or hop-to-hop under `--hop-by-hop`):
   - Fetches `spring-boot-dependencies-{from}.pom` and `spring-boot-dependencies-{to}.pom` from Maven Central
   - URL pattern: `https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-dependencies/{version}/spring-boot-dependencies-{version}.pom`
   - Extracts managed dependency versions from both POMs and computes added/changed/removed coordinates
The BOM diff is attached to the extraction result metadata but the per-hop Markdown table is built from **release-note statements** only.
 
---
 
### Angular
 
#### Version discovery
 
| Item | Value |
|------|-------|
| URL | `https://registry.npmjs.org/@angular/core` |
| Method | GET |
| Auth | None |
| Response | JSON with a `versions` map; filtered to `\d+.\d+.\d+` release versions (no prerelease tags) |
 
#### Per-hop extraction
 
For each scanned version:
 
1. **Fetches GitHub release notes**
   - URL pattern: `https://api.github.com/repos/angular/angular/releases/tags/{tag}`
   - Tag candidates: `v{version}`, `{version}`
   - Same GitHub headers and optional `GITHUB_TOKEN` as Spring Boot
2. **Parses Angular-specific release format** — handles Angular's structured changelog sections (features, bug fixes, breaking changes) and extracts individual statements. The matching `CHANGELOG.md` section is merged in and de-duplicated against the release body.
3. **Enriches GitHub commits** when `GITHUB_TOKEN` is set and `ANGULAR_GITHUB_ENRICHMENT` is not `false` (the default is on). Each row whose text contains `angular/angular/commit/{sha}` is filled from `GET /repos/angular/angular/commits/{sha}`: the statement becomes Title / Commit / Release, plus `Breaking:`, `Deprecated:`, and `Issue: #N …` lines when the commit message has those footers or a `Fixes #N` trailer. The first fixed issue is fetched and its title plus the first 500 characters of its cleaned body are included. `BREAKING CHANGE` or a `!` header becomes `breaking / confirmed`; a `DEPRECATED` footer becomes `deprecation / confirmed`. Metadata records the package scope, commit type, pull number, fixed issues, and whether any file sits under `packages/*/schematics/`. A row with an Angular pull or issue link but no commit link uses the same issue enrichment as Spring Boot, without backport following. Cleaning, concurrency, and the primary rate-limit stop are shared with Spring Boot (`GITHUB_ENRICH_MAX_CONCURRENT`, `GITHUB_ENRICH_BODY_MAX_CHARS`). Without a token the rows stay as the changelog line. Blog insights are not enriched.
4. **Optional blog insight extraction** — a release insight strategy can scan the release body for links to angular.dev blog posts and extract supplementary migration guidance. These insights are stored in extraction metadata but do not appear in the raw Markdown table directly.
5. **Classifies** statements into change types.
---
 
### WildFly
 
WildFly has the richest extraction pipeline, including Jira enrichment (detailed in [Phase 3](#phase-3--jboss--wildfly-jira-enrichment)).
 
#### Version discovery
 
| Item | Value |
|------|-------|
| URL | `https://repo1.maven.org/maven2/org/wildfly/wildfly-dist/maven-metadata.xml` |
| Method | GET |
| Auth | None |
| Filtering | Versions ending in `.Final` only (unless prerelease skip is disabled) |
| Normalization | Maven versions like `30.0.1.Final` map to graph semver `30.0.1` |
 
#### Per-hop extraction (source priority chain)
 
The extractor tries sources in order until it obtains non-empty release text:
 
**Priority 1 — GitHub release**
 
| Item | Value |
|------|-------|
| URL | `https://api.github.com/repos/wildfly/wildfly/releases/tags/{tag}` |
| Tag format | `{major}.0.0.Final` (e.g. version `30.0.0` → tag `30.0.0.Final`) |
| GitHub headers | Same as above; optional `GITHUB_TOKEN` |
| Body processing | GitHub-flavored HTML/Markdown is normalized to plain Markdown |
 
**Priority 2 — Official migration guide**
 
| Item | Value |
|------|-------|
| URL | `https://docs.wildfly.org/{major}/Migration_Guide.html` |
| Method | GET |
| Auth | None |
| Processing | HTML is converted to Markdown-like text (headings, paragraphs, list items) |
 
**Priority 3 — WildFly blog**
 
| Item | Value |
|------|-------|
| URL | `https://www.wildfly.org/news/` (index page; individual release posts are discovered from there) |
| Fallback source URL recorded | `https://www.wildfly.org/news/` |
 
After obtaining body text:
 
1. Parse into individual **statements** (one per bullet/issue line).
2. **Jira enrichment** (see Phase 3).
3. **Classify** statements by inferred type.
4. **Apply WildFly CLI hints** — any statement containing a CLI migration operation pattern (e.g. `/subsystem=elytron:migrate`) is promoted to `mandatory_migration` with `confirmed` confidence.
5. Detect **stability level** from release body markers: `[experimental]`, `[preview]`, `[community]`, or default.
---
 
### JBoss EAP
 
EAP uses a **fixed version table** rather than Maven metadata:
 
| EAP version | Docs slug | Underlying WildFly base |
|-------------|-----------|------------------------|
| 7.0.0 | 7.0 | 10.1.0 |
| 7.1.0 | 7.1 | 11.0.0 |
| 7.2.0 | 7.2 | 13.0.0 |
| 7.3.0 | 7.3 | 18.0.0 |
| 7.4.0 | 7.4 | 26.1.0 |
| 8.0.0 | 8.0 | 29.0.0 |
 
#### Per-hop extraction
 
| Source | URL pattern |
|--------|-------------|
| Migration guide | `https://access.redhat.com/documentation/en-us/red_hat_jboss_enterprise_application_platform/{slug}/html/migration_guide/` |
| Release notes | `https://access.redhat.com/documentation/en-us/red_hat_jboss_enterprise_application_platform/{slug}/html/release_notes/` |
 
- Method: GET
- Auth: None (public documentation)
- Rate limiting: configurable delay between requests via `REDHAT_DOCS_DELAY_SEC` (default 2 seconds)
- Processing: HTML parsed with BeautifulSoup; headings and list items extracted to Markdown-like text
- **No Jira enrichment** for EAP (unlike WildFly)
Both documents are concatenated, parsed into statements, classified, and CLI hints applied.
 
---
 
### Hibernate ORM
 
#### Version discovery
 
Maven Central metadata for `org.hibernate.orm:hibernate-core`.
 
#### Per-hop extraction
 
For major version ≥ 6:
 
1. **AsciiDoc migration guide** (preferred):
   - URL: `https://raw.githubusercontent.com/hibernate/hibernate-orm/{tag}/migration-guide.adoc`
   - Tag candidates: `{version}`, `{version}.Final`
   - Parsed with an AsciiDoc-aware parser that extracts sectioned migration items
2. **GitHub release fallback**:
   - URL: `https://api.github.com/repos/hibernate/hibernate-orm/releases/tags/{tag}`
For major version < 6, GitHub releases are used directly.
 
---
 
### RESTEasy
 
#### Version discovery
 
Maven Central metadata for `org.jboss.resteasy:resteasy-core`.
 
#### Per-hop extraction
 
| Item | Value |
|------|-------|
| GitHub API URL | `https://api.github.com/repos/resteasy/resteasy/releases/tags/{tag}` |
| Tag candidates | `v{version}.Final`, `{version}.Final`, `{version}` |
| Processing | Release body parsed as Markdown; statements classified |
 
---
 
### Infinispan
 
#### Version discovery
 
Maven Central metadata for `org.infinispan:infinispan-core`.
 
#### Per-hop extraction
 
1. **GitHub release** — `https://api.github.com/repos/infinispan/infinispan/releases/tags/{tag}` (candidates: `{version}.Final`, `{version}`)
2. **Upgrading guide fallback** (if release body empty):
   - URL: `https://infinispan.org/docs/{major}.x/titles/upgrading/upgrading.html`
   - HTML converted to Markdown-like notes
---
 
### WildFly Elytron
 
#### Version discovery
 
Maven Central metadata for `org.wildfly.security:wildfly-elytron`.
 
#### Per-hop extraction
 
| Item | Value |
|------|-------|
| GitHub API URL | `https://api.github.com/repos/wildfly-security/wildfly-elytron/releases/tags/{tag}` |
| Tag candidates | `{version}.Final`, `{version}` |
| Post-processing | CLI migration hints applied (same as WildFly) |
 
---
 
### Jakarta EE
 
Jakarta EE is special: **no HTTP fetching**. When the upgrade crosses Jakarta EE 9 (the first release using `jakarta.*` namespaces instead of `javax.*`), the extractor emits a deterministic set of **namespace migration rules** — one per package mapping (e.g. `javax.servlet` → `jakarta.servlet`).
 
| Item | Value |
|------|-------|
| Supported spec versions | 8.0.0, 9.0.0, 9.1.0, 10.0.0, 11.0.0 |
| Source URL recorded | `https://jakarta.ee/specifications/platform/{major}/` |
| Precomputed entities | Yes — namespace rules include fully populated entity dicts, bypassing LLM for those fields |
 
If the range does not cross the EE 9 boundary, the extractor returns zero documented changes.
 
---
 
### Shared HTTP behavior
 
All extractors share these behaviors:
 
| Concern | Behavior |
|---------|----------|
| **Request caching** | A fetch runtime memoizes responses by URL within a single pipeline run, preventing duplicate HTTP calls |
| **Timeout** | 30 seconds default; 60 seconds for Red Hat docs |
| **SSL** | Controlled by `SSL_VERIFY` environment variable |
| **GitHub rate limits** | Without `GITHUB_TOKEN`: 60 requests/hour. With token: 5,000 requests/hour |
| **Error handling** | Extraction failures for a hop abort the pipeline with a descriptive error message |
 
---
 
## Phase 3 — JBoss / WildFly Jira enrichment
 
WildFly is the only framework that enriches raw statements with **Red Hat Jira issue data**. This happens after parsing the release body but before classification. The enrichment is **best-effort** — Jira unavailability never blocks the pipeline.
 
### Why enrichment exists
 
WildFly GitHub release notes often contain terse one-liners like:
 
```
[WFLY-17842] - Update documentation due to removal of sun.jdk as implicit dependency
```
 
The actual migration impact lives in the Jira issue description. Enrichment replaces or augments the one-liner with the full issue text so downstream LLM steps have enough context.
 
### Step 3a — Build a release-body issue index (no HTTP)
 
The raw release body (HTML or Markdown) is scanned with regular expressions for Jira issue keys. Supported key prefixes:
 
`WFLY`, `WFCORE`, `WFMP`, `JBEAP`, `EAP7`, `UNDERTOW`, `HAL`, `ISPN`, `HHH`
 
Three formats are recognized:
 
| Format | Example |
|--------|---------|
| Jira HTML export | `[<a href="https://issues.redhat.com/browse/WFLY-19397">WFLY-19397</a>] - Summary text` |
| PR-merge style | `WFLY-20880 Upgrade wildfly-core to 29.0.1.Final by @user in #19161` |
| Migration guide bullets | `- [ WFLY-11574 ] - Some of the web services tests …` |
 
For each match, the index stores:
 
- Issue key (e.g. `WFLY-19397`)
- One-line summary from the release body
- Issue type from the enclosing HTML section header (`Bug`, `Enhancement`, `Feature Request`, etc.)
- Canonical browse URL: `https://redhat.atlassian.net/browse/{KEY}`
Note: `issues.redhat.com` links found in HTML are converted to `redhat.atlassian.net` because the legacy host's REST API returns HTTP 301 redirects.
 
### Step 3b — Collect all issue keys to fetch
 
The union of:
 
- All keys from the release-body index
- All keys found in parsed statement text (catches migration-guide bullets not in the index)
### Step 3c — Fetch full Jira descriptions (parallel HTTP)
 
For each issue key, up to 4 concurrent requests:
 
**Primary: Atlassian REST API v2**
 
| Item | Value |
|------|-------|
| URL | `https://redhat.atlassian.net/rest/api/2/issue/{KEY}?fields=summary,description,issuetype,priority,status` |
| Method | GET |
| Headers | `Accept: application/json` |
| Auth | **None required** for public WildFly project issues |
| Timeout | 10 seconds per request |
| Fields used | `summary` (title), `description` (plain text in API v2) |
 
**Fallback: HTML page scraping**
 
If the REST API returns non-200:
 
| Item | Value |
|------|-------|
| URL | `https://redhat.atlassian.net/browse/{KEY}` |
| Method | GET |
| Headers | `Accept: text/html`, browser-like `User-Agent` |
| Extracted from HTML | `og:title` (preferred) or `<title>` for issue title; `og:description` or `<meta name="description">` for description text |
 
Failed fetches are silently skipped — the key simply won't appear in the details cache.
 
### Step 3d — Enrich statements in-place
 
For each parsed statement whose text contains a recognizable Jira key:
 
| Field | Enrichment |
|-------|------------|
| `source_url` | Set to `https://redhat.atlassian.net/browse/{KEY}` |
| `text` | Replaced with the richest available description using this priority: (1) full Jira REST/scraped description merged with release one-liner, (2) release body one-liner alone, (3) cleaned raw text with key prefix stripped |
| `issue_type` | Propagated from the release index when available |
 
The enriched text format when Jira details are available:
 
```
Title: {jira summary}
Jira: {full jira description or N/A}
Release: {release body one-liner or N/A}
```
 
This is what appears in the **Statement** column of the raw Markdown table and is what the filter LLM analyzes.
 
---
 
## Phase 4 — Storing raw release nodes (Markdown)
 
After all version hops are extracted, the pipeline renders a **single Markdown report** containing every raw change record. This is the "raw release nodes" artifact.
 
### Document structure
 
```markdown
# {Framework Name} — documented changes (extract-only)
 
- **Framework key:** `{key}`
- **Resolved range:** `{from}` → `{to}`
- **Generated (UTC):** {timestamp}
 
---
 
## `{prev}` → `{curr}`
 
| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| breaking | confirmed | https://... | Description text... |
| dependency_upgrade | inferred | https://... | Description text... |
 
## `{next_prev}` → `{next_curr}`
 
| Type | Confidence | Source | Statement |
| ...  | ...        | ...    | ...         |
```
 
### Column semantics
 
| Column | Content |
|--------|---------|
| **Type** | Rule classification from upstream extractor (`breaking`, `behavioral`, `dependency_upgrade`, `mandatory_migration`, `deprecation`, etc.) |
| **Confidence** | `confirmed` (explicitly stated in source) or `inferred` (heuristic classification) |
| **Source** | URL pointing to the origin — GitHub release, Jira issue, Red Hat doc, BOM POM, etc. For Jira-enriched WildFly items, this is the Atlassian browse URL |
| **Statement** | Full change description — for WildFly, this includes the enriched Jira text |
 
### Storage location and naming
 
Default path under `runs/raw/`:
 
```
{framework-key}-{resolved-from}-to-{resolved-to}-changes.md
```
 
Example: `wildfly-29.0.0-to-30.0.0-changes.md`
 
### Cell sanitization
 
Pipe characters, carriage returns, and newlines inside table cells are replaced with spaces to keep the Markdown table valid.
 
### What "raw nodes" means conceptually
 
Each table row is one **raw release node** — an atomic upstream change record before any LLM filtering. A typical WildFly major upgrade report contains hundreds of rows across multiple version hops. These rows include noise (test fixes, CI changes, copyright updates) that the next phase removes.
 
---
 
## Phase 4b — System-1 change triage
 
Before the filter LLM sees the raw table, an optional **System-1 classifier** labels every row. The question it answers is “does an upgrading user need to change anything?”, not “is this a bug fix?”. A row is dropped only when the deterministic rules or the model are confident it is noise. Anything uncertain is kept.
 
Triage runs only when **both** `TRIAGE_BASE_URL` and `TRIAGE_MODEL` are set. Leaving either empty is the off switch: no rules, no HTTP, and the raw file stays the 4-column table above. `--skip-triage` does the same for one invocation.
 
### Order of decisions
 
1. **Hard keep** (no model call): an Angular `BREAKING CHANGE` / `DEPRECATED` footer, a `!` in the commit header, an `ng update` schematic, a confirmed `breaking` / `deprecation` / `mandatory_migration` row, or a title that says the change removes, renames, deprecates, breaks, or requires something.
2. **Hard drop** (no model call): an Angular `docs` / `test` / `ci` / `build` commit whose files all sit outside `packages/*/src/`; a Spring Boot issue typed `documentation` or `task`; a Spring Boot issue closed as not planned; a row that is only a “full changelog” or WildFly Core pointer.
3. **Model.** Three fixed questions (`requires_action`, `category`, `impact`), versioned as `TRIAGE_QUESTIONS_VERSION`. A row is dropped only when all of these hold: action probability below `TRIAGE_DROP_MAX_ACTION_PROB` (default 0.20), category is `internal_fix`, `noise`, or `new_optional_feature` with probability at least `TRIAGE_DROP_MIN_CATEGORY_PROB` (default 0.80), and impact score below `TRIAGE_DROP_MAX_IMPACT_SCORE` (default 1.0).
 
A 4xx response or a connection failure on the first request keeps every row and records `Triage source = error` (one log line, then the run continues). A timeout or 5xx is retried twice and then keeps that row only.
 
### What is written
 
When triage ran, `runs/raw/<framework>-<from>-to-<to>-changes.md` still lists **every** row, kept and dropped, in the original order, with columns `Triage`, `Category`, `Cat. prob`, `P(action)`, `Impact`, and `Triage source`. The header gains:
 
```text
- **Triage:** <model> · questions v<N> · kept <k> / dropped <d> / error <e>
```
 
`runs/triage/<framework>-<from>-to-<to>-triage.jsonl` stores the full probability distributions. `runs/triage/...-summary.json` stores counts, summed `input_tokens`, and wall time. The filter LLM does not see the raw file directly: it receives only `keep` rows, with columns `Type | Confidence | Source | Statement | Category | Impact score`. `Impact score` is the classifier's 0–3 effort estimate; the filter uses it only to order items, and the prompt maps each `Category` to an output section. When the kept table is split into category groups, each part keeps the framework and range lines and leaves out the summary sections.
 
Re-running against a raw file that already has those columns makes no classifier calls. `--retriage-from-cache` reapplies the thresholds to the saved distributions and rewrites the `Triage` column. Classifying a raw file that has no extraction metadata (labels, files, commit type) logs a warning and recommends `--force-extract`.
 
Answers are cached under `ARTIFACT_CACHE_DIR/triage/`, keyed by questions version, model name, and state text.

`runs/nodes/*-changes_filtered.md` therefore holds only the migration-relevant changes built from the kept rows, and it is the only input the entity LLM sees. Next to it, `*-changes_filtered.md.input.sha256` records the hash of the filter input. When the kept rows change (`--force-triage`, `--retriage-from-cache`, new thresholds, or triage enabled on an old raw file), the CLI prints a warning and re-runs both the filter and the entity LLM, even without `--force-llm`. A filtered file from before triage with no hash file is reused only while the input is still the untriaged 4-column table. An existing `Version` node is still not repopulated.
 
If the kept table is larger than `FILTER_MAX_INPUT_TOKENS` (default 60000), the filter runs once per category group — breaking with deprecation, behaviour with config and security, dependency upgrades, then everything else — and the section outputs are concatenated.
 
---
 
## Phase 5 — Filter and group (raw → filtered nodes)

This phase is the `filter` mode path (`--entity-source filter`, research disabled, or `--skip-research`). When research ran and `ENTITY_SOURCE` is `dossier` (the default), the pipeline skips this call and builds the filtered document from dossier entities instead (Phase 5c).

The raw Markdown table is too noisy for direct entity extraction. A **first LLM call** transforms it into a curated, categorized migration document.
 
### LLM provider and model
 
The model is selected via environment variables (see [Environment variables](#environment-variables-and-model-configuration)). Supported providers:
 
| Provider | Client | Default model |
|----------|--------|---------------|
| AWS Bedrock | LangChain ChatBedrock | `eu.amazon.nova-pro-v1:0` |
| OpenAI | LangChain ChatOpenAI | From `MODEL_ID` |
| Anthropic | LangChain ChatAnthropic | From `MODEL_ID` |
| Ollama | LangChain ChatOllama | From `MODEL_ID` |
| OpenAI-compatible | ChatOpenAI with custom base URL | From `MODEL_ID` (works with LiteLLM, vLLM, etc.) |
 
Inference parameters: `temperature` and `top_p` from agent config (defaults: 0.7 and 1.0).
 
### Prompt design
 
The filter prompt instructs the model to act as an **expert software migration analyst**. The Markdown document is injected via a `{changes_text_markdown_table}` placeholder at the end of the prompt. When System-1 triage ran, that document contains only the kept rows plus `Category` and `Impact`; the model is told to use `Category` and to override it when the statement clearly contradicts it. When triage did not run, the placeholder is the full 4-column raw file.
 
#### Core rules given to the model
 
1. **Filter noise** — Remove rows representing tests, documentation-only updates, CI/CD, quickstarts, examples, refactors with no user-facing effect, and internal build changes. Keep only changes that force or strongly require user action.
2. **Consolidate and combine** — Merge multiple rows about the same migration (e.g. several Jakarta EE component upgrades) into one row with comma-separated Jira keys and a unified impact statement.
3. **Deduplicate** — Never repeat the same migration across sections.
4. **Transform columns** — Input columns `| Type | Confidence | Source | Statement |` become output columns `| # | JIRA | Title | Impact | Sources |`:
   - `#` — row number within section, starting at 1
   - `JIRA` — issue key extracted from Source URL (e.g. `WFLY-17948`); comma-separated when consolidated; `N/A` if none found
   - `Title` — short header summarizing the change
   - `Impact` — rewritten, actionable migration guidance (not a copy-paste of the raw statement)
   - `Sources` — comma-separated `Source` URLs of every raw row consolidated into the item; `N/A` when none
5. **Do not invent facts** — Only use information supported by the input records.
#### Required output sections (in order)
 
| Section | Emoji | Meaning |
|---------|-------|---------|
| Breaking Changes | 🔴 | Will cause failures if not addressed |
| Mandatory Migrations — Security & CVE Fixes | 🟠 | Security patches requiring action |
| Mandatory Migrations — Major Component Upgrades | 🟠 | Major version bumps, namespace changes |
| Mandatory Migrations — Security Configuration | 🟠 | Security subsystem changes |
| Behavioral Changes | 🟡 | Default value or lifecycle changes |
| Deprecations | 🟡 | APIs marked for future removal |
| Notable New Capabilities | 🔵 | Optional but recommended features |
 
Sections with zero items are omitted entirely.
 
#### Summary sections (required at bottom)
 
1. **Summary by Priority** — count table aggregating items by severity level
2. **Most Critical Items for Migration** — bulleted list of 3–5 highest-impact changes
#### Output format constraints
 
- Return **only** the structured Markdown document
- No conversational filler, no JSON, no code fences, no intro/outro text
- If the model wraps output in ` ```markdown ` fences, the pipeline strips them automatically
### Invocation details
 
| Parameter | Value |
|-----------|-------|
| Input | Complete raw Markdown report (entire document, all hops) |
| Message type | Single `HumanMessage` with the formatted prompt |
| Calls | Exactly **one** LLM call for the entire document |
| Retries | Up to `EXTRACTION_RATE_LIMIT_RETRIES` (default 3) with exponential backoff on rate-limit errors |
| Output | Filtered Markdown written to `runs/nodes/{base}-changes_filtered.md` |
 
### Example filtered output shape
 
```markdown
## 🔴 Breaking Changes
 
| # | JIRA | Title | Impact | Sources |
| :--- | :--- | :--- | :--- | :--- |
| 1 | WFLY-17842 | Removal of `sun.jdk` implicit dependency | The `sun.jdk` module is no longer added... | https://issues.redhat.com/browse/WFLY-17842 |
 
## 🟠 Mandatory Migrations — Security & CVE Fixes
 
| # | JIRA | Title | Impact | Sources |
| ... |
 
---
 
## Summary by Priority
| Priority Level | Count | Description |
| ... |
 
## 🚨 Most Critical Items for Migration
- ...
```
 
---
 
## Phase 5b — Per-change research

Research runs right after triage and before the filter LLM. It is optional. The stage runs only when `RESEARCH_BASE_URL` and `RESEARCH_MODEL_ID` are set. `TAVILY_API_KEY` is optional: without it the model has no `web_search` and reads the row Sources and the pages they link to with `fetch_url` only. Otherwise the pipeline logs one info line and the entity step receives the filtered Markdown exactly as before. `--skip-research` does the same for one invocation.

Every kept triage row becomes one research row: the title comes from the statement's `Title:` prefix, `Sources` are the issue, pull request, commit, and JIRA links in the statement (the row's Source only when there are none), and the triage `Category` gives a section hint. For each research row, a small OpenAI-compatible model may call two tools:

- `web_search` — Tavily search. Every query includes the framework name and the hop's target version; the tool appends them when the model leaves them out. Results are cached under `ARTIFACT_CACHE_DIR/research/search/`.
- `fetch_url` — readable text of a public page, capped by `RESEARCH_FETCH_MAX_CHARS`. GitHub issue, pull, and commit URLs are read through the GitHub REST API (the same token and parsers as GitHub enrichment). URLs that resolve to a private, loopback, or link-local address are refused.

The model returns a fact dossier: a short summary, cited findings, and `applies_when`. It does not write migration steps. A finding is kept only when its URL was fetched in that run and the page matches the hop's major.minor line or is version-neutral (an issue, pull request, or commit). A dossier whose findings are all dropped is `not_found`. A timeout, a tool-budget overrun, or invalid JSON becomes `status: error` with no findings. Using the tool budget exactly is not an overrun: the model is asked for the final dossier. Error and not-found dossiers are left out.

The filter LLM then receives the kept rows plus a `## Research` appendix: one block per researched row (`### <Title>`, `Row sources: …`, applicability, cited findings). It writes the consolidated migration document, using the research to pick sections, merge rows that are the same change, and name exact APIs in `Impact`. When the kept table is split into category groups, each part gets only the blocks of its rows. Finally the entity LLM receives that document plus a second `## Research` appendix: for each document row, the dossiers of the kept rows that share one of its `Sources`, merged.

`runs/research/<framework>-<from>-to-<to>-research.jsonl` stores one dossier per filtered row. `runs/research/...-summary.json` stores status counts, tool-call counts, cache and artifact hits, and wall time.

A later run reads the hop's `research.jsonl` first and reuses each row whose `row_key` matches, provided the line is not `error` and its `prompt_version` and `model` equal the current `PROMPT_VERSION` and `RESEARCH_MODEL_ID`. Rows that are missing or stale fall through to the row cache, then to the model. A complete JSONL therefore skips research for that hop without the row cache, and a hand edit to a dossier's `text` is used by the entity step. The run prints `Research <framework> <from>→<to>: N/M rows reused from <path>` and rewrites the JSONL at the end. The JSONL does not record `RESEARCH_ENABLE_THINKING` or whether Tavily was on, so changing either does not invalidate it; use `--force-research`. Finished `ok` and `not_found` dossiers are cached by prompt version, model id, framework, hop, and row key. Error dossiers are not cached, so the next run tries that row again. The row key is a hash of the section, title, JIRA keys, and source URLs, so renumbering a row does not invalidate research.

Each row is sent with the enriched raw statements behind it. Raw rows are matched by their Source URL and by the issue, pull request, commit, and JIRA links inside the statement. A Source URL shared by more than `RESEARCH_SHARED_URL_MAX_ROWS` raw rows is skipped, so a row citing a release-notes page does not receive every statement from that release. `--force-research` ignores that cache and any existing jsonl.

An exhausted Tavily quota is the one fail-closed case. HTTP 432, 433, or 401, or a 429 that is still failing after three attempts, stops the hop: in-flight rows are cancelled, finished dossiers stay in the row cache, and that hop writes no `research.jsonl`, no entities JSON, and no graph data. The process exits with code 2:

```text
Tavily quota exhausted at <framework> <from>→<to> (<done>/<total> rows researched). Re-run after the quota resets; finished rows are cached.
```

A later run researches only the rows that were not cached. Hops that already finished keep their artifacts.

---

## Phase 5c — Dossier entities

When research is enabled and not skipped, this is the default path (`ENTITY_SOURCE=dossier`). It replaces the filter LLM and the document-wide entity call.

After research, a deterministic gate reads each kept row's dossier:

- `**Action:** none` drops the row, except for `GATE_PROTECTED_CATEGORIES` (default `breaking`, `deprecation`, `security`), which stay so a wrong `none` on those rows is not silent.
- `required`, `unclear`, and a missing action line stay.
- `not_found`, `error`, and a missing dossier stay, marked `evidence: row_only`. The entity call then sees only the row text.

Rows that describe the same change are clustered by specific URLs: `/pull/`, `/commit/`, `/issues/`, `/browse/<KEY>`, or a `/compare/` URL with an anchor. A release tag, `CHANGELOG.md`, a docs page, or a blog page never joins rows. GitHub pull, commit, and issue URLs are compared as `github.com/<owner>/<repo>/<kind>/<id>`, so `commit/<sha>.patch`, `.diff`, `pull/<n>/files`, `pull/<n>/commits/<sha>`, and `patch-diff.githubusercontent.com` links meet the plain URL. A component larger than `CLUSTER_MAX_ROWS` (default 4) is split back to row-source edges, then to single rows, and the joining URLs are logged. `CLUSTER_CONFIRM=llm` (default `off`) can split a multi-row cluster when the research model says the titles are different changes.

One entity call per cluster uses the entity model (below), with `ENTITY_CONCURRENCY` (default 4) calls at a time. The call sees only that cluster's rows and dossiers and must return at most one entity. More than one is retried once; a cluster that still fails is recorded as `status: error` and left out of the entities file. Other clusters continue and their artifacts are written, but a hop with any failed cluster is **not populated** (an existing `Version` node is never repopulated, so a partial hop could not be completed later). The run exits with code 3 after the remaining hops; re-running retries only the failed clusters, because the others are cached. When every cluster of a hop fails, the hop's artifacts are removed and the run exits with code 1. Two entities in one hop that share a title get the later title suffixed with its source URL tail, so graph `MERGE` does not fold them together.

`runs/clusters/<framework>-<from>-to-<to>-clusters.jsonl` records every gate decision and each cluster's status. `runs/clusters/...-summary.json` records gate reasons, cluster sizes, entities written, empty results, errors, and wall time. `runs/json/...-entities.json` is the same batch as before, in cluster order. `runs/nodes/..._filtered.md` is rendered from those entities: the same section headings and `| # | JIRA | Title | Impact | Sources |` table, with `Impact` the first sentence of `reason` and no summary sections.

Each cluster is cached under `ARTIFACT_CACHE_DIR/entities/` by prompt version, model, framework, hop, cluster membership, and everything the call sends per member (triage category and impact, type, source, statement, dossier status, text, and sources), so a re-triage that changes a category re-runs the cluster. A changed dossier re-runs only that cluster. Error results are not cached. `--force-llm` ignores the cache. `entities.json.input.sha256` records the hash of those cache keys for inspection. A dossier run also deletes `_filtered.md.input.sha256`, so a later `--entity-source filter` run calls the filter LLM instead of reusing the rendered document as its output.

`--stop-after-clusters` writes the cluster artifact and stops. It does not call the entity model and does not need `MODEL_*`.

**Entity model.** With `ENTITY_MODEL_ID` unset, the entity calls use `MODEL_PROVIDER` / `MODEL_ID` through LangChain. With it set, they use a dedicated OpenAI-compatible model through the OpenAI SDK, and `MODEL_*` is not needed for the dossier path:

| Provider (`ENTITY_MODEL_PROVIDER`) | Output (`ENTITY_OUTPUT_FORMAT`) | Thinking |
|---|---|---|
| `openai` (default) | `json_schema` with `strict: true`, built from `MigrationEntitiesBatch`: every object closed and every field required, defaults removed. `json_object` and `off` are also accepted. | `reasoning_effort` = `ENTITY_REASONING_EFFORT` (default `high`). `ENTITY_THINKING=off` sends `none`, which only some models accept. |
| `deepseek` | `json_object`. DeepSeek has no schema-enforced mode, so `json_schema` is rejected at startup. The reply is still validated against the schema. | `thinking: {"type": "enabled"}` plus `reasoning_effort`; `ENTITY_THINKING=off` sends `disabled`. |

The base URL defaults to `https://api.openai.com/v1` or `https://api.deepseek.com` (`ENTITY_BASE_URL` overrides). The key is `ENTITY_API_KEY`, else `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`. `ENTITY_MAX_OUTPUT_TOKENS` (default 32000) covers reasoning and the JSON reply; a reply cut off at that limit, an empty reply, or a refusal counts as a failed attempt. The provider, model, output format, thinking, and effort are part of the cluster cache key and of `model` in the clusters summary, so changing any of them re-runs the clusters.

## Phase 6 — Entity extraction (filtered → JSON)

This phase is the `filter` mode path. Dossier mode (Phase 5c) does not send the filtered document to the entity model.

The filtered Markdown document is fed to a **second LLM call** that produces structured JSON entities.
 
### Prompt design
 
The entity extraction prompt instructs the model to analyze the structured changelog and extract **all migration-impacting changes** as typed entities. Two placeholders are filled in:
 
| Placeholder | Value |
|-------------|-------|
| `{framework}` | Framework display name (e.g. `WildFly`, `Spring Boot`, `Angular`) |
| `{changes_text}` | The filtered Markdown document. When research produced cited dossiers, a `## Research` appendix follows it: one block per row (`### <section> #<index> — <title>`) with the summary, findings, URLs, and `applies_when`. Error and not-found dossiers are left out. With research off, skipped, or empty, this value is the filtered Markdown byte for byte. |
 
#### Output schema
 
The model must return a JSON object:
 
```json
{
  "entities": [
    {
      "change_type": "string",
      "reason_type": "string",
      "reason": "string",
      "action_step": "string",
      "affected_properties": ["string"],
      "replacement_property": "string",
      "affected_classes": ["string"],
      "replacement_class": "string",
      "affected_dependencies": ["string"],
      "replacement_dependency": "string",
      "cli_operation": "string",
      "subsystem": "string"
    }
  ]
}
```
 
#### Field extraction guidelines (given to the model)
 
| Field | Required | Guidance |
|-------|----------|----------|
| `change_type` | Yes | One of: `breaking_change`, `mandatory_migration`, `dependency_upgrade`, `deprecation`, `behavior_change`, `configuration_change`, `namespace_migration`, `informational`, `other` |
| `reason_type` | Optional | Inferred category: `security`, `performance`, `spec_compliance`, `dependency_alignment`, `bugfix`, `other`, or empty |
| `reason` | Yes | 1–3 sentences: what changed, why it matters for upgraders, compatibility/behavior impact |
| `action_step` | Important | Concrete migration steps: what to change, how, why, and how to validate. Must not be vague ("review configuration") — must specify what to validate and what success looks like |
| `affected_properties` | If applicable | Dot-notation config property names |
| `replacement_property` | If applicable | New property name when one replaces another |
| `affected_classes` | If applicable | Fully qualified Java class names |
| `replacement_class` | If applicable | New class name when one replaces another |
| `affected_dependencies` | If applicable | Maven `groupId:artifactId` coordinates or component names |
| `replacement_dependency` | If applicable | New dependency with version if specified |
| `cli_operation` | If applicable | Exact WildFly CLI command fragment (only if explicitly present in source) |
| `subsystem` | If applicable | WildFly subsystem name (e.g. `undertow`, `elytron`, `messaging`) |
 
#### Extraction strategy (given to the model)
 
1. Prioritize breaking changes, mandatory migrations, removals, and spec transitions
2. Group repetitive dependency upgrades into single entries
3. Capture platform-level component upgrades relevant to the framework
4. Ignore test fixes, quickstart updates, CI/CD, documentation-only changes
5. Prefer fewer high-value entities over many fragmented low-signal entries
#### Output constraints
 
- Output **only** JSON — no markdown, no explanations, no trailing commas
- Double quotes everywhere
### Structured output mechanism
 
The pipeline uses LangChain's **`with_structured_output(MigrationEntitiesBatch)`** to constrain the model to the Pydantic schema. If structured output fails (validation error, provider incompatibility):
 
1. Fall back to a plain text LLM call
2. Parse JSON from the response (handles markdown code fences and surrounding text)
3. Validate against the Pydantic model
### Invocation details
 
| Parameter | Value |
|-----------|-------|
| Input | Complete filtered Markdown document |
| Message type | Single `HumanMessage` with the formatted prompt |
| Calls | Exactly **one** LLM call for the entire document |
| Retries | Same rate-limit retry policy as the filter step |
| Output validation | Response must contain at least one entity; empty entity list is treated as failure |
| Storage | Pretty-printed JSON (2-space indent, UTF-8, trailing newline) written to `runs/json/{base}-entities.json` |
 
### Example entity
 
```json
{
  "change_type": "breaking_change",
  "reason_type": "spec_compliance",
  "reason": "The sun.jdk module is no longer added as an implicit dependency to deployments. Applications relying on JDK-internal classes must explicitly declare the dependency.",
  "action_step": "If your application uses JDK-internal APIs previously available through the implicit sun.jdk module, add an explicit dependency on sun.jdk in jboss-deployment-structure.xml or MANIFEST.MF. Rebuild and redeploy, then verify no ClassNotFoundException occurs at runtime.",
  "affected_properties": [],
  "replacement_property": "",
  "affected_classes": [],
  "replacement_class": "",
  "affected_dependencies": ["sun.jdk"],
  "replacement_dependency": "",
  "cli_operation": "",
  "subsystem": ""
}
```
 
### Mapping entities to graph rule types
 
When entities are later written to the graph, `change_type` strings are mapped to graph rule types:
 
| Entity `change_type` contains | Graph rule type |
|-------------------------------|-----------------|
| `breaking`, `removal`, `removed` | `breaking` |
| `mandatory` | `mandatory_migration` |
| `deprecat` | `deprecation` |
| `dependency` + `upgrade` | `dependency_upgrade` |
| `potential` | `potential_breaking` |
| (default) | `behavioral` |
 
Each entity's `reason` and `action_step` are concatenated (up to 8,000 characters) to form the graph node's `statement` field.
 
---
 
## Phase 7 — Optional graph population
 
Unless `--dry-run` is set, the pipeline writes migration data to a **Neo4j or Memgraph** graph database.

### Pre-write canonicalization (spec 025)

Before any graph write, every affected entity in the batch is canonicalized by
code in `migration_oracle/pipeline/canonical/`:

1. **Normalize** (`normalize.py`) — a deterministic normalizer per framework
   profile (`profiles.py`): clean backticks/quotes/`@`/trailing `()`, split
   `@angular/core InjectFlags` / `@angular/router:Router` /
   `@angular/core/rxjs-interop RxResourceOptions` into `package` + bare symbol,
   split `Owner.member`, attach bare lower-case options to their rule's
   replacement (or only class) symbol, map template operators to
   `TemplateSyntax`, `NGxxxx` codes to `DiagnosticCode`, and dotted config keys
   to their file (`engines.*` → `package.json`, `angularCompilerOptions.*` →
   `tsconfig.json`, …). Spring Boot / WildFly are a no-op apart from computing
   `key`; their names stay byte-for-byte as written.
2. **Verify** (`api_index.py`) — for Angular, the golden public-API files
   (`goldens/public-api/<entry-point>/index.api.md`, `index.md` before v19, in
   `angular/angular`) are listed with one request
   (`git/trees/<tag>:goldens/public-api?recursive=1`) at both hop version tags
   and parsed from the API Extractor report: exported declarations, members at
   brace depth 1 (including the inline option fields of a function signature),
   `export { X as Y }` aliases of local declarations, and the members of the
   type of `export const X: Y`. Re-exports of imported symbols are skipped, so
   the declaring package owns the symbol. Indexes are cached under
   `ARTIFACT_CACHE_DIR/api-index/angular/<version>.json` (keyed by parser
   version) and fetched with `GITHUB_TOKEN`.
   - Each symbol resolves to one entry point: the LLM `package` if the symbol is
     there, else the only entry point, else the one matching a dependency of the
     rule, else the primary entry point (`@angular/core` beats
     `…/primitives/*` and `…/testing`). Otherwise `ambiguous`.
   - Bare options get their owner from the index first (the one rule symbol
     whose API lists the option), then the rule's replacement / only class.
   - Unresolved packages get `npm:?#<symbol>` with `verified: false`; nothing is
     dropped. When one version's goldens are missing (for example a `to` tag
     that does not exist yet) the index is `partial` and still used; when none
     load it is `unavailable` and every npm entity is `verified: false`.
   - Maven entities are `verified: unchecked` (no API index yet).
3. **Audit** (`run.py`) — one line per occurrence goes to
   `runs/canonical/<framework>-<from>-to-<to>-canonical.jsonl` plus a
   `…-summary.json` (counts per kind, verified percentages, collapsed raw
   names, unverified keys for manual review). `--dry-run` writes both files
   without graph writes — the cheap way to review a hop.

Entity nodes (`Class`, `ApplicationProperty`, `Dependency`, and the new
`TemplateSyntax` / `DiagnosticCode`) merge on the canonical `key` and carry
`name`, `package`, `symbol`, `member`, `file`, `ecosystem`, `verified`. `name`
remains the identifier the scanners and MCP queries match on.

### Pre-write rule signals (spec 027)

Right after canonicalization and before any graph write, every rule is
classified by **how a service shows that the rule applies**:

| `signal` | Decided by | Example |
|---|---|---|
| `symbol` | the code uses a named API | `TestBed.get` removed |
| `config` | a config key is set | `angularCompilerOptions.strictStandalone` default changed |
| `dependency` | a package is declared (optionally in a range) | `@angular/animations` deprecated |
| `syntax` | template syntax is used | `in` is an operator |
| `behavioral` | the API name is not enough; the code must be read or a person asked | `onDestroy` timing |
| `universal` | every service on the hop is affected | minimum Node / TypeScript |

The stage is one System-1 request per rule per question version (the same
endpoint as triage), cached under `ARTIFACT_CACHE_DIR/signals/` by question
version, model, framework and state — and the state contains the canonical
keys, so a canonicalization change re-asks only the rules it affects. One
`signal` choice plus one `feature.<id>` `noul` per feature travel in the same
request, so the state goes on the wire once per rule. `--force-signals` ignores
the cache.

The model picks the type and the features; **code decides what to search for**.
Only `removed` and `mentioned` entities count — finding the *replacement* in a
service means it has already migrated — and only the kind the type searches
(`symbol` → class/member, `config` → property with a known file, `dependency` →
dependency, `syntax` → syntax token). Two rules keep a wrong type from
excluding a rule that applies:

- **The guard.** A type with no key to search for becomes `behavioral`
  (`signalSource: guard`). A `config` key without a known file, or a symbol with
  an unresolved package (`npm:?#X`), is not searchable by key.
- **The floors.** `symbol` / `config` / `dependency` / `syntax` need
  `SIGNAL_SEARCHABLE_MIN_PROB` (0.70); `universal` needs
  `SIGNAL_UNIVERSAL_MIN_PROB` (0.60). Below the floor → `behavioral`
  (`signalSource: low_confidence`). Features are tagged at or above
  `SIGNAL_FEATURE_MIN_PROB` (0.50).

A rule whose entities are all dependencies and whose change is a
`component_upgrade` is `dependency` by rule, without asking the model for the
type (`signalSource: rule`); its features are still requested.

With Nimble unset or unreachable the stage logs once, writes no signal
properties, and populate continues. `--skip-signals` does the same for one
invocation. Either way the summary records `nimble: disabled` or `unavailable`,
and hops already in the graph can be backfilled later (see below). A rule
without the properties is read by the planner as `behavioral`.

Written on `MigrationRule` in the same session as the rule: `signal`,
`signalConfidence`, `signalSource`, `signalKeys`, `features`,
`signalQuestionsVersion`, `signalModel`.

`runs/signals/<framework>-<from>-to-<to>-signals.jsonl` holds one line per rule
(rendered state, every probability, the chosen type, source, guard/floor reason,
keys, features, cache hit, input tokens); `…-summary.json` counts rules per
signal, per source and per feature plus guard, low-confidence, error and cache
figures.

**Backfill.** Hops already in the graph are never repopulated, so their rules
would keep no classification. `scripts/classify_signals.py` reads the cached
`runs/json/*-entities.json`, canonicalizes, classifies, and runs
`MATCH (r:MigrationRule {ruleId: $id}) SET r += $props`. It sets only those
properties, is idempotent, and reports `ruleId`s that are not in the graph:

```bash
python scripts/classify_signals.py --framework angular --all
python scripts/classify_signals.py --framework spring-boot 3.5.0 4.0.0 --dry-run
```

### Pre-write checks
 
1. **Migration search indexes** are ensured (with unsupported index types silently ignored).
2. **Version existence check** — if a `Version` node for this framework and target version already exists, the graph write is skipped entirely (idempotent).
### Data written
 
For each entity in the JSON batch, the pipeline creates:
 
| Graph element | Source |
|---------------|--------|
| `Version` node | Target version metadata (framework name, sortable version, stability level if known) |
| `MigrationRule` node per entity | Mapped rule type, `confirmed` confidence, synthetic statement, source URL |
| Precomputed entity properties | Full entity dict attached for rich querying (classes, dependencies, CLI ops, subsystems) |
 
The primary source URL for all rules defaults to the last extraction's first documentation source URL (typically the GitHub release or migration guide page).
 
### Database connection
 
The graph driver is obtained from environment configuration (Neo4j URI, credentials). The driver is always closed after the write attempt, success or failure.
 
---
 
## Caching, idempotency, and force flags
 
The pipeline is designed for **incremental re-runs**. Each stage independently checks for existing artifacts.
 
| Condition | Behavior |
|-----------|----------|
| Raw MD exists, no `--force-extract` | Skip all HTTP extraction; read existing MD |
| Entities JSON exists, no `--force-llm` | Skip both LLM calls when the entity input digest still matches. A new or changed research appendix regenerates the entities JSON. |
| Research configured | Research only the filtered rows whose cache entry is missing. `--skip-research` leaves the entity input unchanged. `--force-research` ignores the row cache. |
| Tavily quota exhausted (432, 433, 401, or 429 after retries) | Exit code 2. No `research.jsonl`, entities JSON, or graph write for the current hop. Finished rows stay cached. |
| Filtered MD exists, no `--force-llm`, raw was cached | Skip filter LLM; reuse filtered MD, but still run entity LLM if JSON missing |
| `--force-extract` only | Re-extract and overwrite raw MD; reuse filtered MD and JSON if present (with warning) |
| `--force-llm` only | Re-run both LLM steps; reuse raw MD if present |
| `--force` | Re-run everything |
| `--dry-run` | Run all non-graph steps; write the `runs/canonical/` audit artifacts; skip graph write |
 
### Stale artifact warnings
 
If raw Markdown was regenerated but cached JSON was reused, the pipeline prints a warning recommending `--force-llm` to keep artifacts consistent. The same applies when raw MD is regenerated but cached filtered MD is reused.
 
---
 
## Environment variables and model configuration
 
### LLM provider
 
| Variable | Default | Purpose |
|----------|---------|---------|
| `MODEL_PROVIDER` | `bedrock` | One of: `bedrock`, `openai`, `anthropic`, `ollama`, `litellm`, `google` |
| `MODEL_ID` | `eu.amazon.nova-pro-v1:0` | Model identifier for the chosen provider |
| `AWS_REGION` | `eu-central-1` | AWS region for Bedrock |
| `OPENAI_API_KEY` | — | API key for OpenAI or compatible servers |
| `OPENAI_BASE_URL` | — | Custom OpenAI-compatible endpoint (LiteLLM, vLLM, etc.) |
| `LITELLM_BASE_URL` | — | Alternative base URL for LiteLLM |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `DISABLE_THINKING` | `false` | Disable extended thinking on Bedrock models |
 
### Upstream fetching
 
| Variable | Default | Purpose |
|----------|---------|---------|
| `GITHUB_TOKEN` | — | GitHub API bearer token (strongly recommended). Required for Spring Boot issue enrichment |
| `GITHUB_ENRICH_MAX_CONCURRENT` | `8` | Parallel GitHub issue and commit fetches during enrichment |
| `GITHUB_ENRICH_BODY_MAX_CHARS` | `1500` | Maximum cleaned GitHub issue or commit body length |
| `SPRING_BOOT_GITHUB_ENRICHMENT` | `true` | Set to `false` to keep Spring Boot release rows unenriched |
| `ANGULAR_GITHUB_ENRICHMENT` | `true` | Set to `false` to keep Angular release and changelog rows unenriched |
| `SSL_VERIFY` | `true` | Set to `false` to disable TLS certificate verification |
| `TRIAGE_BASE_URL` | empty | System-1 classifier origin, for example `http://gpuserver1.neterra.skrill.net:8002`. Empty disables triage |
| `TRIAGE_ENDPOINT_PATH` | `/v1/systemone` | Path joined onto `TRIAGE_BASE_URL` |
| `TRIAGE_MODEL` | empty | Model name sent as `model` (currently `nimble`). Empty disables triage |
| `TRIAGE_API_KEY` | empty | Sent as `Authorization: Bearer …` only when set. The local deployment does not need it |
| `TRIAGE_TIMEOUT_SEC` | `30` | Per-request timeout |
| `TRIAGE_MAX_CONCURRENT` | `2` | Parallel classifier calls. The server serialises work, so higher values only queue |
| `TRIAGE_STATE_MAX_CHARS` | `6000` | Cap on the state string sent for one row |
| `TRIAGE_DROP_MAX_ACTION_PROB` | `0.20` | Drop only when P(action) is below this |
| `TRIAGE_DROP_MIN_CATEGORY_PROB` | `0.80` | Drop only when the chosen noise-side category is at least this confident |
| `TRIAGE_DROP_MAX_IMPACT_SCORE` | `1.0` | Drop only when the impact score is below this |
| `FILTER_MAX_INPUT_TOKENS` | `60000` | Above this, the filter LLM runs once per triage category group |
| `RESEARCH_BASE_URL` | empty | OpenAI-compatible API root for the research model, for example `http://gpuserver2.neterra.skrill.net:8010/v1`. A trailing `/chat/completions` is stripped. Empty disables research |
| `RESEARCH_MODEL_ID` | empty | Model id sent to that server, for example `/models/Qwen3.6`. Empty disables research |
| `RESEARCH_API_KEY` | empty | Sent as `Authorization: Bearer …` only when set |
| `RESEARCH_ENABLE_THINKING` | `false` | Sent as `chat_template_kwargs.enable_thinking` |
| `RESEARCH_MAX_CONCURRENT` | `4` | Parallel research rows |
| `RESEARCH_MAX_TOOL_CALLS` | `12` | Tool calls allowed for one row |
| `RESEARCH_TIMEOUT_SEC` | `240` | Per-row budget for the whole tool-calling loop |
| `RESEARCH_MODEL_TIMEOUT_SEC` | `60` | Timeout for one model HTTP request, capped at `RESEARCH_TIMEOUT_SEC` |
| `RESEARCH_SEARCH_RESULTS` | `5` | Tavily hits returned to the model |
| `RESEARCH_FETCH_MAX_CHARS` | `20000` | Cap on fetched page text |
| `RESEARCH_SHARED_URL_MAX_ROWS` | `3` | A Source URL shared by more raw rows than this (release-notes page, release tag, `CHANGELOG.md`) is not used to attach raw statements |
| `RESEARCH_RAW_CONTEXT_MAX_CHARS` | `8000` | Cap on the raw statements attached to one research row |
| `TAVILY_API_KEY` | empty | Tavily Search key. Empty = fetch-only research (no `web_search`) |
| `ENTITY_MAX_INPUT_TOKENS` | `60000` | Above this, the filter-mode entity LLM runs once per filtered change section (summary sections are skipped) and the entities are concatenated |
| `ENTITY_SOURCE` | `dossier` when research ran, otherwise `filter` | `dossier` builds entities from research dossiers. `filter` keeps the filter LLM, then the document entity call. Overridden by `--entity-source` |
| `ENTITY_CONCURRENCY` | `4` | Parallel dossier entity calls |
| `CLUSTER_MAX_ROWS` | `4` | Clusters larger than this are split back to row-source edges, then to single rows |
| `CLUSTER_CONFIRM` | `off` | `llm` asks the research model whether each multi-row cluster is one change |
| `GATE_PROTECTED_CATEGORIES` | `breaking,deprecation,security` | Kept even when the dossier says `**Action:** none` |
| `SIGNAL_STATE_MAX_CHARS` | `4000` | Cap on the state string sent for one rule to the signal classifier |
| `SIGNAL_SEARCHABLE_MIN_PROB` | `0.70` | `symbol` / `config` / `dependency` / `syntax` below this probability become `behavioral` |
| `SIGNAL_UNIVERSAL_MIN_PROB` | `0.60` | `universal` below this probability becomes `behavioral` |
| `SIGNAL_FEATURE_MIN_PROB` | `0.50` | A feature is tagged on the rule at or above this probability |
| `JBOSS_SKIP_PRERELEASE` | `1` | When `1`/`true`/`yes`, filter Maven versions to `.Final` suffix only |
| `REDHAT_DOCS_DELAY_SEC` | `2.0` | Delay between Red Hat documentation requests (EAP) |
 
### Resilience
 
| Variable | Default | Purpose |
|----------|---------|---------|
| `EXTRACTION_RATE_LIMIT_RETRIES` | `3` | Max retry attempts on LLM rate-limit errors (exponential backoff: 2s, 4s, 8s) |
 
### Graph database
 
Connection details come from standard Neo4j/Memgraph environment variables configured in the graph driver module (URI, username, password).
 
---
 
## Failure modes and retries
 
| Failure point | Behavior |
|---------------|----------|
| Unknown framework key | Exit code 1; prints supported keys |
| Version resolution error | Exit code 1; prints resolution error |
| Extraction HTTP failure for a hop | Exit code 1; prints `{prev} → {curr}` and error message |
| Filter LLM returns empty | Exit code 1 |
| Entity LLM returns no entities | Exit code 1 |
| Cached JSON fails validation | Exit code 1; suggests `--force-llm` |
| Cached JSON has zero entities | Exit code 1; suggests `--force-llm` |
| LLM rate limit (429) | Automatic retry with exponential backoff |
| Jira fetch failure | Silently degraded; enrichment uses release one-liner only |
| Graph version already exists | Exit code 0; graph write skipped |
| Tavily quota exhausted during research | Exit code 2; current hop writes no research jsonl, entities JSON, or graph data. Earlier hops stay as they are |
| `--dry-run` | Exit code 0 after LLM steps; no graph write |
 
---
 
## End-to-end example walkthrough
 
**Command:**
 
```bash
uv run python scripts/export_extract_populate_framework.py --framework wildfly 29.0.0 30.0.0
```
 
### Step-by-step
 
1. **Bootstrap** — Loads `.env`, registers WildFly extractor, creates `runs/raw`, `runs/nodes`, `runs/json`.
2. **Version resolution** — Fetches Maven metadata for `org.wildfly:wildfly-dist`. Resolves `29.0.0` and `30.0.0`. Computes hops through every intermediate `.Final` release (e.g. `29.0.0→29.0.1`, `29.0.1→30.0.0`).
3. **Extraction (hop 1: 29.0.0→29.0.1)** —
   - GET GitHub release `29.0.1.Final` from `wildfly/wildfly`
   - Parse release body into ~8 statements
   - Index Jira keys from HTML (e.g. `WFLY-18341`, `WFLY-18294`)
   - Fetch Jira details from `redhat.atlassian.net/rest/api/2/issue/WFLY-18341?fields=summary,description,...`
   - Enrich statements with full Jira descriptions
   - Classify and apply CLI hints
   - Produce ~8 documented changes
4. **Extraction (hop 2: 29.0.1→30.0.0)** —
   - GET GitHub release `30.0.0.Final`
   - Parse ~200+ issue lines
   - Fetch Jira details for all unique keys (4 concurrent, 10s timeout each)
   - Enrich, classify, CLI hints
   - Produce ~200 documented changes
5. **Render raw Markdown** — Write `runs/raw/wildfly-29.0.0-to-30.0.0-changes.md` with two `## hop` sections and a 4-column table (~208 rows total).
6. **Filter LLM** — Send entire raw MD to the filter prompt. Model returns categorized document with ~30 consolidated items across Breaking/Mandatory/Behavioral/Deprecation/New Capabilities sections plus summary. Write `runs/nodes/wildfly-29.0.0-to-30.0.0-changes_filtered.md`.
7. **Entity LLM** — Send filtered MD to the whole-version extraction prompt with `{framework}=WildFly`. Model returns JSON with ~25 entities. Write `runs/json/wildfly-29.0.0-to-30.0.0-entities.json`.
8. **Graph write** — Check if WildFly 30.0.0 exists in graph. If not, create Version node + 25 MigrationRule nodes with precomputed entity properties. Print count of rules written.
**Total LLM calls:** 2 (one filter, one entity extraction).
 
**Total HTTP calls:** ~1 Maven metadata + ~2 GitHub releases + ~200 Jira REST calls (cached/deduplicated across hops) + optional migration guide fetches.
 
---
 
## Summary
 
The export-extract-populate-framework pipeline is a **four-stage materialization** of framework migration knowledge:
 
1. **Extract** — Deterministic HTTP fetching and parsing, with WildFly-specific Jira enrichment, producing raw tabular Markdown.
2. **Filter** — First LLM call removes noise, merges related changes, and categorizes by migration severity.
3. **Entity-extract** — Second LLM call produces typed JSON entities with actionable migration steps.
4. **Populate** — Optional graph write for queryable migration rules linked to framework versions.
Each stage caches its output independently, supports forced refresh via CLI flags, and degrades gracefully when optional enrichment sources (Jira, blog fallbacks) are unavailable.