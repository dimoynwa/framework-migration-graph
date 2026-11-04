# Rollback Procedure

Bundled as `references/rollback.md` under the `framework-migration-execute` skill bundle.
Load it during the execute stage when a build fails after a migration step and you need to
revert the change safely.

---

## 5-Step Revert Procedure

### Step 1 — IDENTIFY

Confirm which task caused the build failure. Note the TASK-ID and the exact error from the build output.

### Step 2 — STASH

Stash all uncommitted changes introduced by the failed task:

```bash
git stash push -m "rollback: failed migration task TASK-NNN"
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

If the build still fails, a prior task may also be involved — escalate to the user.

### Step 4 — DECIDE

Choose one of the following options:

**Option A — Mark failed and continue:** Set Status to failed in tasks.md and proceed with the remaining queue.

```
Edit tasks.md: **Status**: failed
Add reason inline: **Failure**: build failed: {error}
```

**Option B — Retry with a fix:** Apply a corrected version of the task manually, then mark done.

```
Edit tasks.md: **Status**: done
```

**Option C — Pause migration:** Stop execution and leave tasks.md for a future attempt.

### Step 5 — RECORD

Whichever option you chose in Step 4, ensure tasks.md reflects the outcome:

```
Edit tasks.md: **Status**: failed (or done for Option B)
```

(Skip Step 5 if you already updated Status in Option A or B above.)
