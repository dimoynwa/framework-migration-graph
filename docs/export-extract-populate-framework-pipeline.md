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
11. [Phase 6 — Entity extraction (filtered → JSON)](#phase-6--entity-extraction-filtered--json)
12. [Phase 7 — Optional graph population](#phase-7--optional-graph-population)
13. [Caching, idempotency, and force flags](#caching-idempotency-and-force-flags)
14. [Environment variables and model configuration](#environment-variables-and-model-configuration)
15. [Failure modes and retries](#failure-modes-and-retries)
16. [End-to-end example walkthrough](#end-to-end-example-walkthrough)

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
│  4. FILTER/GROUP LLM  →  runs/nodes/...-changes_filtered.md                 │
│     Single call; Markdown in → categorized Markdown out                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. WHOLE-VERSION ENTITY LLM  →  runs/json/...-entities.json                │
│     Single call; filtered Markdown in → structured JSON out                  │
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

- **Two separate LLM calls**, not one: first call cleans and structures the document; second call extracts typed JSON entities. This separation keeps each prompt focused and reduces hallucination on noisy raw input.
- **Whole-document LLM calls**: both LLM steps send the entire Markdown document in a single request (not batched per row). This allows the model to deduplicate, merge related upgrades, and maintain cross-item context.
- **Incremental caching**: raw Markdown, filtered Markdown, and entities JSON are persisted independently. Re-runs skip expensive steps when artifacts already exist.

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
| `--force-llm` | Always call both LLM steps and overwrite filtered Markdown and entities JSON, even if they already exist. |
| `--force` | Shorthand for `--force-extract` **and** `--force-llm`. |
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
4. **Artifact directory creation** — Three sibling directories under `runs/` are ensured to exist:
   - `runs/raw/` — raw Markdown reports
   - `runs/nodes/` — filtered/grouped Markdown
   - `runs/json/` — entities JSON

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

4. **Computes BOM dependency diff** (range-level, not per-hop):
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

2. **Parses Angular-specific release format** — handles Angular's structured changelog sections (features, bug fixes, breaking changes) and extracts individual statements.

3. **Optional blog insight extraction** — a release insight strategy can scan the release body for links to angular.dev blog posts and extract supplementary migration guidance. These insights are stored in extraction metadata but do not appear in the raw Markdown table directly.

4. **Classifies** statements into change types.

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

## Phase 5 — Filter and group (raw → filtered nodes)

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

The filter prompt instructs the model to act as an **expert software migration analyst**. The full raw Markdown document is injected via a `{changes_text_markdown_table}` placeholder at the end of the prompt.

#### Core rules given to the model

1. **Filter noise** — Remove rows representing tests, documentation-only updates, CI/CD, quickstarts, examples, refactors with no user-facing effect, and internal build changes. Keep only changes that force or strongly require user action.

2. **Consolidate and combine** — Merge multiple rows about the same migration (e.g. several Jakarta EE component upgrades) into one row with comma-separated Jira keys and a unified impact statement.

3. **Deduplicate** — Never repeat the same migration across sections.

4. **Transform columns** — Input columns `| Type | Confidence | Source | Statement |` become output columns `| # | JIRA | Title | Impact |`:
   - `#` — row number within section, starting at 1
   - `JIRA` — issue key extracted from Source URL (e.g. `WFLY-17948`); comma-separated when consolidated; `N/A` if none found
   - `Title` — short header summarizing the change
   - `Impact` — rewritten, actionable migration guidance (not a copy-paste of the raw statement)

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

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-17842 | Removal of `sun.jdk` implicit dependency | The `sun.jdk` module is no longer added... |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| ... |

---

## Summary by Priority
| Priority Level | Count | Description |
| ... |

## 🚨 Most Critical Items for Migration
- ...
```

---

## Phase 6 — Entity extraction (filtered → JSON)

The filtered Markdown document is fed to a **second LLM call** that produces structured JSON entities.

### Prompt design

The entity extraction prompt instructs the model to analyze the structured changelog and extract **all migration-impacting changes** as typed entities. Two placeholders are filled in:

| Placeholder | Value |
|-------------|-------|
| `{framework}` | Framework display name (e.g. `WildFly`, `Spring Boot`, `Angular`) |
| `{changes_text}` | The complete filtered Markdown document |

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
| Entities JSON exists, no `--force-llm` | Skip both LLM calls; load JSON from disk |
| Filtered MD exists, no `--force-llm`, raw was cached | Skip filter LLM; reuse filtered MD, but still run entity LLM if JSON missing |
| `--force-extract` only | Re-extract and overwrite raw MD; reuse filtered MD and JSON if present (with warning) |
| `--force-llm` only | Re-run both LLM steps; reuse raw MD if present |
| `--force` | Re-run everything |
| `--dry-run` | Run all non-graph steps; skip graph write |

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
| `GITHUB_TOKEN` | — | GitHub API bearer token (strongly recommended) |
| `SSL_VERIFY` | `true` | Set to `false` to disable TLS certificate verification |
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
