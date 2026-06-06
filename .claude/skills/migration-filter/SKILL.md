---
name: migration-filter
description: >
  Filters, deduplicates, and categorizes raw framework migration change records into a
  structured, severity-ordered Markdown report. Use this skill whenever a user attaches or
  pastes a raw migration table (with columns Type | Confidence | Source | Statement) and
  asks to filter, categorize, prioritize, or clean up the changes. Also trigger when the
  user says things like "filter this migration output", "categorize these changes",
  "turn this raw changelog into a migration doc", "clean up these migration records",
  "which changes are breaking", "prioritize these changes", or "run the filter prompt on
  this". Always trigger when a raw 4-column migration table is present alongside any
  request to process, organize, or report on migration changes — even if the user phrases
  it casually. This skill handles Phase 5 (filter-and-group) of the Migration Oracle
  pipeline, producing the filtered Markdown artifact that feeds Phase 6 entity extraction.
---

# Migration Filter

Transforms a raw, noisy migration change table into a clean, severity-ordered Markdown
document. This is **Phase 5** of the Migration Oracle pipeline: the filter-and-group LLM
call that runs between raw extraction and entity extraction.

---

## Inputs

- **Raw migration table**: A Markdown document with a 4-column table per hop:
  `| Type | Confidence | Source | Statement |`
  Attached as a file, pasted inline, or already present in the conversation.
- **Framework name** (optional): e.g. `WildFly`, `Spring Boot`, `Angular`. Infer from the
  document if not stated — it usually appears in the section headings.

If no document is present, ask once: "Please attach or paste the raw migration table you'd
like me to filter."

---

## Output

Return **only** the structured Markdown document described below. No conversational text
before or after, no JSON, no code fences wrapping the entire output.

### Required sections (in order, omit any section with zero items)

```
## 🔴 Breaking Changes
## 🟠 Mandatory Migrations — Security & CVE Fixes
## 🟠 Mandatory Migrations — Major Component Upgrades
## 🟠 Mandatory Migrations — Security Configuration
## 🟡 Behavioral Changes
## 🟡 Deprecations
## 🔵 Notable New Capabilities
```

Under each section heading, output a Markdown table with **exactly** these columns:

```
| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
```

### Required summary sections (always present, at the bottom)

```
## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | [X] | Must fix before migrating. |
| 🟠 **Mandatory** | [X] | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | [X] | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | [X] | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration
- ...
- ...
- ...
```

---

## Filtering rules (apply all before writing any output)

### Rule 1 — Filter noise
Remove rows that represent **only**:
- Internal test fixes with no user-facing behavior change
- Documentation-only updates
- CI/CD pipeline changes
- Quickstart or sample app changes
- Internal refactors with zero impact on public APIs, config, or runtime behavior
- Build infrastructure changes

Keep any change that **forces or strongly requires** an upgrading user to modify their
code, configuration, dependencies, runtime, deployment, or environment.

### Rule 2 — Consolidate and combine
If multiple rows relate to the same overarching migration (e.g. several Jakarta EE
component upgrades), merge them into **one row**. Combine their JIRA keys (comma-separated
in the `JIRA` column) and write a single unified impact statement.

### Rule 3 — Deduplicate
Never repeat the same migration in more than one row or section. If the same required
action appears across several raw rows, produce exactly one consolidated item.

### Rule 4 — Transform columns
The input has `| Type | Confidence | Source | Statement |`. The output must use
`| # | JIRA | Title | Impact |`. Derive each output column as follows:

| Output column | Derivation rule |
|---|---|
| `#` | Incrementing row number within the section, starting at 1. Reset to 1 for each new section. |
| `JIRA` | Extract the issue key from the `Source` URL (e.g. `WFLY-17948` from a Jira URL). If multiple rows were consolidated, comma-separate all keys. If no key can be confidently extracted, write `N/A`. Do **not** include the full URL. |
| `Title` | A short, specific header (≤8 words) summarising the change. Extract from the `Statement`; do not copy verbatim. |
| `Impact` | Rewrite the `Statement` as a concise, actionable migration guide. State: what changed, why it affects the upgrader, and exactly what action to take. Do not copy-paste the raw statement. Do not mention confidence scores. |

### Rule 5 — Do not invent facts
Use only information present in the input rows. If a precise remediation step is not
stated but the migration impact is clear, give the most conservative actionable guidance
supported by the input.

---

## Section assignment rules

Place each consolidated item in **exactly one section** — the single most severe or
applicable one.

**Precedence order (highest wins):**
Breaking Changes → Mandatory Migrations — Security & CVE Fixes →
Mandatory Migrations — Major Component Upgrades →
Mandatory Migrations — Security Configuration →
Behavioral Changes → Deprecations → Notable New Capabilities

**Specific placement rules:**
- Security fixes that require user action → **Security & CVE Fixes** even if they also
  involve a dependency upgrade.
- Major platform/API/namespace/component version migrations → **Major Component Upgrades**
  unless the migration will cause compile or runtime failures → then **Breaking Changes**.
- New features → **Notable New Capabilities** only if adoption is optional. If adoption is
  required for compatibility, place in the appropriate mandatory or breaking section.

---

## Table quality rules

- Keep `Title` short and specific — name the exact component, API, subsystem, or namespace.
- Keep `Impact` concise but actionable: what changed, why it matters, what the user must do.
- Preserve technical names exactly as they appear in the source (class names, property keys,
  Maven coordinates, subsystem names, CLI fragments, version numbers).
- Do not mention confidence scores anywhere in the output.
- Do not include source URLs anywhere in the output.
- Within each section, order rows by likely migration severity and breadth of impact,
  highest first.

---

## Summary aggregation rules

Count items for the **Summary by Priority** table as follows:

| Priority level | What to count |
|---|---|
| 🔴 **Breaking** | Total rows under **Breaking Changes** |
| 🟠 **Mandatory** | Combined total of all three **Mandatory Migrations** sections |
| 🟡 **Behavioral / Deprecation** | Combined total of **Behavioral Changes** + **Deprecations** |
| 🔵 **New Capabilities** | Total rows under **Notable New Capabilities** |

Always include all four priority levels in the table, even when the count is `0`.

---

## Most Critical Items rules

Provide **3 to 5 bullets** in the `🚨 Most Critical Items for Migration` section.

- Prefer items from **Breaking Changes** and **Mandatory Migrations**.
- If fewer than 3 such items exist, include the next most consequential **Behavioral Changes**.
- Each bullet: 1–2 sentences. Summarise the concrete migration risk and the required action.
- Do **not** merely repeat section titles. Surface the specific risk.

---

## Example output shape

```markdown
## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-17842 | Removal of `sun.jdk` implicit module dependency | The `sun.jdk` module is no longer implicitly added to deployments. Applications that relied on internal JDK APIs via this module will fail to deploy. Audit your code for `sun.*` imports and replace with supported JDK or third-party alternatives before upgrading. |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18102 | Upgrade `io.netty` to 4.1.94 (CVE-2023-34462) | Netty 4.1.94 patches a denial-of-service vulnerability in HTTP/2 header handling. Update your `io.netty:netty-all` BOM entry or direct dependency to `4.1.94.Final`. Run your HTTP/2 integration tests to confirm no regressions. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 1 | Must fix before migrating. |
| 🟠 **Mandatory** | 1 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 0 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 0 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration
- The removal of the implicit `sun.jdk` module will break any deployment using internal JDK APIs; replace all `sun.*` usages before upgrade.
- Netty must be updated to 4.1.94.Final to patch CVE-2023-34462; failing to do so exposes HTTP/2 endpoints to denial-of-service attacks.
```

---

## Pipeline context

This skill produces the **filtered Markdown artifact** (`changes_filtered.md`) that is
consumed by the entity extraction step (Phase 6). The output of this skill must be a clean,
self-contained Markdown document — not JSON, not a summary, not a conversation reply.

If the user is running the full Migration Oracle pipeline, the output of this skill goes
directly into the second LLM call (changelog-migration-extractor skill or equivalent) as
`{changes_text}`.
