# Verification: {FRAMEWORK} {FROM} to {TO}
Run:   after all tasks.md tasks are done, before archiving the migration folder.
Order: Level 0 to 5 in sequence. Stop and fix on first failure.

## Prerequisites
- [ ] Runtime gate satisfied (Java version from plan.md)
- [ ] Build tool reachable; test DB/services up (for integration levels)

### Level 0 - Static residue (no build)
Each TASK's per-task verifier, plus a global sweep that no removed symbol survives:
  $ ! grep -rq "{removed-api}" src/    # PASS: no removed API remains
  $ ! grep -rq "{removed-namespace}" src/  # PASS: namespace migration complete

### Level 1 - Clean build
  $ {build command}                                   # PASS: exit 0

### Level 2 - Unit tests
  $ {unit test command}                               # PASS: exit 0

### Level 3 - Integration tests
  $ {integration test command}                        # PASS: exit 0

### Level 4 - App starts
  $ {run command} &  sleep {n}
  $ curl -fsS localhost:{port}/actuator/health        # PASS: UP

### Level 5 - Constraints and provenance
- [ ] Paysafe constraint held (Gate 5-A):
      $ git diff {base} -- '**/pom.xml' | grep -i com.paysafe
      shows no version change to any com.paysafe.* dependency
- [ ] Every tasks.md task is done (Gate 5-B):
      zero pending/failed; needs-review tasks have explicit sign-off
- [ ] Every Relevance-Index entry resolved (Gate 5-C):
      promoted, dismissed-with-reason, or logged to backlog

## Completion gate
  0-A  No removed API symbols remain      [ ]
  1-A  Clean build                        [ ]
  2-A  Unit tests pass                    [ ]
  3-A  Integration tests pass             [ ]
  4-A  App starts / health UP             [ ]
  5-A  Paysafe constraint held            [ ]
  5-B  No pending/failed tasks            [ ]
  5-C  Relevance index resolved           [ ]
All ticked -> migration complete. Archive or remove the ps-migration/ folder and commit.
