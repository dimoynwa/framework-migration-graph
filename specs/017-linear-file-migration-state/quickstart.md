# Quickstart: End-to-End Migration Walkthrough

This guide demonstrates a complete, linear framework migration against a sample consumer repository using the new file-state workflow.

## Prerequisites
- A consumer repository checking out the framework to be migrated.
- Python 3 with the optional PyYAML preflight for scanning is configured and active.

## 1. Run Plan Stage
Execute the `plan` stage to perform preflight scans, query the graph for knowledge, and construct the migration folder.

```bash
# Tool command executes the 'plan' skill
# Example MCP Call via Client:
# use_mcp_tool(server="migration_oracle", toolName="plan", arguments={"framework": "spring-boot", "from_version": "2.7.18", "to_version": "3.2.0"})
```
**Result**: The system creates a visible folder at the project root: `ps-migration/spring-boot-2.7.18-to-3.2.0/` containing:
- `plan.md` (Strategy, Rule Ledger)
- `tasks.md` (Ordered tasks queue, Relevance Index)
- `verification.md` (Levels 0-5 skeleton, including 5-A/B/C completion gates)

*Sample Rule Ledger Row (`plan.md`):*
`| SPRING-BOOT-3-001 | runtime | org.springframework.http.HttpStatus | TASK | direct | TASK | TASK-001 |`

*Sample Task Block (`tasks.md`):*
```markdown
### TASK-001
**Status**: pending
**Derives-from**: SPRING-BOOT-3-001
**Origin**: graph
**Executor**: openrewrite
**Recipe**: org.openrewrite.java.spring.boot3.SpringBoot3BestPractices
**Effort**: trivial
**File pattern**: src/main/**/*.java
**Instructions**: Migrate HttpStatus usages.
**Before/After**: `HttpStatus.value()` -> `HttpStatus.value()` (or specific framework changes)
**Verify**: `$ ! grep -rq "HttpStatus" src/main/` — Expected: exit 0 (no matches remain).
```

## 2. Run Intermediary Stages (File-Only)

### Gap-Check
Review the tasks for mechanical completeness.
```bash
# Tool command executes the 'gap-check' skill
```
**Result**: `tasks.md` is annotated with missing verifiers or unclassified rules.

### Clarify (Optional)
Resolve entries in the Relevance Index.
```bash
# Example MCP Call:
# use_mcp_tool(server="migration_oracle", toolName="clarify", arguments={})
```
**Result**: Ambiguous entries in `tasks.md` are either promoted to `Origin=manual` tasks or explicitly dismissed with a documented reason.

*Sample Relevance-Index Entry Before:*
`RI-001 | SPRING-BOOT-3-042 | Deprecated Security Config | incomplete | awaiting clarify`

*Sample Relevance-Index Entry After:*
`RI-001 | SPRING-BOOT-3-042 | Deprecated Security Config | incomplete | dismissed: Covered by central auth team migration in separate epic`

### Preview (Optional)
View the read-only rendered representation grouped by risk/scope.
```bash
# Tool command executes the 'preview' skill
```

## 3. Run Execute Stage
Process tasks linearly (TASK-001..NNN) from `tasks.md`.

```bash
# Example MCP Call:
# use_mcp_tool(server="migration_oracle", toolName="execute", arguments={})
```
- As tasks are worked, the `execute` stage directly modifies the `Status` string in `tasks.md` (`pending` -> `done`, `failed`, or `needs-review`).
- Execution is strictly sequential. If a task fails verification, it is marked `failed`, but execution fixes forward and continues to the next task.

## 4. Finalize & Verification
At the end of execution, `execute` finalizes the `verification.md` file by injecting the project's build, test, and run commands, and building once.

```bash
# Handled automatically at the tail of the `execute` stage
```
**Completion Gate Evaluation (5-A/B/C)**:
- **5-A**: Validates the Paysafe constraint (no `com.paysafe.*` dependency downgraded).
- **5-B**: Enforces that there are no `pending` or `failed` tasks. Any task marked `needs-review` MUST have an explicit human sign-off line in the file. If missing, the gate fails. Add the sign-off to `tasks.md` and re-run verification. Example format: `**Sign-off**: [@username] [2026-07-07] — Reviewed and confirmed safe to proceed.`
- **5-C**: Checks if all Relevance-Index entries were resolved.

## Resuming Work
The state is entirely maintained in the markdown files. There is no session state in the Neo4j graph.
To resume a migration:
1. Re-read the `ps-migration/` folder.
2. Check `git status` for any uncommitted progress.
3. Relaunch the specific stage (`execute` will pick up from the first `pending` task).

*Note*: If `execute` determines that `plan.md`'s `Generated` date is older than 7 days, it will suggest re-planning (a staleness warning is surfaced), but it will never auto-replan.
