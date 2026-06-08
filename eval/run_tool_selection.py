"""Layer 2 — Tool Selection Eval.

For each of the 21 EVALUATION.md scenarios, send the scenario text plus the full
tool list to the model and assert which tool is selected.  No tool is actually
executed; `tool_choice={"type":"any"}` forces the model to pick one.

Usage
-----
    # Basic run
    uv run python eval/run_tool_selection.py

    # Override model
    uv run python eval/run_tool_selection.py --model claude-opus-4-8

    # CI mode: exits non-zero when accuracy < 95 %
    uv run python eval/run_tool_selection.py --ci

Output
------
Results are written to eval/results/tool_selection_latest.json in addition to
the printed summary table.

Requirements
------------
    ANTHROPIC_API_KEY  must be set in the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Locate the project root and set up the Python path so we can import the
# migration_oracle package regardless of the cwd from which this script is run.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Set env vars required by config before importing server
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")

import migration_oracle.mcp.server  # noqa: F401 — side-effect: registers all tools
from migration_oracle.mcp.instance import mcp  # noqa: E402

# ---------------------------------------------------------------------------
# Scenarios — 21 entries, one per EVALUATION.md row
# ---------------------------------------------------------------------------

SCENARIOS: list[dict[str, str]] = [
    {
        "scenario": "I need to find migration rules for going from Spring Boot 2.7 to 3.2",
        "expected": "analyze_upgrade_path",
    },
    {
        "scenario": "Show me what replaced WebSecurityConfigurerAdapter",
        "expected": "resolve_deprecation",
    },
    {
        "scenario": "Trace the full deprecation chain for WebMvcConfigurerAdapter",
        "expected": "entity_evolution",
    },
    {
        "scenario": "Search for guidance on actuator endpoint security in Boot 3",
        "expected": "search_migration_knowledge",
    },
    {
        "scenario": "Find an OpenRewrite recipe for the Spring Security migration",
        "expected": "search_openrewrite_recipes",
    },
    {
        "scenario": "Start a migration session for project payments-service from 2.7 to 3.2",
        "expected": "create_migration_context",
    },
    {
        "scenario": "What steps are still pending for context abc-123?",
        "expected": "get_pending_steps",
    },
    {
        "scenario": "Mark step step-42 as completed",
        "expected": "update_step_status",
    },
    {
        "scenario": "What api-surface steps are critical for context abc-123?",
        "expected": "get_steps_for_scope_tier",
    },
    {
        "scenario": "Close the migration context, we skipped the test steps",
        "expected": "close_migration_context",
    },
    {
        "scenario": "Build me a migration plan split into auto and manual tracks",
        "expected": "build_recipe_plan",
    },
    {
        "scenario": "What does the graph schema look like?",
        "expected": "get_graph_schema",
    },
    {
        "scenario": "Run this Cypher: MATCH (r:MigrationRule) RETURN r LIMIT 5",
        "expected": "execute_custom_cypher",
    },
    {
        "scenario": "Submit an insight: SecurityFilterChain registration changed in 3.0",
        "expected": "submit_migration_insight",
    },
    {
        "scenario": "Show me community insights for Spring Boot 3.x",
        "expected": "get_community_insights",
    },
    {
        "scenario": "Upvote insight insight-99",
        "expected": "vote_insight",
    },
    {
        "scenario": "Approve insight insight-99 as verified",
        "expected": "verify_insight",
    },
    {
        "scenario": "Resolve the com.paysafe dependency for payments-core",
        "expected": "resolve_paysafe_dependency_by_service_name",
    },
    {
        "scenario": "List all pipeline artifacts we have stored",
        "expected": "list_pipeline_runs",
    },
    {
        "scenario": "Read the filtered migration document for Spring Boot 3.2",
        "expected": "get_artifact_content",
    },
    {
        "scenario": "Install the migration skill for Claude Code",
        "expected": "install_migration_skill",
    },
]

assert len(SCENARIOS) == 21, f"Expected 21 scenarios, found {len(SCENARIOS)}"

# ---------------------------------------------------------------------------
# Convert MCP tool schema to Anthropic tool_use format
# ---------------------------------------------------------------------------


async def _load_anthropic_tools() -> list[dict]:
    """Load tools from the MCP instance and convert to Anthropic API format."""
    mcp_tools = await mcp.list_tools()
    tools = []
    for t in mcp_tools:
        input_schema = getattr(t, "inputSchema", None) or getattr(
            t, "input_schema", None
        )
        if input_schema is None:
            input_schema = {"type": "object", "properties": {}}
        if hasattr(input_schema, "model_dump"):
            input_schema = input_schema.model_dump()
        tools.append(
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": input_schema,
            }
        )
    return tools


# ---------------------------------------------------------------------------
# Single probe
# ---------------------------------------------------------------------------


def _probe(
    client: anthropic.Anthropic,
    scenario: str,
    tools: list[dict],
    model: str,
) -> str:
    """Return the name of the tool the model selects for the scenario."""
    response = client.messages.create(
        model=model,
        max_tokens=256,
        tools=tools,  # type: ignore[arg-type]
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": scenario}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.name
    return ""


# ---------------------------------------------------------------------------
# Main eval loop
# ---------------------------------------------------------------------------


async def run_eval(model: str, ci: bool) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    tools = await _load_anthropic_tools()

    results: list[dict] = []
    correct = 0

    col_w = (52, 42, 42, 6)
    sep = "-+-".join("-" * w for w in col_w)
    print()
    print(
        f"{'Scenario':<{col_w[0]}} | {'Expected':<{col_w[1]}} | {'Actual':<{col_w[2]}} | Pass"
    )
    print(sep)

    for i, entry in enumerate(SCENARIOS, start=1):
        scenario = entry["scenario"]
        expected = entry["expected"]

        actual = _probe(client, scenario, tools, model)
        passed = actual == expected
        if passed:
            correct += 1

        mark = "PASS" if passed else "FAIL"
        short = scenario if len(scenario) <= col_w[0] else scenario[: col_w[0] - 3] + "..."
        print(
            f"{short:<{col_w[0]}} | {expected:<{col_w[1]}} | {actual:<{col_w[2]}} | {mark}"
        )

        results.append(
            {
                "index": i,
                "scenario": scenario,
                "expected": expected,
                "actual": actual,
                "pass": passed,
            }
        )

        if i < len(SCENARIOS):
            time.sleep(0.3)

    print(sep)
    accuracy_pct = correct / len(SCENARIOS) * 100
    print(f"\nAccuracy: {correct}/{len(SCENARIOS)} correct ({accuracy_pct:.1f}%)")

    output_dir = _SCRIPT_DIR / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "tool_selection_latest.json"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "total": len(SCENARIOS),
        "correct": correct,
        "accuracy_pct": round(accuracy_pct, 2),
        "results": results,
    }
    output_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults written to {output_path}")

    if ci and accuracy_pct < 95.0:
        print(
            f"\nCI check FAILED: accuracy {accuracy_pct:.1f}% is below the 95% threshold.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Layer 2 tool-selection eval for PaysafeMigrationOracle MCP server."
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Anthropic model ID to use (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Exit non-zero when accuracy < 95%% (for CI pipelines)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(run_eval(model=args.model, ci=args.ci))
