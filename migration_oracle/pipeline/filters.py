"""Filter-and-group LLM call: raw Markdown → filtered Markdown."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from migration_oracle.pipeline._cache import CacheFlags
from migration_oracle.pipeline._llm import (
    LLMInvocationError,
    get_llm,
    invoke_with_retry,
    strip_markdown_fences,
    strip_preamble,
)

FILTER_PROMPT = """
Developer: Developer: You are an expert software migration analyst specializing in analyzing raw changelogs, release notes, and issue tracker exports for software platforms and frameworks.

Your task is to analyze a large markdown table of raw change records, filter out non-essential noise, combine related changes, rewrite the descriptions for clarity, and output a beautifully formatted Markdown document organized by migration impact.

⚠️ IMPORTANT RULES:
- **Filter the Noise:** Strictly remove any rows that represent tests, documentation updates, CI/CD scripts, quickstart modifications, examples, refactors with no user-facing migration effect, or internal build changes. ONLY keep changes that force or strongly require an upgrading user to modify their code, configuration, dependencies, runtime, deployment process, or environment.
- **Consolidate & Combine:** If multiple rows relate to the same overarching migration (e.g., upgrading multiple related components to Jakarta EE), merge them into a single row. Combine their issue keys in the `JIRA` column, and write a unified impact statement.
- **Deduplicate:** Do not repeat the same migration across sections or rows. If several raw rows describe the same required user action, produce one consolidated item.
- **Migration Focus:** Prefer concrete user-impacting guidance over internal implementation detail. Exclude changes that are merely informative unless they imply a real migration action or behavior change.
- **Data Transformation:** The input table has columns `| Type | Confidence | Source | Statement |`. You MUST transform this into output tables with the following exact columns: `| # | JIRA | Title | Impact |`.
  - **`#`**: A simple incrementing row number within each section, starting at 1.
  - **`JIRA`**: Extract the issue key (e.g., WFLY-17948) from the `Source` URL. If there are multiple related issue keys after consolidation, comma-separate them. If no issue key can be confidently extracted, use `N/A`.
  - **`Title`**: Extract the title from the `Statement` (or summarize it into a short, clear header).
  - **`Impact`**: Rewrite the `Statement` into a concise, actionable, migration-focused guide. It should clearly state what changed, why it impacts the user, and the exact action the user must take. Do not just copy-paste the raw description.
- **Do Not Invent Facts:** Use only information supported by the provided records. If a precise remediation step is not stated but the migration impact is clear, give the most conservative actionable guidance supported by the input.

---
### DOCUMENT STRUCTURE & SECTIONING

You MUST categorize the filtered and consolidated records into the following specific sections. Under each section heading, output a Markdown table with the exact columns: `| # | JIRA | Title | Impact |`.

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
- Do not include the original `Source` URLs in the output.
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
### DOCUMENT TO ANALYZE

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


def run_filter(
    raw_md: str,
    *,
    output_path: Path,
    flags: CacheFlags,
) -> FilterResult:
    emit_stale_warnings(flags)

    if flags.skip_filter_llm and output_path.exists():
        return FilterResult(filtered_md=output_path.read_text(encoding="utf-8"), artifact_path=output_path)

    prompt = FILTER_PROMPT.format(changes_text_markdown_table=raw_md)
    try:
        response = invoke_with_retry(get_llm(), prompt)
    except LLMInvocationError as exc:
        print(f"Filter LLM call failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    filtered = strip_preamble(strip_markdown_fences(response))
    if not filtered.strip():
        print("Filter LLM returned empty output.", file=sys.stderr)
        raise SystemExit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(filtered + "\n", encoding="utf-8")
    return FilterResult(filtered_md=filtered, artifact_path=output_path)
