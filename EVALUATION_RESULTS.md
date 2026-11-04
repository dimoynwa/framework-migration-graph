# PaysafeMigrationOracle - Evaluation Results

Date: 2026-07-28
Runner mode: codex-inline

---

## Summary

| Layer | Status | Key Result |
|---|---|---|
| Layer 0 - Offline Surface Audit | risk | Runtime-discovered surface is 17 tools, 9 resources, 3 prompts as expected by `EVALUATION.md`; schema lint now passes and all 74 tool parameters have schema-level descriptions. Remaining risk is missing protocol/resource-injection coverage. |
| Layer 1 - Protocol and Runtime Conformance | risk | FastMCP import/list discovery works and stage gating matches documented counts; full protocol client coverage for `initialize`, JSON-RPC errors, cancellation, SSE, and streamable HTTP is not implemented. |
| Layer 2 - Contract Tests | fail | Schema lint gate now passes 6/6. Previous focused/full failures remain outside this fix: real Neo4j calls from tests that should be mocked plus full-suite isolation issues. |
| Layer 3 - Agent Selection and Parameter Correctness | risk | Inline selection against current surface: 22/22 primary scenarios selected the expected tool/resource/prompt; provider-backed probe was not run because provider credentials are unset and the bundled Anthropic script is stale. |
| Layer 4 - Security and Adversarial Evaluation | risk | Existing deterministic Cypher-blocking and credential-scrub tests mostly pass; no dedicated prompt-injection, path traversal, SSRF, protocol error-scrub, or DoS harness was found. |
| Layer 5 - End-to-End Golden Trajectories | not_run | YAML fixtures exist under `tests/mcp/eval/`, but no runnable `eval/run_trajectories.py` harness is present. |
| Layer 6 - Performance, Operations, and Regression Guard | risk | Import/list smoke is about 11.2-11.4s locally; invalid `MIGRATION_MODE` fails clearly. Concurrency, memory, timeout, SBOM, and dependency vulnerability gates are not implemented. |

---

## Layer 0 - Offline Surface Audit

### Inventory

Generated artifact: `mcp-surface.json`.

Discovered by importing `migration_oracle.mcp.server` with `MIGRATION_MODE=full`, then calling FastMCP list APIs:

| Kind | Expected | Discovered | Status |
|---|---:|---:|---|
| Tools | 17 | 17 | pass |
| Resources | 9 | 9 | pass |
| Prompts | 3 | 3 | pass |

Discovered tools:

`install_migration_skill`, `resolve_paysafe_dependency_by_service_name`, `search_migration_knowledge`, `search_openrewrite_recipes`, `analyze_upgrade_path`, `build_recipe_plan`, `check_version_availability`, `list_pipeline_runs`, `get_artifact_content`, `submit_migration_insight`, `get_community_insights`, `vote_insight`, `verify_insight`, `resolve_deprecation`, `entity_evolution`, `get_graph_schema`, `execute_custom_cypher`.

Stage-gated runtime counts:

| Stage | Expected | Discovered | Status |
|---|---:|---:|---|
| research | 13 | 13 | pass |
| plan | 14 | 14 | pass |
| gap-check | 1 | 1 | pass |
| clarify | 1 | 1 | pass |
| preview | 1 | 1 | pass |
| execute | 9 | 9 | pass |

### Required Check Results

| surface_kind | surface_name | severity | check | finding | suggested_fix |
|---|---|---|---|---|---|
| tool | all | fixed | parameter schema clarity | 74/74 tool parameters now have JSON-schema `description` fields. | Keep `test_all_tool_parameters_have_descriptions` as the regression gate. |
| test | `tests/mcp/test_schema_lint.py::test_tool_count` | fixed | expected inventory | Test now asserts the current 17-tool full surface. | Keep inventory synchronized with `EVALUATION.md` and `tests/mcp/test_server.py`. |
| doc | `docs/graph-schema.md` | medium | canonical docs redirect | `test_graph_schema_formula_unchanged` reads the redirect stub and fails to find the formula now located under OKF docs. | Point the guard to `docs/01-foundation/graph-schema.md` or keep the formula in the redirect stub. |
| resource | skill resources | medium | untrusted instructions | Resources are Markdown instructions exposed to agents; no deterministic injection-resistance harness was found. | Add fixture resources with malicious text and assert agents treat returned text as evidence/instructions only within the intended skill boundary. |

### Recommended Quality Findings

Descriptions are generally behavior-first and distinct enough for inline selection. Schema-only clients now see parameter semantics for `artifact_type`, `direction`, `format`, `scope_filter`, `min_severity`, `target`, `scope`, `delta`, and the Paysafe compatibility parameters.

---

## Layer 1 - Protocol and Runtime Conformance

### Commands

```bash
env NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test NEO4J_USERNAME=neo4j MIGRATION_MODE=full MCP_TRANSPORT=stdio .venv/bin/python -c '<discover mcp surface>'
env MIGRATION_MODE=bad NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test .venv/bin/python -c 'import migration_oracle.mcp.server'
env NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test NEO4J_USERNAME=neo4j MIGRATION_MODE=full MCP_ACTIVE_STAGE=<stage> .venv/bin/python -c '<list tools>'
```

### Results

- Full runtime import/list discovery succeeded with 17 tools, 9 resources, 3 prompts.
- Invalid `MIGRATION_MODE='bad'` fails before serving with a clear valid-options error.
- Stage gating produced the expected per-stage tool counts.
- `tests/mcp/test_server.py` startup sequencing checks passed under mocks.

### Gaps

- No dedicated MCP protocol harness was found for actual `initialize`, `tools/list`, `resources/list`, `prompts/list`, `tools/call`, `resources/read`, `prompts/get`, unsupported methods, cancellation, or shutdown over stdio/SSE/streamable HTTP.
- Runtime startup with real Neo4j credentials was not validated. Test credentials caused Neo4j authentication failures when tests reached live graph calls.

---

## Layer 2 - Contract Tests

### Commands

```bash
env NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test NEO4J_USERNAME=neo4j MIGRATION_MODE=full MCP_TRANSPORT=stdio uv run pytest tests/mcp/test_schema_lint.py tests/mcp/test_feature_flag.py tests/mcp/test_server.py tests/mcp/test_prompts.py -v
env NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test NEO4J_USERNAME=neo4j MIGRATION_MODE=full MCP_TRANSPORT=stdio uv run pytest tests/mcp/test_schema.py tests/mcp/test_artifacts.py tests/mcp/test_deprecation.py tests/mcp/test_upgrade.py tests/mcp/test_analyze_upgrade_path.py tests/mcp/test_search.py tests/mcp/test_search_openrewrite_recipes.py tests/mcp/test_community.py tests/mcp/test_paysafe_tool.py tests/paysafe/test_resolver_credential_scrub.py -v
env NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test NEO4J_USERNAME=neo4j MIGRATION_MODE=full MCP_TRANSPORT=stdio uv run pytest tests/mcp -v
```

Initial sandboxed `uv run` failed on `/Users/dimo.drangov/.cache/uv/sdists-v9/.git` permission access; rerun with approval succeeded.

### Passing Tests

- Schema lint gate after fixes: 6/6 passed.
- Previous fast gate before this fix: 26/27 passed.
- Focused contract/security group: 64/68 passed.
- Full MCP suite: 189/221 passed.
- Passing areas include feature flags, stage gating, server startup order, prompts, skill resources, install skill behavior, Cypher mutation blocking, artifacts, deprecation, upgrade-path projections, OpenRewrite search filters, many Paysafe resolver typed-error tests, and credential scrubbing.

### Failures

| Command | Test | Error summary | Affected surface | Likely owner layer |
|---|---|---|---|---|
| fast gate | `tests/mcp/test_schema_lint.py::test_tool_count` | Fixed; now expects 17 and passes. | full tool inventory | Layer 0 |
| focused group | 4 `tests/mcp/test_community.py::test_submit_insight_*` tests | Tests patched embedding/community write calls, but `submit_migration_insight` still called real `resolve_version`, causing Neo4j auth/rate-limit errors. | `submit_migration_insight` | Layer 2 |
| full suite | `tests/mcp/test_graph_schema_guard.py::test_graph_schema_formula_unchanged` | Guard reads `docs/graph-schema.md`, which is now a redirect stub. | graph schema docs | Layer 0/2 |
| full suite | `tests/mcp/test_paysafe_tool.py::test_resolve_delegates_to_resolver` | Mock expected resolver call; in full-suite order the call count was 0. This passed in the focused group. | Paysafe resolver tool | Layer 2 isolation |
| full suite | `tests/mcp/test_resolve_version.py::*` | Live Neo4j authentication/rate-limit errors. | version resolution | Layer 2 environment/isolation |
| full suite | `tests/mcp/test_schema.py::test_execute_custom_cypher_safe`, `test_get_graph_schema_has_server_build` | Failed only in full-suite order; focused group passed. | schema/Cypher tools | Layer 2 isolation |
| full suite | `tests/mcp/test_search.py::*`, `tests/mcp/test_search_content.py::*` | Search fixture/mocking failures only in full-suite order; focused group passed. | search tools | Layer 2 isolation |
| full suite | `tests/mcp/test_tool_api_fields.py::test_submit_insight_*` | Same live version-resolution/auth issue around `submit_migration_insight`. | community tool return shape | Layer 2 |
| full suite | several `tests/mcp/test_upgrade.py::*` | Live `resolve_version` calls after mock/state leakage; these passed in focused group. | upgrade tools | Layer 2 isolation |

### Missing Contracts

- Protocol-level MCP request/response tests.
- Dedicated resource-read tests for every `skill://` URI through the MCP runtime.
- Dedicated prompt-get tests through the MCP runtime.
- Tests that isolate `resolve_version` in community-write and upgrade-tool unit tests.

---

## Layer 3 - Agent Selection and Parameter Correctness

### Mode

Codex-inline, no provider API. The bundled `eval/run_tool_selection.py --ci` was attempted and failed because `ANTHROPIC_API_KEY` is unset. It is also stale: it contains 21 old tool-only scenarios, including removed context tools, instead of the current 22 tool/resource/prompt scenarios in `EVALUATION.md`.

### Scenario Results

Inline scoring against `mcp-surface.json` and current descriptions:

| Result | Count |
|---|---:|
| Primary expected selections | 22/22 |
| Closed-set parameter probes | 7/7 selected valid enums or required clarification |
| Hallucination/clarification probes | 6/6 avoided removed tools, unsafe Cypher, arbitrary paths, or invented parameters |

Notable risks:

- `build_recipe_plan` is the right selection for "Build a migration plan split into auto and manual tracks", but valid execution requires `current_version` and `target_version`; the agent must clarify if those are absent.
- `get_community_insights.entity_type` is accepted but not currently applied; the schema description now says this explicitly.
- Enum mappings are now visible in JSON-schema parameter descriptions as well as docstrings.

### Parameter Findings

- `artifact_type`: "filtered migration document" maps to `filtered_md`.
- `direction`: "at or above" maps to `ceil`; "not newer than" maps to `floor`.
- `format`: "give me Markdown" maps to `format="markdown"`.
- `scope_filter`/`min_severity`: "critical API surface changes" maps to `scope_filter=["api-surface"]`, `min_severity="critical"`.
- `target`/`scope`: "install globally for Claude Code" maps to `target="claude-code"`, `scope="global"`.
- `delta`: "upvote" maps to `1`, "downvote" maps to `-1`.

### How To Run A Provider Probe

No provider raw results were produced in this run. Existing provider script failed before probing:

```text
ERROR: ANTHROPIC_API_KEY is not set.
```

Current minimum viable probe flow:

```bash
# Regenerate the current MCP surface.
env NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test NEO4J_USERNAME=neo4j MIGRATION_MODE=full MCP_TRANSPORT=stdio \
  .venv/bin/python -c '<list tools/resources/prompts and write mcp-surface.json>'

# Create provider-neutral scenarios from the Layer 3 table in EVALUATION.md.
# Each JSONL record should include: id, scenario, expected_kind, expected_name,
# expected_arguments, and expected_clarification when applicable.

# Then run a provider adapter that receives mcp-surface.json and the scenario JSONL.
# Do not include expected answers in the prompt; use them only for scoring.
python eval/run_selection.py --surface mcp-surface.json --scenarios evaluation-scenarios.jsonl
```

The existing `eval/run_tool_selection.py` should not be used as the production gate until it is updated: it requires Anthropic credentials and still evaluates removed context tools.

---

## Layer 4 - Security and Adversarial Evaluation

### Results

- `execute_custom_cypher` mutation keyword tests passed in the focused group: `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`, `CALL db`, and case-insensitive blocking.
- `get_artifact_content` rejects invalid artifact types and has no direct path parameter in tests.
- Paysafe credential scrub tests passed: OAuth token, basic auth, clean messages, Artifactory fallback behavior.
- `install_migration_skill` tests cover invalid target/scope, permission failure, missing source rollback/no partial install, project/global targets, and coexistence with unrelated skills.

### Missing Tests

- Prompt injection in graph rows, community insights, artifact content, source docs, OpenRewrite descriptions, and skill resources.
- Protocol-level secret/path leakage assertions for JSON-RPC errors.
- Path traversal probes for `install_migration_skill` `project_dir`/`target_dir`.
- SSRF/unsafe URL probes for resolver/network-facing paths.
- DoS bounds for huge `user_entities`, large artifact files, missing `LIMIT` in custom Cypher, and search concurrency.
- Authorization tests for moderator-only `verify_insight` and trusted-local filesystem access.

### High-Risk Findings

- No tenant/authorization model is enforced by the MCP surface. `verify_insight` and local filesystem tools should remain trusted-operator-only until access control is added or deployment is explicitly local-only.
- `submit_migration_insight` can reach live graph version resolution during unit-style tests, which increases the chance of leaking backend availability/auth behavior through unexpected error paths.

---

## Layer 5 - End-to-End Golden Trajectories

### Results

Not run. `tests/mcp/eval/eval_rollback_scenario.yaml` and `tests/mcp/eval/eval_stateless_fallback_scenario.yaml` exist, but no `eval/run_trajectories.py` harness exists.

### Why Error Recovery Was Not Run

The error recovery metric is trajectory-derived, not just a count of individual error-path unit tests. It needs a harness that executes full workflows, forces documented failures, observes the next agent action, and scores whether the workflow recovered correctly. Current tests cover partial deterministic error paths such as blocked Cypher, invalid artifact type, missing artifact, invalid skill install target, resolver credential scrubbing, and some typed Paysafe failures, but they do not measure recovery across a complete migration workflow.

### Trajectory Findings

- The current surface and prompts support the six golden trajectories in `EVALUATION.md` conceptually.
- There is no deterministic harness to verify actual sequence, parameters, final evidence quality, redundant calls, or safe error recovery.

To generate a golden trajectory, write one fixture per workflow with:

- `id`, `user_task`, and fixture setup.
- `expected_sequence` entries with `kind` (`prompt`, `resource`, or `tool`), `name`, and required argument subset.
- `disallowed` calls, especially removed context tools, arbitrary paths, mutation Cypher, and write calls during read-only stages.
- `expected_evidence` checks for generated files, statuses, or returned fields.
- `error_recovery` checks for documented non-success statuses.

Then add `eval/run_trajectories.py` to replay each fixture against a disposable consumer repo and mocked graph/service fixtures, score sequence/parameters/evidence, and emit JSON results for this report.

---

## Layer 6 - Performance, Operations, and Regression Guard

### Results

| Check | Result |
|---|---|
| Import full MCP server | `real 11.40s`, `user 4.35s`, `sys 1.44s` |
| Import and list tools/resources/prompts | `real 11.19s`, `user 4.36s`, `sys 1.44s` |
| Invalid mode fail-fast | Passed; invalid `MIGRATION_MODE='bad'` raises clear valid-options `ValueError`. |
| Build reproducibility | `uv run pytest` works only with approval in this sandbox because uv cache access is outside workspace permissions. |

### Recommended CI Gate

```text
static/schema -> protocol -> unit/contract -> security -> LLM selection -> trajectory -> performance smoke
```

Recommended immediate commands after fixing stale/isolation failures:

```bash
uv run pytest tests/mcp/test_schema_lint.py tests/mcp/test_feature_flag.py tests/mcp/test_server.py tests/mcp/test_prompts.py -v
uv run pytest tests/mcp/test_schema.py tests/mcp/test_artifacts.py tests/mcp/test_deprecation.py tests/mcp/test_upgrade.py tests/mcp/test_analyze_upgrade_path.py tests/mcp/test_search.py tests/mcp/test_search_openrewrite_recipes.py -v
uv run pytest tests/mcp/test_community.py tests/mcp/test_paysafe_tool.py tests/paysafe/test_resolver_credential_scrub.py -v
python eval/run_selection.py --surface mcp-surface.json --scenarios evaluation-scenarios.jsonl
python eval/run_trajectories.py --fixture tests/mcp/eval --surface mcp-surface.json
python eval/run_performance_smoke.py --fixture small
```

---

## Key Findings and Recommendations

### Priority 1 - Must fix before production

1. Point graph-schema guard at the canonical OKF document.
2. Isolate `submit_migration_insight` and version-resolution tests from live Neo4j unless explicitly running integration tests with valid credentials.
3. Add a real MCP protocol harness for initialize/list/call/read/get/error/shutdown behavior.

### Priority 2 - Should fix before production

1. Replace or update `eval/run_tool_selection.py`; it currently requires Anthropic credentials and evaluates removed context tools.
2. Add deterministic trajectory runner for the YAML fixtures and the six workflows in `EVALUATION.md`.
3. Add prompt/resource/artifact injection fixtures and protocol-level secret/path leakage assertions.

### Priority 3 - Quality improvements

1. Reduce full import/list latency or document the expected local target, especially if sentence-transformers is imported during registration.
2. Add concurrency, timeout, memory, dependency review, and large-input smoke tests.
3. Clarify `get_community_insights.entity_type` in parameter schema as accepted but not applied.

---

## Metrics Summary

| Metric | Target | Result |
|---|---|
| Surface inventory coverage | 100% | 100% against current `EVALUATION.md` surface |
| Protocol conformance pass rate | 100% | Partial only; no dedicated protocol harness |
| Contract pass rate | 100% | Focused gates 26/27 and 64/68; full `tests/mcp` 189/221 |
| Selection accuracy | >= 95% | Inline 22/22 primary scenarios; provider probe not run |
| Parameter validity rate | 100% | Inline closed-set probes 7/7; 74/74 tool parameters now have schema descriptions |
| Clarification accuracy | >= 90% | Inline hallucination/clarification probes 6/6 |
| Golden trajectory completion rate | >= 90% | not_run; no trajectory runner |
| Error recovery rate | >= 80% | not_run; partial deterministic error-path tests only |
| Secret/path leakage incidents | 0 | 0 known from focused credential-scrub/path tests; protocol-level leakage not tested |
| Redundant call rate | <= 0.5 | not_run; no trajectory runner |
