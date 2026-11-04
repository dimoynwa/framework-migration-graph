# Quickstart: Testing the Research Stage

Follow these steps to locally test the Split Migration Harness amendments, specifically the insertion of the `/migration-research` stage and its consumption by `/migration-plan`.

## Prerequisites
- A target project repository with a supported framework (e.g., Spring Boot).
- The Migration Oracle MCP server running.

## Step 1: Run the full inline pipeline (Baseline)
First, generate a baseline to verify the `DEFAULT_PATH_EQUIVALENCE`.
1. Delete any existing `ps-migration` folder in your target project.
2. Run `/migration-plan` directly.
3. Verify that `plan.md`, `tasks.md`, and `verification.md` are generated.
4. Open `plan.md` and verify the header contains `Research: inline`.
5. Copy the generated files to a backup directory (e.g., `baseline-plan/`) for diffing later.

## Step 2: Run the Research Stage
1. Delete the `ps-migration` folder to start fresh.
2. Run `/migration-research` on the target project.
3. Verify that ONLY `research.md` is generated in `ps-migration/{framework}-{from}-to-{to}/`.
4. Open `research.md` and verify the header metadata, scanned entities, rule results (with nested entity deprecation chains), and complete instruction texts are present.

## Step 3: Run the Plan Stage (Consuming Research)
1. Without modifying the codebase, run `/migration-plan`.
2. Observe the agent output to verify that Step 1.5 detects `research.md`, successfully matches the scan checksum, and explicitly skips Steps 3–4 (version-map load and knowledge queries).
3. Verify that `plan.md`, `tasks.md`, and `verification.md` are generated.
4. Open `plan.md` and verify the header contains `Research: ps-migration/.../research.md` and `Research-generated: <timestamp>`.

## Step 4: Test Version Mismatch Logic
1. Re-run `/migration-research` with a different target version (e.g. modifying the "To" version).
2. Run `/migration-plan` with the original versions (so they don't match the new `research.md`).
3. Verify the agent emits a clear warning that the versions mismatched, falls through to inline knowledge queries, and `Research: inline` is generated in `plan.md`.

## Step 5: Verify Equivalence
1. Run a diff between the baseline `plan.md`/`tasks.md` and the newly generated files (from Step 3).
2. Ensure that task counts, task order, render classifications, and exact instructions are identical. Diff the files excluding lines matching `Generated:`, `Project:`, `Research:`, `Research-generated:`, and `Graph snapshot:` to avoid false differences from runtime context.

## Step 6: Test Checksum Mismatch Logic
1. Run `/migration-research` to reset state to valid version match. Verify that `/migration-research` completes without error even though `research.md` already exists from Step 2.
2. Modify a source file in the target project to add a new framework import or property (changing the codebase scan result).
3. Run `/migration-plan` again (without re-running research).
4. Verify that the agent emits a clear warning that the codebase scan checksum no longer matches the `research.md` artifact.
5. Tell the agent to proceed with the potentially stale artifact. Ensure it skips Steps 3-4 and renders the files.

## Step 7: Test Gap-Check and Preview Provenance
1. Run `/migration-gap-check`. Verify it successfully reads the provenance headers and does not error out.
2. Run `/migration-preview`. Verify the summary block includes a display line stating the knowledge source (the `research.md` file and date).
