"""Layer 0 — Schema Audit: automated lint tests for MCP tool and prompt schemas.

Run with:
    uv run pytest tests/mcp/test_schema_lint.py -v
"""

from __future__ import annotations

import re

import pytest

import migration_oracle.mcp.server  # noqa: F401 — registers all tools/prompts
from migration_oracle.mcp.instance import mcp

# ---------------------------------------------------------------------------
# Imperative verbs that are acceptable as the first word of a description.
# Keep this list inclusive of everything actually used in the codebase plus
# common English imperatives. The test fails only when a description starts
# with a word that is NOT on this list.
# ---------------------------------------------------------------------------
ALLOWED_FIRST_WORDS: frozenset[str] = frozenset(
    {
        # Core imperatives used in the current descriptions
        "return",
        "create",
        "submit",
        "get",
        "list",
        "search",
        "build",
        "resolve",
        "execute",
        "install",
        "find",
        "analyze",
        "close",
        "mark",
        "update",
        "show",
        "fetch",
        "read",
        "vote",
        "approve",
        "verify",
        "trace",
        # Currently used (non-ideal but documented in EVALUATION.md as present)
        "produce",
        "set",
        "query",
        "copy",
        "record",
        "increment",
        # Generic extras
        "add",
        "delete",
        "remove",
        "check",
        "compute",
        "calculate",
        "load",
        "save",
        "run",
        "scan",
        "push",
        "pull",
        "validate",
        "emit",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_word(description: str) -> str:
    """Return the lower-cased first word of a description string."""
    first_line = description.strip().splitlines()[0].strip()
    match = re.match(r"[A-Za-z]+", first_line)
    return match.group(0).lower() if match else ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_tools_have_descriptions():
    """Every registered tool must have a non-trivial description (>= 20 chars)."""
    tools = await mcp.list_tools()
    assert tools, "No tools registered — did the server module import correctly?"
    missing = [t.name for t in tools if not t.description or len(t.description) < 20]
    assert not missing, f"Tools with missing/short descriptions: {missing}"


@pytest.mark.asyncio
async def test_tool_count():
    """Exactly 22 tools must be registered."""
    tools = await mcp.list_tools()
    assert len(tools) == 22, (
        f"Expected 22 tools, got {len(tools)}: {[t.name for t in tools]}"
    )


@pytest.mark.asyncio
async def test_prompt_count():
    """Exactly 3 prompts must be registered."""
    prompts = await mcp.list_prompts()
    assert len(prompts) == 3, (
        f"Expected 3 prompts, got {len(prompts)}: {[p.name for p in prompts]}"
    )


@pytest.mark.asyncio
async def test_start_migration_prompt_has_required_args():
    """The start_migration prompt must declare the 4 required arguments."""
    prompts = await mcp.list_prompts()
    prompt = next((p for p in prompts if p.name == "start_migration"), None)
    assert prompt is not None, "Prompt 'start_migration' not found"
    arg_names = {a.name for a in (prompt.arguments or [])}
    required = {"framework", "current_version", "target_version", "project_id"}
    assert required.issubset(arg_names), (
        f"start_migration prompt is missing arguments: {required - arg_names}"
    )


@pytest.mark.asyncio
async def test_all_tool_descriptions_start_with_imperative_verb():
    """Every tool description must begin with a recognised imperative verb.

    The first word (case-insensitive) must be in ALLOWED_FIRST_WORDS.
    This catches descriptions that start with noun phrases, participles, or
    vague openers like 'This tool ...' that harm LLM tool-selection accuracy.
    """
    tools = await mcp.list_tools()
    violations: list[tuple[str, str]] = []
    for tool in tools:
        if not tool.description:
            continue  # caught by test_all_tools_have_descriptions
        first = _first_word(tool.description)
        if first not in ALLOWED_FIRST_WORDS:
            violations.append((tool.name, first))

    if violations:
        lines = "\n".join(
            f"  {name!r}: first word is {word!r} (not in ALLOWED_FIRST_WORDS)"
            for name, word in violations
        )
        pytest.fail(
            f"The following tools have non-imperative description openers:\n{lines}\n\n"
            "Either fix the docstring to start with an imperative verb, or add the "
            "word to ALLOWED_FIRST_WORDS in this test."
        )
