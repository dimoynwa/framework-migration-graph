# PaysafeMigrationOracle — MCP Evaluation Guide

MCP server evaluation is not the same as API testing. The server's correctness (unit and
integration tests) is necessary but not sufficient: the other half of the question is
whether an LLM agent, given the server's tool list, calls the right tools in the right
order with the right parameters. This guide covers both halves.

---

## The two halves of MCP evaluation

```
┌────────────────────────────────────────────────────────────────────────┐
│  Half 1 — Server correctness                                           │
│  Does the tool DO what its description claims?                         │
│  Tools: pytest, unit/integration tests, contract tests                 │
├────────────────────────────────────────────────────────────────────────┤
│  Half 2 — Agent correctness                                            │
│  Does the LLM SELECT the right tool, with the right parameters,        │
│  in the right order, given only the tool descriptions?                 │
│  Tools: golden trajectories, LLM-as-judge, scenario probes            │
└────────────────────────────────────────────────────────────────────────┘
```

Most projects stop at Half 1. This guide covers both.

---

## Layer 0 — Schema Audit (offline, no LLM, no running server)

Before running any test, audit the tool schema statically. This is the cheapest
check and catches the largest class of agent failures: bad or missing descriptions.

### Checklist

Run this after every change to a `@mcp.tool()` function:

```
[ ] Every tool function has a docstring (non-empty first line)
[ ] Every tool description is ≤ 200 words
[ ] Every parameter with a closed set of valid values enumerates them
    (scope: api-surface|runtime|config|build|test)
    (outcome: completed|skipped|failed)
    (artifact_type: raw_md|filtered_md|entities_json)
[ ] Side effects (writes) are flagged as such in the description
[ ] Read-only tools state they are read-only
[ ] Idempotent tools say "idempotent"
[ ] No-op parameters (accepted but not applied) are disclosed
[ ] Tools that require env vars name them explicitly
[ ] Tools that may return status='not_found' or status='blocked' say so
[ ] The first sentence is imperative: "Return X", "Create or resume Y", "Submit Z"
```

### Automated schema lint

Inspect the tool list programmatically. Add this as a CI check:

```python
# tests/mcp/test_schema_lint.py
import pytest
from migration_oracle.mcp.instance import mcp

@pytest.mark.asyncio
async def test_all_tools_have_descriptions():
    tools = await mcp.list_tools()
    missing = [t.name for t in tools if not t.description or len(t.description) < 20]
    assert not missing, f"Tools with missing/empty descriptions: {missing}"

@pytest.mark.asyncio
async def test_prompt_count():
    prompts = await mcp.list_prompts()
    assert len(prompts) == 3  # start_migration, resume_migration, migration_workflow_prompt

@pytest.mark.asyncio
async def test_start_migration_prompt_has_required_args():
    prompts = await mcp.list_prompts()
    p = next(p for p in prompts if p.name == "start_migration")
    arg_names = {a.name for a in (p.arguments or [])}
    assert {"framework", "current_version", "target_version", "project_id"}.issubset(arg_names)
```

---

## Layer 1 — Contract Tests (unit, no LLM, mocked graph)

Contract tests verify that tool return shapes match what is documented. The LLM
learns from the description what fields to expect in the response. If the actual
response omits a field or changes a key name, the agent silently misreads results.

### What to assert

For every tool, assert:
- `status` key is present and is one of `ok | not_found | blocked | error | duplicate`
- All documented top-level keys are present (even if empty string / empty list)
- No undocumented keys are introduced without updating the description

### Example contract test pattern

```python
# tests/mcp/test_contracts.py
from unittest.mock import patch
from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

def test_analyze_upgrade_path_contract():
    with patch("migration_oracle.mcp.tools.upgrade.upgrade_queries.analyze_upgrade_path",
               return_value=[]):
        result = analyze_upgrade_path(
            framework="Spring Boot",
            current_version="2.7",
            target_version="3.2",
        )
    assert result["status"] == "ok"
    assert "rules" in result
    assert "lifecycle_alerts" in result
    assert "framework" in result
    assert "from_version" in result
    assert "to_version" in result
    assert isinstance(result["rules"], list)
```

Repeat for all 21 tools. The existing `tests/mcp/` suite already covers many; fill
gaps for `artifacts`, `install`, and `paysafe` tools.

### Error-path contracts

Every tool that can return a non-`ok` status needs an error-path contract test:

```python
def test_execute_custom_cypher_blocked_contract():
    result = execute_custom_cypher(query="CREATE (n) RETURN n")
    assert result["status"] == "blocked"
    assert "blocked_keyword" in result
    assert result["blocked_keyword"]  # non-empty

def test_resolve_deprecation_not_found_contract():
    with patch("...deprecation_queries.resolve_deprecation", return_value=None):
        result = resolve_deprecation(entity_name="does.not.Exist")
    assert result["status"] == "not_found"
    assert "entity_name" in result
```

---

## Layer 2 — Tool Selection Tests (LLM-driven, no running server)

These tests check whether the LLM, given the tool schema alone, selects the correct
tool for a scenario. Run them by sending a prompt + tool list to the model and
asserting which tool it picks — **without executing the tool**.

This is the most direct measurement of description quality.

### Setup

Use the Anthropic API in tool-use mode with `tool_choice={"type": "any"}`:

```python
import anthropic

client = anthropic.Anthropic()

def probe_tool_selection(scenario: str, tools: list[dict]) -> str:
    """Return the name of the tool the model selects for the scenario."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        tools=tools,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": scenario}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.name
    return ""
```

### Scenarios and expected tools

Run each scenario and assert the expected tool is selected:

| Scenario | Expected tool |
|---|---|
| "I need to find migration rules for going from Spring Boot 2.7 to 3.2" | `analyze_upgrade_path` |
| "Show me what replaced WebSecurityConfigurerAdapter" | `resolve_deprecation` |
| "Trace the full deprecation chain for WebMvcConfigurerAdapter" | `entity_evolution` |
| "Search for guidance on actuator endpoint security in Boot 3" | `search_migration_knowledge` |
| "Find an OpenRewrite recipe for the Spring Security migration" | `search_openrewrite_recipes` |
| "Start a migration session for project payments-service from 2.7 to 3.2" | `create_migration_context` |
| "What steps are still pending for context abc-123?" | `get_pending_steps` |
| "Mark step step-42 as completed" | `update_step_status` |
| "What api-surface steps are critical for context abc-123?" | `get_steps_for_scope_tier` |
| "Close the migration context, we skipped the test steps" | `close_migration_context` |
| "Build me a migration plan split into auto and manual tracks" | `build_recipe_plan` |
| "What does the graph schema look like?" | `get_graph_schema` |
| "Run this Cypher: MATCH (r:MigrationRule) RETURN r LIMIT 5" | `execute_custom_cypher` |
| "Submit an insight: SecurityFilterChain registration changed in 3.0" | `submit_migration_insight` |
| "Show me community insights for Spring Boot 3.x" | `get_community_insights` |
| "Upvote insight insight-99" | `vote_insight` |
| "Approve insight insight-99 as verified" | `verify_insight` |
| "Resolve the com.paysafe dependency for payments-core" | `resolve_paysafe_dependency_by_service_name` |
| "List all pipeline artifacts we have stored" | `list_pipeline_runs` |
| "Read the filtered migration document for Spring Boot 3.2" | `get_artifact_content` |
| "Install the migration skill for Claude Code" | `install_migration_skill` |

### Measuring description quality

To quantify the impact of description changes, run the suite twice:

```bash
# Before adding docstrings
python eval/run_tool_selection.py --tag before > results_before.json

# After adding docstrings  
python eval/run_tool_selection.py --tag after > results_after.json

python eval/compare_results.py results_before.json results_after.json
```

Target: **≥ 95% tool selection accuracy** across all 21 scenarios.

---

## Layer 3 — Parameter Correctness Tests (LLM-driven)

Tool selection is necessary but not sufficient. The model also must pass valid
parameter values. This layer checks whether the model constructs correct arguments.

### Closed-set parameter probes

```python
scope_probe = (
    "Using get_steps_for_scope_tier for context 'ctx-1', "
    "show me critical api-surface steps."
)
# Assert: scope == "api-surface", severity_threshold in {"high", "critical"}

outcome_probe = (
    "Mark step step-42 in context ctx-1 as done."
)
# Assert: outcome == "completed"  (not "done", "finished", "ok")

artifact_probe = (
    "Get the filtered migration document for Spring Boot 3.2 from Spring Boot 2.7."
)
# Assert: artifact_type == "filtered_md"  (not "filtered", "filtered_markdown")
```

### Hallucination probes

These check that the model does not invent parameter values:

```python
cypher_probe = (
    "Run a Cypher query to count all MigrationRule nodes."
)
# Assert: query contains "MATCH" and "RETURN", does NOT contain "CREATE/MERGE/SET"

delta_probe = (
    "Downvote insight insight-55."
)
# Assert: delta == -1  (not 0, not a string)
```

---

## Layer 4 — Trajectory Evaluation (end-to-end, full agent)

Trajectory evaluation tests the full four-loop harness as an agent would run it.
Unlike unit tests, it evaluates the **sequence** of tool calls, not individual calls.

A wrong tool in step 3 may not fail immediately — it may silently produce wrong data
that causes a failure three steps later. Trajectory evaluation catches this.

### Golden trajectories

Record correct tool call sequences for known scenarios. Store as JSON:

```json
{
  "scenario": "Start a fresh Spring Boot 2.7 → 3.2 migration for payments-service",
  "expected_trajectory": [
    {"tool": "create_migration_context", "required_params": ["project_id", "from_version", "to_version", "framework"]},
    {"tool": "get_steps_for_scope_tier", "required_params": ["context_id", "scope"], "scope_must_be": "api-surface"},
    {"tool": "analyze_upgrade_path", "required_params": ["framework", "current_version", "target_version"]},
    {"tool": "get_pending_steps", "required_params": ["context_id"]},
    {"tool": "update_step_status", "required_params": ["context_id", "step_id", "outcome"]},
    {"tool": "close_migration_context", "required_params": ["context_id", "final_status"]}
  ]
}
```

A trajectory passes when:
1. All required tool calls appear in order (subsequence match, not exact match).
2. No wrong tools appear between required calls.
3. `context_id` from `create_migration_context` is threaded through all subsequent calls.

### Resumption trajectory

```json
{
  "scenario": "Resume migration context ctx-abc that was started last session",
  "expected_trajectory": [
    {"tool": "create_migration_context", "must_return": {"created": false}},
    {"tool": "get_pending_steps"},
    {"tool": "update_step_status"}
  ],
  "must_NOT_appear": ["create_migration_context called twice with same triple"]
}
```

### Running trajectory evaluations

Use Claude Code itself against a real (or seeded test) Memgraph instance:

```bash
# Start a seeded test graph
docker compose up -d memgraph-test

# Run the trajectory probe
uv run python eval/run_trajectory.py \
  --scenario "Spring Boot 2.7 → 3.2" \
  --project-id eval-project-001 \
  --model claude-sonnet-4-6 \
  --golden eval/golden_trajectories/spring_boot_2_7_to_3_2.json
```

### LLM-as-judge

For scenarios too complex for rule-based trajectory checking, use a second LLM to
evaluate whether the agent's trajectory was correct:

```
Judge prompt:
"The agent was asked to: [scenario].
It made these tool calls in this order: [actual_trajectory].
The correct tool call order is: [golden_trajectory].
Score the agent's trajectory 0–10 on:
- Correct tool selection (3 pts)
- Correct parameter values (3 pts)  
- Correct sequencing (2 pts)
- Efficient (no redundant calls) (2 pts)
Return JSON: {score: N, issues: [...]}"
```

---

## Layer 5 — Regression Guard

Protect against description drift — tool behavior changes that are not reflected
in descriptions, or description changes that break previously-correct tool selection.

### After any tool logic change

1. Re-run the Layer 1 contract tests. If a return key was added or removed, update
   the description to match.
2. Re-run the Layer 2 tool selection suite. If accuracy drops below 95%, the
   description needs updating.

### After any description change

1. Re-run the Layer 2 tool selection suite. Confirm accuracy stays ≥ 95%.
2. Re-run the Layer 3 parameter probes for the changed tool.

### CI integration

Add to your CI pipeline in this order:

```
pytest tests/mcp/test_schema_lint.py          # Layer 0 — fast, always
pytest tests/mcp/                             # Layer 1 — unit, always
pytest eval/test_contracts.py                 # Layer 1 — contract, always
python eval/run_tool_selection.py --ci        # Layer 2 — LLM, on PR
python eval/run_trajectory.py --ci            # Layer 4 — e2e, nightly
```

---

## Metrics Reference

| Metric | Description | Target |
|---|---|---|
| **Tool selection accuracy** | % of scenarios where the correct tool is selected | ≥ 95% |
| **Parameter validity rate** | % of closed-set parameters passed with a valid value | 100% |
| **Trajectory completion rate** | % of golden trajectories completed without wrong tools | ≥ 90% |
| **`context_id` threading rate** | % of multi-step scenarios where context_id is passed correctly | 100% |
| **Error recovery rate** | % of error-status responses (blocked/not_found) correctly handled | ≥ 80% |
| **Description coverage** | % of tools with a docstring ≥ 20 chars | 100% |
| **Redundant call rate** | Avg extra tool calls per trajectory (lower is better) | ≤ 0.5 |

---

## Common Failure Modes

**Wrong tool in the same group**
The model calls `resolve_deprecation` when it should call `entity_evolution`. Fix:
add "For the full replacement chain use `entity_evolution` instead" to the
`resolve_deprecation` description.

**Closed-set parameter hallucination**
The model passes `scope="API"` instead of `scope="api-surface"`. Fix: enumerate
valid values explicitly in the docstring or parameter `description` field.

**Missing `context_id` threading**
The model calls `get_pending_steps` without the `context_id` from the prior
`create_migration_context` call. Fix: add "Returns: context_id — use in all
subsequent context tool calls" to `create_migration_context`.

**Double-close on auto-close**
The model calls `close_migration_context` after `update_step_status` already
auto-closed the context. Fix: state "update_step_status auto-closes the context
when all steps complete" in both tool descriptions.

**Empty pending steps misread as error**
The model retries or calls the wrong tool when `get_pending_steps` returns `[]`.
Fix: state both empty-list cases (all done vs no MigrationStep nodes) and name
the fallback tool (`build_recipe_plan`).

**Mutation attempt in `execute_custom_cypher`**
The model generates a Cypher query containing `MERGE` or `SET`. Fix: list all
blocked keywords in the description so the model self-corrects before the call.

---

## Quick-start evaluation run

```bash
# 1. Start the server (stdio mode — client manages the process)
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=your-password

# 2. Run schema lint and contract tests
uv run pytest tests/mcp/ -v

# 3. Run tool selection suite (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=your-key
uv run python eval/run_tool_selection.py --model claude-sonnet-4-6

# 4. Inspect results
cat eval/results/latest.json | python -m json.tool
```

Expected output after all improvements in spec 005a are applied:

```
Schema lint:          21/21 tools have descriptions ✓
Contract tests:       47/47 passed ✓
Tool selection:       21/21 correct (100%) ✓
Parameter validity:   18/18 closed-set probes passed ✓
```
