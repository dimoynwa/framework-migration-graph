"""Filter-and-group LLM call: raw Markdown → filtered Markdown."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from migration_oracle.pipeline._cache import CacheFlags
from migration_oracle.pipeline.research.markdown import FilterResearch
from migration_oracle.pipeline.triage.markdown import (
    FILTER_TABLE_HEADER,
    split_filter_groups,
)
from migration_oracle.pipeline.triage.settings import load_settings
from migration_oracle.pipeline._llm import (
    LLMInvocationError,
    get_llm,
    invoke_with_retry,
    strip_markdown_fences,
    strip_preamble,
)

FILTER_PROMPT = """
You are an expert software migration analyst specializing in analyzing raw changelogs, release notes, and issue tracker exports for software platforms and frameworks.

Your task is to analyze a large markdown table of raw change records, filter out non-essential noise, combine related changes, rewrite the descriptions for clarity, and output a beautifully formatted Markdown document organized by migration impact.

⚠️ IMPORTANT RULES:
- **Filter the Noise:** Strictly remove any rows that represent tests, documentation updates, CI/CD scripts, quickstart modifications, examples, refactors with no user-facing migration effect, or internal build changes. ONLY keep changes that force or strongly require an upgrading user to modify their code, configuration, dependencies, runtime, deployment process, or environment.
- **Pre-classified rows:** When the table has `Category` and `Impact score` columns, a fast classifier has already labelled each row. Use `Category` to choose the output section with this mapping, but override it when the statement clearly contradicts it:
  - `breaking` → 🔴 Breaking Changes
  - `security` → 🟠 Mandatory Migrations — Security & CVE Fixes (or — Security Configuration when the change is to authentication, authorization, or security subsystem settings rather than a vulnerability fix)
  - `dependency_upgrade` → 🟠 Mandatory Migrations — Major Component Upgrades when it is a major version bump, namespace change, or replacement; otherwise 🟡 Behavioral Changes, or drop it when the bump needs no user action
  - `behavior_change` and `config_change` → 🟡 Behavioral Changes (🔴 Breaking Changes when existing applications fail until updated)
  - `deprecation` → 🟡 Deprecations
  - any other category → decide from the statement
  `Impact score` is the classifier's migration-effort estimate from 0 (none) to 3 (high). Use it only to order items within a section. It is not the output `Impact` column. Ignore this rule when the table has no `Category` column.
- **Research appendix:** The document may end with a `## Research` section. Each block in it (`### <Title>` followed by `Row sources: …`) was written by a research step that fetched that row's sources and the official documentation; it is evidence for the input row with the same `Source` URL or the same link in its `Statement`. Research blocks are NOT input rows: never create an item from a block on its own. Use the block to decide the section (a block whose `**Action:**` line is `none`, together with a statement that confirms it, is a strong reason to drop the row), to consolidate rows that research shows are the same change, and to write `Impact` with the exact class, property, coordinate, or version the block cites.
- **Consolidate & Combine:** If multiple rows relate to the same overarching migration (e.g., upgrading multiple related components to Jakarta EE), merge them into a single row. Combine their issue keys in the `JIRA` column, and write a unified impact statement.
- **Deduplicate:** Do not repeat the same migration across sections or rows. If several raw rows describe the same required user action, produce one consolidated item.
- **Migration Focus:** Prefer concrete user-impacting guidance over internal implementation detail. Exclude changes that are merely informative unless they imply a real migration action or behavior change.
- **Data Transformation:** The input table has columns `| Type | Confidence | Source | Statement |`, plus `| Category | Impact score |` when change triage has already classified the rows. You MUST transform this into output tables with the following exact columns: `| # | JIRA | Title | Impact | Sources |`.
  - **`#`**: A simple incrementing row number within each section, starting at 1.
  - **`JIRA`**: Extract the issue-tracker key (e.g., WFLY-17948) from the `Source` URL or from links inside the `Statement`. If there are multiple related issue keys after consolidation, comma-separate them. GitHub issue or pull request numbers are not JIRA keys; they go in `Sources`. If no issue key can be confidently extracted, use `N/A`.
  - **`Title`**: Extract the title from the `Statement` (or summarize it into a short, clear header).
  - **`Impact`**: Rewrite the `Statement` into a concise, migration-focused summary: what changed, which applications are affected, and what the user must do. Name exact classes, properties, coordinates, and versions only when the statement or the row's research block states them; otherwise describe the action at the level the sources support. Do not just copy-paste the raw description.
  - **`Sources`**: Comma-separated URLs that identify this specific change, for every raw row consolidated into this item. Take them in this order: (1) issue, pull request, commit, or JIRA links inside the `Statement` (for example `[#43559](https://github.com/spring-projects/spring-boot/issues/43559)` → `https://github.com/spring-projects/spring-boot/issues/43559`); (2) the row's `Source` URL only when the Statement has no such link. Do not list a release-notes page, release tag, or changelog file when a specific link exists. Write bare URLs without Markdown link syntax. Use `N/A` when no URL is available.
- **Do Not Invent Facts:** Use only information supported by the provided records and their research blocks. If a precise remediation step is not stated but the migration impact is clear, give the most conservative actionable guidance supported by the input.

---
### DOCUMENT STRUCTURE & SECTIONING

You MUST categorize the filtered and consolidated records into the following specific sections. Under each section heading, output a Markdown table with the exact columns: `| # | JIRA | Title | Impact | Sources |`.

If a section has no applicable records, omit that section entirely.

**Required Sections (in order):**

## 🔴 Breaking Changes
*(Items that will cause failures or compilation errors if not addressed before upgrade)*

## 🟠 Mandatory Migrations — Security & CVE Fixes
*(Security patches requiring configuration or dependency updates)*

## 🟠 Mandatory Migrations — Major Component Upgrades
*(Major version bumps, namespace changes like javax to jakarta, or API removals)*

## 🟠 Mandatory Migrations — Security Configuration
*(Changes to security subsystems, authentication realms, or authorization)*

## 🟡 Behavioral Changes
*(Changes in default values, lifecycle behavior, or underlying logic that might alter app behavior silently)*

## 🟡 Deprecations
*(APIs or features marked for removal in future versions; actions to migrate away)*

## 🔵 Notable New Capabilities
*(Optional but highly recommended new features that require configuration to activate)*

### Section Assignment Rules
- Place each consolidated item in exactly one section: the single most severe/applicable section.
- If an item could fit multiple sections, use this precedence order: **Breaking Changes** → **Mandatory Migrations — Security & CVE Fixes** → **Mandatory Migrations — Major Component Upgrades** → **Mandatory Migrations — Security Configuration** → **Behavioral Changes** → **Deprecations** → **Notable New Capabilities**.
- Security fixes that require action belong under **Security & CVE Fixes** even if they also involve a dependency upgrade.
- Major platform, API, namespace, or component version migrations belong under **Major Component Upgrades** unless they are more accurately a breaking failure scenario.
- New features belong under **Notable New Capabilities** only if they are optional to adopt; if adoption is required for compatibility, place them in the appropriate mandatory or breaking section instead.

### Table Content Quality Rules
- Keep `Title` short and specific.
- Keep `Impact` concise but actionable: what changed, why it matters, and what the user should do.
- Preserve technical accuracy and name exact affected components, APIs, subsystems, namespaces, versions, or config areas whenever the source provides them.
- Do not mention confidence scores in the output.
- Fill the `Sources` column as defined above for every item. Do not drop the specific issue, pull request, commit, or JIRA links of consolidated rows.
- Within each section, order items by likely migration severity and breadth of impact, highest first.

---
### SUMMARY & CRITICAL ITEMS (Must be at the bottom)

After listing the sections above, you MUST generate the following two sections:

## Summary by Priority
Provide a table summarizing the total count of items in each main priority level:
| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | [X] | Must fix before migrating. |
| 🟠 **Mandatory** | [X] | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | [X] | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | [X] | Optional but recommended to leverage. |

Count aggregation rules:
- **Breaking** = total items under **Breaking Changes**.
- **Mandatory** = combined total of all three **Mandatory Migrations** sections.
- **Behavioral / Deprecation** = combined total of **Behavioral Changes** and **Deprecations**.
- **New Capabilities** = total items under **Notable New Capabilities**.
- If a priority level has zero items, still include it in the summary table with count `0`.

## 🚨 Most Critical Items for Migration
Provide a bulleted list of the 3 to 5 most impactful, high-risk, or widespread changes that every upgrading user absolutely must know about. Keep each bullet to 1-2 sentences.

Selection rules:
- Prefer items from **Breaking Changes** and **Mandatory Migrations**.
- If fewer than 3 such items exist, include the next most consequential **Behavioral Changes**.
- Do not merely repeat section titles; summarize the concrete migration risk/action.

---
{partial_note}### DOCUMENT TO ANALYZE

{changes_text_markdown_table}

---
### REQUIRED OUTPUT

Return ONLY the complete, structured Markdown document. Do not include any conversational filler, JSON, code fences, or introductory/concluding text outside of the requested Markdown structure.
"""


@dataclass(frozen=True)
class FilterResult:
    filtered_md: str
    artifact_path: Path


def emit_stale_warnings(flags: CacheFlags) -> None:
    if flags.stale_filtered_warning:
        print(
            "Warning: raw Markdown was re-extracted but cached filtered Markdown will "
            "be reused. Pass --force-llm to regenerate LLM artifacts.",
            file=sys.stderr,
        )
    if flags.stale_json_warning:
        print(
            "Warning: raw Markdown was re-extracted but cached entities JSON will be "
            "reused. Pass --force-llm to regenerate LLM artifacts.",
            file=sys.stderr,
        )


def filter_document(raw_md: str, research: FilterResearch | None = None) -> str:
    """The full filter input: kept-row table plus the research appendix.

    This is what the cache sidecar hashes. Without research it is ``raw_md``,
    so sidecars written before research existed stay valid.
    """
    if research is None or research.empty:
        return raw_md
    return research.document(raw_md)


def run_filter(
    raw_md: str,
    *,
    output_path: Path,
    flags: CacheFlags,
    research: FilterResearch | None = None,
) -> FilterResult:
    """Write the consolidated migration document from the kept rows.

    ``research`` carries the per-row research blocks; each LLM call receives the
    blocks of the rows in its chunk.
    """
    emit_stale_warnings(flags)
    document = filter_document(raw_md, research)

    if flags.skip_filter_llm and output_path.exists():
        _write_input_digest(document, output_path)
        return FilterResult(filtered_md=output_path.read_text(encoding="utf-8"), artifact_path=output_path)

    chunks = _filter_chunks(raw_md, document)
    with_research = [
        research.document(chunk) if research is not None and not research.empty else chunk
        for chunk in chunks
    ]
    if len(with_research) == 1:
        pieces = [_invoke_filter(with_research[0])]
    else:
        pieces = [_invoke_filter(chunk, partial=True) for chunk in with_research]
    filtered = "\n\n".join(pieces)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(filtered + "\n", encoding="utf-8")
    _write_input_digest(document, output_path)
    return FilterResult(filtered_md=filtered, artifact_path=output_path)


def filter_input_digest_path(output_path: Path) -> Path:
    """Sidecar holding the sha256 of the filter input that produced ``output_path``."""
    return output_path.with_name(output_path.name + ".input.sha256")


def filter_input_changed(filter_md: str, output_path: Path) -> bool:
    """Whether the cached filtered Markdown was built from a different filter input.

    Without a sidecar the artifact predates triage, so it was built from an
    untriaged table: it is stale only when the current input is triaged.
    """
    if not output_path.exists():
        return False
    digest_path = filter_input_digest_path(output_path)
    if digest_path.exists():
        return digest_path.read_text(encoding="utf-8").strip() != _digest(filter_md)
    return FILTER_TABLE_HEADER in filter_md


def refresh_flags_for_filter_input(
    flags: CacheFlags, filter_md: str, output_path: Path
) -> CacheFlags:
    """Re-run both LLM steps when the filter input changed.

    ``filter_md`` is the full input (:func:`filter_document`): the kept rows and
    their research appendix, so a changed dossier also regenerates the document.

    Triage decisions can change without re-extraction (``--force-triage``,
    ``--retriage-from-cache``, threshold or model changes, enabling triage on an
    old raw file). Cached filtered Markdown and entities JSON built from the
    previous row set would otherwise be reused silently.
    """
    if not (flags.skip_filter_llm or flags.skip_entity_llm):
        return flags
    if not filter_input_changed(filter_md, output_path):
        return flags
    print(
        "Filter input changed since the cached filtered Markdown was built "
        f"({output_path}); re-running the filter and entity LLM steps.",
        file=sys.stderr,
    )
    return replace(
        flags,
        skip_filter_llm=False,
        skip_entity_llm=False,
        stale_filtered_warning=False,
        stale_json_warning=False,
    )


def _digest(filter_md: str) -> str:
    return hashlib.sha256(filter_md.encode("utf-8")).hexdigest()


def _write_input_digest(filter_md: str, output_path: Path) -> None:
    filter_input_digest_path(output_path).write_text(
        _digest(filter_md) + "\n", encoding="utf-8"
    )


PARTIAL_NOTE = """### PARTIAL INPUT

This document is one part of a larger change set that was split by category. Output only the change sections for these rows. Do NOT output `## Summary by Priority` or `## 🚨 Most Critical Items for Migration`; they would be wrong for a partial input.

---
"""


def _filter_chunks(raw_md: str, document: str | None = None) -> list[str]:
    """One chunk, or one chunk per triage category group when the kept table is large.

    Each chunk keeps the document preamble (framework and range lines) so the
    model knows which framework and versions it is filtering.
    """
    if FILTER_TABLE_HEADER not in raw_md:
        return [raw_md]
    size_of = document if document is not None else raw_md
    if _estimate_tokens(size_of) <= load_settings().filter_max_input_tokens:
        return [raw_md]
    groups = split_filter_groups(raw_md)
    if len(groups) <= 1:
        return groups
    preamble = _preamble(raw_md)
    return [preamble + group for group in groups]


def _preamble(raw_md: str) -> str:
    lines: list[str] = []
    for line in raw_md.splitlines(keepends=True):
        if line.startswith("|") or line.startswith("## "):
            break
        lines.append(line)
    return "".join(lines)


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def render_filter_prompt(table: str, *, partial: bool = False) -> str:
    """Plain substitution: statements may contain braces, so no ``str.format``."""
    return FILTER_PROMPT.replace(
        "{partial_note}", PARTIAL_NOTE if partial else ""
    ).replace("{changes_text_markdown_table}", table)


def _invoke_filter(table: str, *, partial: bool = False) -> str:
    prompt = render_filter_prompt(table, partial=partial)
    try:
        response = invoke_with_retry(get_llm(), prompt)
    except LLMInvocationError as exc:
        print(f"Filter LLM call failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    filtered = strip_preamble(strip_markdown_fences(response))
    if not filtered.strip():
        print("Filter LLM returned empty output.", file=sys.stderr)
        raise SystemExit(1)
    return filtered
