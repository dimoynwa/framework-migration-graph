# Quickstart: Verifying Hybrid Plan Rendering

Because this feature consists strictly of prompt-text/documentation amendments with zero application code changes, verification is performed through manual walk-through rather than starting a running service.

## Verification Steps

1. **Review the Amended Prompt Files**
   Ensure the following files contain the newly specified anchor text and constraints without modifying the underlying MCP tool contract signatures:
   - `migration_oracle/mcp/skills/framework_migration_plan.md`
   - `migration_oracle/mcp/skills/framework_migration_gap_check.md`
   - `migration_oracle/mcp/skills/framework_migration_clarify.md`
   - `migration_oracle/mcp/skills/framework_migration_preview.md`

2. **Walk the Worked Example by Hand**
   Open the design document at `docs/hybrid-plan-rendering.md` and navigate to `§6` (the worked example featuring `payments-ledger-service`, Spring Boot 2.7.18 → 3.2.4, and rules r1/r2).
   
   - **Simulate the Plan Stage**: Re-read the new text in `framework_migration_plan.md`. Observe how rule `r1` (actionable) gets classified as `CONCRETE TASK` and `r2` (incomplete) gets classified as `RELEVANCE-INDEX ENTRY`. Mentally verify that the corresponding suffixes would be appended to the `result_summary` for `update_queried_entity`.
   - **Simulate the Gap-Check Stage**: Re-read the new text in `framework_migration_gap_check.md`. Verify that the pre-existing `stepless_rule` captures the `r2` relevance-index entry.
   - **Simulate the Clarify Stage**: Imagine applying a manual fix to `r2` using `add_manual_step`. Verify per the text in `framework_migration_clarify.md` that the origin is strictly set and preserved as `"manual"`.
   - **Simulate the Preview Stage**: Re-read the text in `framework_migration_preview.md` and verify that rendering instructions mandate showing the provenance (e.g. `[manual]`) for `r2` and `[graph]` for `r1`.

3. **Verify the Constraints**
   Confirm that the `update_queried_entity`, `write_gap_check_flags`, `add_manual_step`, and `get_pending_steps` tools have the exact same signatures as before, ensuring the zero-code-change boundary condition holds.

4. **Verify Stage-Gating**
   Confirm the YAML frontmatter `compatibility.tools` block in each file is byte-identical to its pre-edit state, ensuring MCP_ACTIVE_STAGE gating mechanics and server restart behaviors are completely unaffected.