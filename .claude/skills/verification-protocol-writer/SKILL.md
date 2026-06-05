---
name: verification-protocol-writer
description: >
  Generates structured, runnable verification protocols for software feature implementations.
  Use this skill whenever a spec, feature branch, tasks.md, or implementation has been completed
  and needs a verification document — even if the user phrases it casually: "how do I verify this",
  "write me tests for the implementation", "create a smoke test script", "make a checklist for QA",
  "how do I know it works", "write verification steps", "completion gate for this spec".
  Also trigger when reviewing a tasks.md or spec.md and the user asks what comes after implementation.
  Produces a layered verification.md covering static checks, CLI/interface structure, integration
  layer-by-layer, idempotency, and edge-case paths — ordered so failures are caught as cheaply
  as possible, with a final completion gate checklist.
---

# Verification Protocol Writer

Produces a `verification.md` file that is the definitive runnable gate between
`/speckit.implement` completing and a spec being marked ✅ in `SPEC_ORGANIZATION.md`
(or equivalent completion tracking).

---

## What you need before starting

Read these inputs before writing a single line of the protocol:

1. **The spec** (`spec.md` or equivalent) — for acceptance criteria, success criteria (SC-*),
   and the list of required behaviours
2. **The tasks.md** — for the exact modules, functions, and constants that were implemented
3. **The design documents** (project knowledge) — for correctness constraints that the spec
   may not have fully captured (enum values, Cypher patterns, write-boundary rules)
4. **The `plan.md` contracts section** — for forbidden patterns and write-boundary rules that
   must be verified structurally, not just functionally

If any of these are missing, ask for them or search project knowledge before proceeding.

---

## The eight-level structure

Every verification protocol uses exactly this level sequence. Each level states its
infrastructure requirements at the top (no LLM / no DB / both required). Readers stop at the
first failure rather than running everything — state this explicitly in the protocol header.

| Level | Name | Infrastructure | Purpose |
|-------|------|----------------|---------|
| 0 | Static checks | None | Imports, constants, config values |
| 1 | Interface structure | None | CLI flags, error exits, help text |
| 2 | Isolation behaviour | None (or seeded files) | Cache logic, warning conditions, flag interactions |
| 3 | Integration — read path | DB only | Driver connects, read helpers return correct shapes |
| 4 | Integration — write path (safe) | DB + LLM | Dry-run: artifacts produced, nothing written to DB |
| 5 | Integration — write path (full) | DB + LLM | Full run: all nodes/edges written with correct properties |
| 6 | Idempotency | DB + LLM | Node + edge counts identical after second run |
| 7 | Edge-case paths | DB or None | Flag combinations, partial-condition guards, error modes |

Not all eight levels are always needed. Omit levels that have no content for this spec —
but never reorder or renumber the levels that remain.

---

## How to write each level

### Level 0 — Static checks

The fastest possible signal that implementation is complete and structurally correct.
No external services needed.

Include checks for:
- **Module imports** — every public module listed in `plan.md` must import without error
- **Named constants** — any dict/enum constant from the spec (e.g. `SOURCE_SECTION_TO_RULE_TYPE`)
  must have the exact set of keys defined in the reference documents. Check both key completeness
  and value correctness in separate sub-checks
- **Config constants** — any `EXTRACTION_*` or similar constants defined by the spec must
  be present in `config.py` with their default values

Each check must be a self-contained one-liner or inline Python block with an explicit
`print('PASS: ...')` so the reader knows what passed. Assertions must include the actual
value in the failure message: `assert x == 3, f'Got: {x}'`.

### Level 1 — Interface structure

Verifies the CLI (or API surface) without touching any external service.

Include checks for:
- **Help text** — list every required flag/argument by name; reader confirms visually
- **Unknown input rejection** — call with an invalid value; assert non-zero exit and
  human-readable error (not a traceback)
- **Missing required config** — unset a required env var; assert non-zero exit and
  clear message

### Level 2 — Isolation behaviour

Tests behaviours that can be exercised with pre-seeded fixture files, no live services.
This level is where cache logic, warning conditions, and flag interactions live.

For **warning conditions**: the check must assert both (a) warning text appears and
(b) exit code is still 0 — these two are always tested together.

For **cache reuse**: capture `stat` mtime before and after re-running; assert equality.
Use a cross-platform stat invocation:
```bash
stat -c %Y <file> 2>/dev/null || stat -f %m <file>
```

For **seeded fixtures**: include the exact `cat > ...` heredoc to create them.
Fixtures must be realistic enough to exercise the real code paths, not empty files.

### Level 3 — Integration read path

Database required, no LLM. Each check must clean up after itself — leave the database
in the state it was in before the level ran.

Include:
- Driver connectivity (`RETURN 1 AS n`)
- Each read query helper: call it with known-absent data; assert it returns the correct
  empty/false result
- Each write-then-read helper: write a synthetic record, read it back, assert all
  properties including any computed fields (e.g. `sortableVersion`), then delete it

Always include an explicit cleanup block at the end of Level 3.

### Level 4 — Dry-run (safe write path)

LLM + DB required, but no graph writes should happen.

Seed the raw input fixture (same format as Level 2 if reusing, or a new one).
Run with `--dry-run` (or equivalent safe flag). Then assert:
- Exit code 0
- All expected artifact files exist on disk
- Artifact content is structurally valid (parse it against the Pydantic model or schema)
- **No database write occurred** — query for the node that would have been created;
  assert it does not exist

End Level 4 with the mtime cache-reuse check from Level 2 (now run against real artifacts).

### Level 5 — Full write path

LLM + DB required. Run the full pipeline without dry-run.

Assert in this order:
1. Exit code 0
2. The primary node (e.g. `Version`) has all required properties written
3. All typed property values are from valid enum sets — iterate and assert each value
4. Any property that must NOT be written (deprecated or legacy fields) has zero instances
5. Child nodes created via `OPTIONAL MATCH`-compatible relationships exist with valid
   structure (but allow count to be 0 for informational-only input)

### Level 6 — Idempotency

Run the full write path a second time (`--force-llm` or equivalent), then compare
node and edge counts before and after.

**Critical**: check both node counts AND edge counts. The most common idempotency
failure is duplicate edges (nodes are deduplicated by MERGE, but edges without a
unique key property multiply). List every relationship type that the spec creates
and check its count.

Pattern:
```
capture counts → second run → capture counts → diff → assert diff is empty
```

Save the before-counts to `/tmp/<spec-name>_counts_before.json` and read them back
for comparison. Never rely on in-memory state across the re-run.

### Level 7 — Edge-case paths

Test the specific flag combinations and partial-condition guards from the spec.
For any guard that requires ALL of N conditions to be true, write three sub-checks:
- (A) All conditions met → expected skip/short-circuit behaviour
- (B) One condition absent (remove it) → pipeline proceeds normally
- (C) A different condition absent → pipeline proceeds normally

Always restore any files or nodes that were removed for a sub-check before the next one.

---

## Completion gate checklist

Every protocol ends with a single Markdown table listing every check ID (e.g. `0-A`,
`3-C`) with a one-line description and an empty `Result` column for the user to tick.

The table header must read: "Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when
every item below is checked."

Include every check from every level. Do not group or summarise — every row must be
individually verifiable.

---

## Writing style rules

**Fail fast, fail loud.** Every assertion message includes the actual value received.
Every sub-check ends with a `print('PASS: ...')` that is specific enough to distinguish
it from other passes in the same level.

**Self-contained blocks.** Each numbered sub-check must be copy-pasteable and runnable
without context from previous checks. Avoid `$VARIABLE` references across blocks unless
the variable is defined within the same script.

**Cross-platform stat.** Always write the mtime capture as:
```bash
stat -c %Y <file> 2>/dev/null || stat -f %m <file>
```

**Cleanup is mandatory.** Any node, file, or state created by a check must be deleted by
that check or by an explicit cleanup block at the end of the level.

**Fixture content matters.** Seeded fixtures must contain at least two records of
different types — enough for the LLM to produce non-trivial output. A single empty row
produces unpredictable results.

**Edge count ≠ node count.** The idempotency level must always include relationship
type counts, not just node label counts. Duplicate edge creation is invisible to
node-count-only checks.

**Levels are titled by function, not number.** Readers scan protocols under pressure.
The level header `## Level 3 — Graph connection` is more useful than `## Level 3`.

---

## What NOT to include

- Do not write pytest or unit test files. The protocol is a manual runbook of
  copy-pasteable commands, not a test suite.
- Do not generate fixture data programmatically — write the exact content as heredocs.
- Do not include performance tests or load tests unless the spec explicitly defines
  performance success criteria with numbers.
- Do not include checks that require human visual judgment with no pass/fail criterion
  (e.g. "verify the output looks reasonable"). Every check must have a machine-verifiable
  assertion or an explicit list of strings to grep for.
- Do not duplicate checks between levels. If a check belongs in Level 4, do not
  repeat it in Level 5.

---

## Output location and header

The file must be saved as `specs/<spec-id>-<spec-name>/verification.md`.

The header block at the top of the file must include:

```markdown
**Location**: `specs/<id>-<name>/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `<id>` ✅
**Execution order**: Levels 0 → N in sequence. Stop and fix on the first failure — failures compound.
```

Followed by a Prerequisites table listing: dependency manager sync, database reachability,
LLM credentials, and any writable directories the spec needs.

Then note which levels require LLM and DB and which require neither.

---

## Reference: mapping spec artefacts to protocol levels

| Spec artefact | Goes into level |
|---------------|----------------|
| Module imports listed in `plan.md` | Level 0-A |
| Named dict/enum constants | Level 0-B, 0-C |
| Config env var defaults | Level 0-D |
| CLI flags from spec FR-010 equivalent | Level 1-A |
| Invalid-input rejection | Level 1-B, 1-C |
| Stale-artifact / warning conditions | Level 2 |
| Cache reuse (mtime check) | Level 2-C (deferred to after Level 4) |
| Graph driver + read query helpers | Level 3 |
| Write helper round-trip with cleanup | Level 3-C, 3-D |
| Dry-run / safe-write path | Level 4 |
| Full graph write with property assertions | Level 5 |
| Deprecated-field absence checks | Level 5-F |
| Node + edge count idempotency | Level 6 |
| Multi-condition guard paths | Level 7 |

For details on how each level's checks map to specific tasks.md entries and
reference document sections, see `references/level-design-rationale.md`.
