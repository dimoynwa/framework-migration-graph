# Rollback Procedure

Bundled as `references/rollback.md` under the `framework-migration-execute` skill bundle.
Load it during the execute stage when a build fails after a migration step and you need to
revert the change safely.

---

## 5-Step Revert Procedure

### Step 1 — IDENTIFY

Confirm which migration step caused the build failure. Note the `step_id` and the exact error from the build output.

### Step 2 — STASH

Stash all uncommitted changes introduced by the failed step:

```bash
git stash push -m "rollback: failed migration step <step_id>"
```

Verify the stash was created:

```bash
git stash list
```

### Step 3 — VERIFY

Run the build and tests to confirm the project is back to a passing state:

```bash
./mvnw verify   # Spring Boot
# or
npm test        # Angular
```

If the build still fails, a prior step may also be involved — escalate to the user.

### Step 4 — DECIDE

Choose one of the following options:

**Option A — Skip and continue:** Mark the step as skipped and proceed with the remaining queue.

```
Call: update_step_status(context_id, step_id, outcome="skipped", reason="build failed: <error>")
```

**Option B — Retry with a fix:** Apply a corrected version of the step manually, then mark completed.

```
Call: update_step_status(context_id, step_id, outcome="completed", reason="manual fix applied")
```

**Option C — Abandon session:** End the session and leave the context for a future attempt.

```
Call: close_migration_context(context_id, final_status="abandoned", notes="build failed on step <step_id>: <error>")
```

### Step 5 — RECORD

Whichever option you chose in Step 4, always record the outcome:

```
Call: update_step_status(context_id, step_id, outcome="failed", reason="build failed: <error>")
```

(Skip Step 5 if you already called `update_step_status` in Option A or B above.)
