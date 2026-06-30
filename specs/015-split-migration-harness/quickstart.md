# Quickstart: Split Migration Harness

This guide provides a reproducible, end-to-end sequence for testing the split migration harness locally using a known small version range.

## Prerequisites

1. Ensure your local Neo4j/Memgraph instance is running.
2. Ensure the `migration_oracle` environment is synced (`uv sync`).
3. Start the MCP server (the exact command depends on how you pass the active stage, e.g., via environment variables if testing the gating mechanism).

## The Sequence

We will simulate a migration for a dummy project `demo-service` upgrading from Spring Boot `3.3.0` to `3.4.0`.

### 1. Plan Stage

Start an agent session with the `plan` stage active.

**Prompt**:
```text
Run the migration plan stage for project "demo-service" upgrading "Spring Boot" from "3.3.0" to "3.4.0".
```
*Expected Outcome*: The agent creates a `MigrationContext` and populates the pending queue. Note the `context_id` returned.

### 2. Gap-Check Stage

Start a new agent session with the `gap-check` stage active.

**Prompt**:
```text
Run the gap-check stage for context_id "demo-service|3.3.0|3.4.0". Ensure that at least one gap-check flag is fired (e.g., by injecting a mock uncertain rule or unresolved dependency) so that clarify has something to act on.
```
*Expected Outcome*: The agent reads the context, performs the mechanical audit, and writes `GapCheckFlag` properties to the context. It outputs a list of findings containing at least one flag.

### 3. Clarify Stage (Optional)

Start a new agent session with the `clarify` stage active.

**Prompt**:
```text
Run the clarify stage for context_id "demo-service|3.3.0|3.4.0". Add a manual step with summary "Update custom security config" and instruction "Review the custom security filter chain for deprecated methods."
```
*Expected Outcome*: The agent uses `add_manual_step` to create a new `MigrationStep` with `origin="manual"` and scopes it to the context.

### 4. Preview Stage

Start a new agent session with the `preview` stage active.

**Prompt**:
```text
Run the preview stage for context_id "demo-service|3.3.0|3.4.0".
```
*Expected Outcome*: The agent renders the plan grouped by risk label, including the manual step and any gap-check caveats. Verify that the agent has no mutation tools available.

### 5. Execute Stage

Start a new agent session with the `execute` stage active.

**Prompt**:
```text
Run the execute stage for context_id "demo-service|3.3.0|3.4.0". Mark the first step as completed.
```
*Expected Outcome*: The agent fetches the pending steps and uses `update_step_status` to mark the step as completed.

### 6. Feedback Stage

Start a new agent session with the `feedback` stage active.

**Prompt**:
```text
Run the feedback stage for context_id "demo-service|3.3.0|3.4.0". Close the migration context.
```
*Expected Outcome*: The agent calls `close_migration_context` and the final status is recorded.