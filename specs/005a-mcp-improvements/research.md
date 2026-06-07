# Research: MCP Server Improvements

**Spec**: `005a-mcp-improvements`
**Date**: 2026-06-07

---

## 1. Harness Invocation — Three Approaches

The four-loop migration harness must be triggered by a user or agent. Three approaches were evaluated.

### Approach 1 — Static Prompt in USAGE.md (Current State)

Users copy a block of text from `USAGE.md`, fill in `[framework]`, `[current_version]`, `[target_version]`, and `[project_id]` manually, and paste it into their agent chat.

**Pros**
- Zero implementation cost — already done.
- Works with every client regardless of MCP protocol support.

**Cons**
- Copy-paste is error-prone; bracket placeholders are easy to miss.
- Drift: if the harness changes, `USAGE.md` must be updated separately.
- No parameter validation — a misspelled version string silently produces wrong results.
- No re-entrancy signal — there is no way to inject a `context_id` if the agent is resuming a session.

---

### Approach 2 — Bake Four-Loop Logic into the Skill Resource

Enrich `skill://framework-migration/main` so that loading the skill gives the agent enough context to start the harness with minimal prompt text. The user only needs to say "load the migration skill and migrate this project from X to Y".

**Pros**
- No new protocol surface — resources are universally supported.
- Skill is already versioned in the repo alongside the server code.
- Works in Cursor, Claude Code, and any compliant MCP client.

**Cons**
- The agent still has to interpolate framework/version values from free text; no structured parameter passing.
- The skill is a static Markdown file — it cannot generate a context-aware preamble (e.g., resume message with an existing `context_id`).
- Useful as a complement but not a replacement for structured invocation.

---

### Approach 3 — MCP `prompts` Capability with Parameters (Recommended)

Implement parameterized MCP prompts via `@mcp.prompt()`. The current `migration_workflow_prompt()` in `server.py` exists but has no parameters — it is effectively static text. The improvement is to add parameters:

```python
@mcp.prompt()
def start_migration(
    framework: str,
    current_version: str,
    target_version: str,
    project_id: str,
    context_id: str | None = None,
) -> str:
    ...
```

Clients that support `prompts/list` and `prompts/get` (Claude Code, MCP Inspector) will surface a form with these fields. The prompt body interpolates real values into the harness preamble and optionally injects a `context_id` for session resumption.

**Pros**
- First-class MCP feature: parameters are validated server-side before the prompt string is generated.
- `context_id` enables re-entrant sessions — the agent knows it is resuming, not starting fresh.
- No copy-paste; client presents a structured input form.
- The prompt body is co-located with the server code, so harness changes stay in sync.
- USAGE.md static prompt becomes a fallback, not the primary path.

**Cons**
- Requires implementing the parameterized prompt handlers.
- Cursor's `prompts` support is currently partial — the static fallback in USAGE.md is still needed.
- Adds a small protocol surface (2–3 `@mcp.prompt()` handlers).

**Decision**: Implement Approach 3. Approach 2 (enriching the skill) is also valuable independently and should be done, but does not replace parameterized prompts. Approach 1 remains in USAGE.md as a fallback.

---

## 2. MCP Tool Description Best Practices

### Why Descriptions Matter

The MCP client sends the full list of tool names, descriptions, and parameter schemas to the LLM on each turn. The model uses this information alone to decide which tool to call, with which arguments, and in what order. A vague or missing description forces the model to guess — which leads to wrong tool selection, hallucinated parameters, and unnecessary retries.

### Core Rules

**Rule 1 — Every `@mcp.tool()` function must have a docstring.**
FastMCP uses the function's docstring as the tool description. Without one, the tool name is the only signal the LLM receives. All 21 tool functions in this codebase currently have no docstrings.

**Rule 2 — The first line of the docstring is the LLM-visible description. Make it actionable.**
Form: `<verb> <object> [qualifier]`. Examples:
- ✅ "Return migration rules and lifecycle alerts for a framework version range."
- ❌ "This tool analyzes upgrade paths."

**Rule 3 — Describe what the tool returns, not just what it does.**
The model needs to know what data comes back so it can decide whether to call the tool at all and how to chain it with other tools.

**Rule 4 — State preconditions and when NOT to use the tool.**
If `get_pending_steps` returns an empty list when no `MigrationStep` nodes exist (pre-redesign data), say so — otherwise the agent will retry or call the wrong tool.

**Rule 5 — For parameters with a closed set of valid values, enumerate them in the docstring or `Field(description=...)`.**
`scope`: `"api-surface"`, `"runtime"`, `"config"`, `"build"`, `"test"`. `outcome`: `"completed"`, `"skipped"`, `"failed"`. Without this, the model invents values.

**Rule 6 — Distinguish read vs. write tools clearly.**
Side effects matter. `submit_migration_insight` writes a node and runs duplicate detection. `get_community_insights` is read-only. The model should not treat them symmetrically.

**Rule 7 — Call out idempotency.**
`create_migration_context` is idempotent. `vote_insight` is not (calling it twice with `delta=1` gives +2 votes). Stating this prevents duplicate calls.

**Rule 8 — Keep descriptions under 200 words total (first line + body).**
Beyond that, the model's attention drifts. Put caveats in parameter descriptions, not in the function docstring body.

### Current Gap Analysis

| Tool | Current description | Gap |
|---|---|---|
| `analyze_upgrade_path` | None | Full docstring missing; `scope_filter`, `min_severity`, `format` have no parameter notes |
| `build_recipe_plan` | None | No description of auto/manual track logic or fallback behavior |
| `resolve_deprecation` | None | "One hop" replacement not explained |
| `entity_evolution` | None | 5-hop chain limit not stated |
| `search_migration_knowledge` | None | BM25+vector hybrid not mentioned; `include_community_insights` purpose unclear |
| `search_openrewrite_recipes` | None | `only_composite`, `require_no_params` filters have no effect yet — not disclosed |
| `get_graph_schema` | None | No description of what the schema contains |
| `execute_custom_cypher` | None | Blocked keywords not listed; read-only constraint not stated |
| `submit_migration_insight` | None | Parameter `spring_boot_version` is misleadingly named when `framework` != Spring Boot |
| `get_community_insights` | None | `entity_type` filter is a no-op (reserved) — not disclosed |
| `vote_insight` | None | Negative `delta` for downvote not mentioned |
| `verify_insight` | None | Moderator-only semantics not stated |
| `create_migration_context` | None | Idempotency not stated |
| `get_pending_steps` | None | Empty-list condition (no `MigrationStep` nodes) not stated |
| `update_step_status` | None | `reason` is accepted but not persisted — not stated |
| `get_steps_for_scope_tier` | None | Valid scope values not listed |
| `close_migration_context` | None | Auto-close vs explicit close not distinguished |
| `resolve_paysafe_dependency_by_service_name` | None | Requires `FINDIT_AUTH_TOKEN` + `GITLAB_API_KEY` — not stated |
| `list_pipeline_runs` | None | No description of what a "pipeline run" is |
| `get_artifact_content` | None | Path resolved from graph, not filesystem — not stated |
| `install_migration_skill` | None | Valid `target` values not listed |

### MCP Prompt Best Practices

A `@mcp.prompt()` handler should:
- Accept typed parameters that map to what a user would fill in a form.
- Return a complete, ready-to-send prompt string — not a template with unfilled placeholders.
- Be named in imperative form: `start_migration`, `resume_migration`.
- Include a docstring that explains the scenario the prompt covers.
- Optional parameters (like `context_id`) should be handled so the prompt is coherent whether or not they are supplied.

---

## 3. Proposed Prompts

### `start_migration` (new, parameterized)

Replaces `migration_workflow_prompt()`. Parameters:
- `framework: str` — e.g. `"Spring Boot"`, `"WildFly"`, `"Quarkus"`
- `current_version: str` — e.g. `"2.7"`
- `target_version: str` — e.g. `"3.2"`
- `project_id: str` — e.g. `"payments-service"`
- `context_id: str | None = None` — supply when resuming a session

### `resume_migration` (new)

Convenience prompt for re-entry. Parameters: `context_id: str`. Generates a prompt that loads the skill and jumps directly to Loop III with the existing context.

### `migration_workflow_prompt` (existing, keep as-is)

The zero-parameter fallback. No changes needed — it is the "quick-start" for clients that do not support parameterized prompts.
