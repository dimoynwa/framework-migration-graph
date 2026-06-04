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

FILTER_PROMPT = """You are an expert software migration analyst.

Analyze the raw framework change records below and produce a severity-ordered migration document.

Rules:
1. Filter noise — remove tests, docs-only, CI/CD, quickstarts, examples, and internal refactors with no user-facing effect.
2. Consolidate related rows into one row with comma-separated JIRA keys and unified impact.
3. Deduplicate — never repeat the same migration across sections.
4. Transform columns from | Type | Confidence | Source | Statement | to | # | JIRA | Title | Impact |.
5. Do not invent facts — only use information from the input.

Required sections (omit empty sections):
## 🔴 Breaking Changes
## 🟠 Mandatory Migrations — Security & CVE Fixes
## 🟠 Mandatory Migrations — Major Component Upgrades
## 🟠 Mandatory Migrations — Security Configuration
## 🟡 Behavioral Changes
## 🟡 Deprecations
## 🔵 Notable New Capabilities

End with:
## Summary by Priority
## 🚨 Most Critical Items for Migration

Return only the structured Markdown document.

{changes_text_markdown_table}
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
