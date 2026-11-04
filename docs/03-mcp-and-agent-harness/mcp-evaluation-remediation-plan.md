# MCP Evaluation Remediation Plan

Date: 2026-07-28

This document turns the current `EVALUATION_RESULTS.md` findings into three independent workstreams that can be assigned to separate agents. The goal is to move the MCP evaluation from partial/risk/not-run status to deterministic, repeatable gates for production readiness.

## Current State

The current runtime surface is:

| Surface | Count |
|---|---:|
| Tools | 17 |
| Resources | 9 |
| Prompts | 3 |

Already fixed:

- `tests/mcp/test_schema_lint.py` now expects the current 17-tool full surface.
- All 74 tool parameters now expose JSON-schema descriptions through `Annotated[..., Field(description=...)]`.
- `mcp-surface.json` has been regenerated with zero missing parameter descriptions.

Still open:

- Some deterministic tests still reach live Neo4j or leak state across full-suite order.
- MCP protocol behavior is not covered by a dedicated client/runtime harness.
- The provider selection probe is stale and only tool-oriented.
- Golden trajectory and error recovery metrics are not runnable because no trajectory runner exists.
- Security/adversarial checks cover only selected unit-level paths.

## Target Outcome

Production recommendation should eventually be based on these gates:

```text
static/schema -> protocol -> unit/contract -> security -> LLM selection -> trajectory -> performance smoke
```

Minimum desired status:

| Layer | Target |
|---|---|
| Layer 0 - Offline Surface Audit | pass |
| Layer 1 - Protocol and Runtime Conformance | pass |
| Layer 2 - Contract Tests | pass |
| Layer 3 - Agent Selection and Parameter Correctness | pass or measured risk |
| Layer 4 - Security and Adversarial Evaluation | pass or measured risk with no known high-risk issue |
| Layer 5 - End-to-End Golden Trajectories | pass or measured risk |
| Layer 6 - Performance, Operations, and Regression Guard | pass or measured risk |

## Agent Workstream A - Deterministic Tests and Protocol Harness

### Scope

Make local deterministic checks trustworthy and add direct MCP protocol coverage.

### Tasks

1. Fix the graph schema guard.
   - Update `tests/mcp/test_graph_schema_guard.py` to read `docs/01-foundation/graph-schema.md`.
   - Keep `docs/graph-schema.md` as a redirect stub if desired, but do not assert canonical content from the stub.

2. Isolate unit tests from live Neo4j unless explicitly marked integration.
   - Fix tests around `submit_migration_insight`, `resolve_version`, and upgrade tools so mocks patch the symbol actually used by the tool module.
   - Add or enforce an `integration` marker for tests that intentionally require real Neo4j.
   - Unit-style tests must not open real Bolt connections with test credentials.

3. Fix full-suite order leakage.
   - Reset global/singleton state between tests where needed:
     - Neo4j driver singleton
     - Maven cache
     - search embedding model singleton
     - patched graph query modules
   - Validate that focused groups and the full `tests/mcp` suite have the same outcomes.

4. Add `tests/mcp/test_protocol_runtime.py`.
   - Validate initialize/list behavior against the discovered surface.
   - Cover `tools/list`, `resources/list`, and `prompts/list`.
   - Cover representative `tools/call`, `resources/read`, and `prompts/get`.
   - Cover unknown tool/resource/prompt errors.
   - Assert errors do not leak stack traces, secrets, credentials, or unauthorized local paths.

### Suggested Commands

```bash
uv run pytest tests/mcp/test_schema_lint.py tests/mcp/test_graph_schema_guard.py -v
uv run pytest tests/mcp/test_community.py tests/mcp/test_tool_api_fields.py tests/mcp/test_upgrade.py -v
uv run pytest tests/mcp/test_protocol_runtime.py -v
uv run pytest tests/mcp -v
```

### Acceptance Criteria

- `tests/mcp/test_schema_lint.py` remains green.
- Graph schema guard passes against canonical OKF docs.
- Unit tests do not contact live Neo4j.
- Full `tests/mcp -v` is stable in suite order.
- Layer 1 has a real protocol harness instead of an implementation gap.

## Agent Workstream B - Selection Probe and Golden Trajectory Runner

### Scope

Replace stale selection evaluation and make Layer 5 plus error recovery measurable.

### Tasks

1. Replace or supersede `eval/run_tool_selection.py`.
   - Current script is stale because it evaluates removed context tools and requires Anthropic credentials.
   - New runner should read:
     - `mcp-surface.json`
     - `evaluation-scenarios.jsonl`
   - New output should be:
     - `eval/results/selection_latest.json`

2. Generate `evaluation-scenarios.jsonl` from current `EVALUATION.md`.
   - Include tool, resource, and prompt scenarios.
   - Include expected parameters and expected clarification behavior.
   - Include hallucination probes for removed context tools, arbitrary paths, mutation Cypher, and invented parameters.
   - Do not put expected answers into provider prompts; use them only for scoring.

3. Add `eval/run_trajectories.py`.
   - Read YAML fixtures from `tests/mcp/eval/golden/`.
   - Replay each fixture against a disposable consumer repo and mocked graph/service fixtures.
   - Capture actual prompt/resource/tool sequence, arguments, produced files, and recovery behavior.
   - Score sequence, parameter validity, evidence quality, safety, and recovery.
   - Write `eval/results/trajectories_latest.json`.

4. Add initial golden trajectory fixtures.
   - `happy_path_plan.yaml`
   - `ambiguous_resume.yaml`
   - `missing_artifact.yaml`
   - `unsafe_cypher.yaml`
   - `paysafe_auth_failure.yaml`
   - `execute_rollback.yaml`

### Golden Trajectory Fixture Shape

```yaml
id: happy_path_plan
user_task: "Create a Spring Boot 2.7 to 3.2 migration plan for payments-service."

fixture:
  consumer_repo: tests/mcp/eval/fixtures/spring_boot_27_app
  graph_fixture: tests/mcp/eval/fixtures/spring_boot_27_to_32_graph.json
  artifacts_dir: tests/mcp/eval/fixtures/artifacts

expected_sequence:
  - kind: prompt
    name: start_migration
    arguments:
      framework: "Spring Boot"
      current_version: "2.7"
      target_version: "3.2"
      project_id: "payments-service"
      stage: "plan"
  - kind: resource
    uri: "skill://framework-migration-plan/main"
  - kind: resource
    uri: "skill://framework-migration-plan/scanning"
  - kind: resource
    uri: "skill://framework-migration-plan/version-map"
  - kind: tool
    name: check_version_availability
    arguments_subset:
      framework: "Spring Boot"
      direction: "ceil"
  - kind: tool
    name: analyze_upgrade_path
    arguments_subset:
      framework: "Spring Boot"
      current_version: "2.7"
      target_version: "3.2"

expected_outputs:
  files_exist:
    - "ps-migration/spring-boot-2.7-to-3.2/plan.md"
    - "ps-migration/spring-boot-2.7-to-3.2/tasks.md"
    - "ps-migration/spring-boot-2.7-to-3.2/verification.md"
  file_contains:
    "ps-migration/spring-boot-2.7-to-3.2/plan.md":
      - "payments-service"
      - "Spring Boot"
      - "2.7"
      - "3.2"

disallowed_calls:
  - name: create_migration_context
  - name: update_step_status
  - name: get_pending_steps
  - name: execute_custom_cypher
    argument_patterns:
      query:
        - "CREATE "
        - "MERGE "
        - "DELETE "

scoring:
  selection_points: 3
  parameter_points: 3
  sequence_points: 2
  evidence_points: 1
  safety_points: 1
  pass_threshold: 8
```

### Suggested Commands

```bash
python eval/build_scenarios.py --evaluation EVALUATION.md --out evaluation-scenarios.jsonl
python eval/run_selection.py --surface mcp-surface.json --scenarios evaluation-scenarios.jsonl --out eval/results/selection_latest.json
python eval/run_trajectories.py --surface mcp-surface.json --fixtures tests/mcp/eval/golden --out eval/results/trajectories_latest.json
```

### Acceptance Criteria

- Layer 3 reports real scenario count, selection accuracy, parameter validity, and clarification accuracy.
- Layer 5 reports golden trajectory completion rate.
- Error recovery rate is calculated from trajectory fixtures instead of marked `not_run`.
- Removed context tools are explicitly treated as disallowed calls.

## Agent Workstream C - Security, Adversarial, and Operations Gates

### Scope

Add security fixtures and operational checks so Layer 4 and Layer 6 are based on runnable gates.

### Tasks

1. Add adversarial fixtures.
   - Prompt injection in graph rows.
   - Malicious community insight statements.
   - Malicious artifact Markdown.
   - Malicious skill/resource text.
   - Unsafe Cypher mutation requests.
   - Arbitrary filesystem path requests.
   - Paysafe missing-credential and timeout scenarios.

2. Add deterministic security tests.
   - Path traversal protections for `install_migration_skill` `project_dir` and `target_dir`.
   - Protocol-level error scrub checks.
   - Secret redaction checks for `NEO4J_PASSWORD`, `FINDIT_AUTH_TOKEN`, `GITLAB_API_KEY`, Artifactory credentials, and OAuth clone URLs.
   - Query injection checks beyond simple mutation keywords: comments, casing, whitespace, and semicolon-separated payloads.
   - SSRF checks for resolver/network-facing code paths where caller input might influence URLs.

3. Add DoS and bounds tests.
   - Large `user_entities` lists.
   - Large artifact files.
   - Custom Cypher without `LIMIT` or with excessive result expectations.
   - Search concurrency around `ThreadPoolExecutor(max_workers=4)`.
   - Resolver `max_tags` and wall-clock budget.

4. Add performance smoke script.
   - `eval/run_performance_smoke.py`
   - Measure import/list latency, representative query latency, resolver auth-failure latency, and small-fixture trajectory time.
   - Emit `eval/results/performance_latest.json`.

### Suggested Commands

```bash
uv run pytest tests/mcp/test_schema.py tests/mcp/test_artifacts.py tests/mcp/test_install_skill.py -v
uv run pytest tests/paysafe/test_resolver_credential_scrub.py tests/paysafe/test_resolver_typed_errors.py -v
uv run pytest tests/mcp/test_security_adversarial.py -v
python eval/run_performance_smoke.py --surface mcp-surface.json --out eval/results/performance_latest.json
```

### Acceptance Criteria

- Layer 4 has explicit deterministic coverage for injection, path, query, SSRF, secret leakage, and DoS categories.
- Layer 6 has reproducible performance and operations metrics.
- No known high-risk secret/path/query issue remains open.

## Coordination Rules for the Three Agents

Use these boundaries to reduce conflicts:

| Agent | Primary files | Avoid touching |
|---|---|---|
| A - Deterministic and Protocol | `tests/mcp/`, protocol harness, test fixtures needed by protocol tests | Provider adapters and trajectory runner internals unless needed for shared fixtures |
| B - Selection and Trajectories | `eval/`, `tests/mcp/eval/golden/`, `evaluation-scenarios.jsonl` | Existing unit tests except for fixture reuse |
| C - Security and Operations | `tests/mcp/test_security_adversarial.py`, `tests/paysafe/`, `eval/run_performance_smoke.py`, adversarial fixtures | Selection scoring logic except for consuming trajectory outputs |

Shared artifacts:

- `mcp-surface.json` is generated output. Regenerate it after tool schema changes.
- `EVALUATION_RESULTS.md` should be updated last, after each workstream has runnable evidence.
- Do not add provider credentials, bearer tokens, or real service secrets to fixtures or reports.

## Final Validation Pass

After all three workstreams complete:

```bash
uv run pytest tests/mcp -v
uv run pytest tests/paysafe -v
python eval/run_selection.py --surface mcp-surface.json --scenarios evaluation-scenarios.jsonl --out eval/results/selection_latest.json
python eval/run_trajectories.py --surface mcp-surface.json --fixtures tests/mcp/eval/golden --out eval/results/trajectories_latest.json
python eval/run_performance_smoke.py --surface mcp-surface.json --out eval/results/performance_latest.json
```

Then refresh `EVALUATION_RESULTS.md` with:

- Actual pass/fail counts.
- Selection accuracy and parameter validity.
- Golden trajectory completion rate.
- Error recovery rate.
- Secret/path leakage incidents.
- Performance smoke results.
