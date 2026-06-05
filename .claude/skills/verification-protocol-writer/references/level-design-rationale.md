# Level Design Rationale

This reference explains *why* each level in the verification protocol is structured the way it is,
and how each level maps to specific tasks.md entries and reference document concerns.
Read this when you need to decide what goes in a level for a spec that doesn't fit the pipeline pattern.

---

## Why eight levels in this order?

The ordering is based on **cost of infrastructure × cost of diagnosis**.

| Level | Infrastructure cost | Diagnosis speed | What it catches |
|-------|-------------------|-----------------|----------------|
| 0 | Zero | Instant | Wrong/missing modules, incorrect constant values |
| 1 | Zero | Instant | CLI interface contract violations |
| 2 | File system only | Fast | Cache logic, flag interaction bugs |
| 3 | DB only | Fast | Driver config, query shape errors |
| 4 | DB + LLM | Slow | LLM pipeline, artifact schema validity, dry-run isolation |
| 5 | DB + LLM | Slow | Graph write correctness, enum validity, deprecated field absence |
| 6 | DB + LLM | Slow | Idempotency — the hardest class of bug to find by inspection |
| 7 | Varies | Fast-medium | Flag combination edge cases |

If a Level 0 check fails (bad import), there is no value in running Levels 3–6 — they will
all fail for the same reason and produce noise. The "stop on first failure" instruction
exists for this reason.

---

## Level 0 — Static checks

**Why sub-checks for constants?**
A dict with a missing key fails silently at runtime — `SOURCE_SECTION_TO_RULE_TYPE['security_fix']`
raising `KeyError` appears as a population failure, not a constant error. Checking the key set
explicitly at Level 0 catches this before a single LLM call is made.

**Why check both key completeness AND value correctness?**
These are two independent failure modes:
- Key completeness fails when a developer adds a new `source_section` value without updating the dict
- Value correctness fails when the dict exists but maps to the wrong `ruleType` string

A check that only asserts `len(dict) == 7` misses the second failure mode.

**Why check config constants here?**
If `EXTRACTION_RATE_LIMIT_RETRIES` is missing from `config.py`, the retry logic will `AttributeError`
at runtime — after the first LLM call has already been made and potentially billable time spent.
Catching it at Level 0 costs nothing.

---

## Level 1 — Interface structure

**Why check the help text manually (not programmatically)?**
The help text check is intentionally a visual inspection, not a grep. The goal is to confirm that
each flag is described correctly and has the right argument format, not just that the string appears
somewhere in the output. A programmatic grep would pass even if `--force-extract` was described as
`--force-llm` in the help text.

**Why include an `unknown input → non-zero exit` check?**
This verifies that the CLI's registry lookup is wired correctly. A missing `sys.exit(1)` call or
an unhandled `KeyError` turns a clean error path into a Python traceback, which is:
- Confusing to operators
- Untested by the import checks at Level 0
- Often introduced when the registry is added late in implementation

**Why check missing `MODEL_PROVIDER` separately from missing credentials?**
`MODEL_PROVIDER` controls which provider class is instantiated. If it's missing, the failure
happens at `get_llm()` call time, which may be deep inside `filters.py`. A clean error message
here requires a guard in `cli.py` or `config.py` — not inside the LLM factory. This check
verifies that guard exists.

---

## Level 2 — Isolation behaviour

**Why test the stale-artifact warning without a live LLM?**
The warning logic is in `cli.py` / `filters.py` and runs before any LLM call. Testing it with
a live LLM conflates two independent concerns: "does the warning fire?" and "does the LLM call
succeed?". If the warning test requires a live LLM call, a credential failure will mask a
warning logic bug.

**Why assert both warning text AND exit code 0 in the same check?**
These two invariants are always coupled. A warning that causes an `sys.exit(1)` would catch
real problems but violates the spec's stated behaviour (FR-008: "warn and continue"). Testing
both together prevents silent changes to the exit behaviour.

**Why use `stat` mtime for cache reuse, not a flag or log line?**
The mtime check is the only externally observable signal that the cache was actually used, as
opposed to the file being rewritten with identical content. A log line saying "using cache" is
easy to add without implementing the actual cache. An unchanged mtime cannot be faked.

**Why defer the mtime check to after Level 4?**
The mtime check requires real artifacts with real content. Seeded dummy files (used in Level 2
for the warning check) have unpredictable mtime behaviour depending on filesystem resolution.
Running the mtime check after Level 4 has produced real artifacts via the LLM ensures the check
is testing actual cache logic, not filesystem timestamp granularity.

---

## Level 3 — Graph connection (read path)

**Why include a write-then-read-then-delete round-trip?**
The `upsert_version_artifact_paths` function involves a MERGE followed by a SET — a pattern
that is easy to implement incorrectly (e.g. using `ON CREATE SET` when `ON MATCH SET` is also
needed, or vice versa). Testing it with a synthetic record and reading back all three paths
plus `sortableVersion` catches all four failure modes of MERGE + SET at Level 3, before a full
LLM run is needed.

**Why check `sortableVersion` specifically?**
`sortableVersion = major × 1_000_000 + minor × 1_000 + patch` uses a specific multiplier that
differs from some legacy code in the reference documents (which used `100_000`). A numeric
assertion at Level 3 catches the wrong multiplier immediately rather than silently producing
incorrect version range query results.

**Why mandate cleanup at the end of Level 3?**
Level 3 creates real nodes in a potentially shared or persistent database. Without cleanup,
a Level 7 check for `version_exists('spring-boot', '3.4.0')` returning `False` will fail
because the Level 3 write-then-read test left a node behind. Cleanup is required, not optional.

---

## Level 4 — Dry-run

**Why parse the entities JSON against the Pydantic model, not just `json.load()`?**
`json.load()` succeeds on any valid JSON. The spec requires a valid `MigrationEntitiesBatch` —
a Pydantic model with required fields and typed sub-models. A file containing `{"entities": []}`
is valid JSON but fails the Pydantic check. Parsing against the model also catches the case where
the LLM returned the old legacy schema (flat `affected_classes` etc.) instead of the redesigned
schema.

**Why assert `len(batch.entities) > 0`?**
FR-012 and the empty-entity validation task (TASK-GAP-005 from the review) both require that
an empty entity list is treated as a pipeline failure. But with `--dry-run`, the pipeline should
not abort — it should still write the (empty) JSON artifact. Asserting at least one entity here
verifies that the seeded fixture was realistic enough to produce non-trivial LLM output.

**Why check that the Version node does NOT exist after dry-run?**
This is the only way to verify that `--dry-run` is correctly wired through the entire call stack,
not just blocking the `populator.py` entry point. If a populator sub-function bypasses the
dry-run guard, the Version node will be created and this assertion will fail.

---

## Level 5 — Full graph write

**Why check enum validity by iterating over all returned values?**
A Cypher `WHERE r.ruleType = 'breaking'` query passes even if 90% of rules have invalid
`ruleType` values. Collecting all values and asserting each is in the valid set catches
the case where `SOURCE_SECTION_TO_RULE_TYPE` maps to an incorrect string.

**Why check the absence of deprecated fields (`actionStep`)?**
The redesign explicitly deprecates `actionStep` on new `MigrationRule` nodes. An absence check
ensures that `populator.py` is not silently writing this field — which could happen if the
implementation copies from an older reference and doesn't notice the deprecation note.

**Why use `OPTIONAL MATCH` in the step/scope count queries?**
Level 5 is run against freshly written data from a small seeded fixture. The LLM may classify
all two records as "informational" (no steps, no scope entries). Using `OPTIONAL MATCH` means
the query succeeds and returns zeros rather than failing. The Level 5 step count check is a
structural correctness check (the query runs without error, all returned counts are non-negative),
not a specific count assertion.

---

## Level 6 — Idempotency

**Why check edge counts separately from node counts?**
Nodes use `MERGE` on a unique key property, so duplicate nodes are rarely created even with a
broken idempotency implementation. Edges are the common failure point: `MERGE (a)-[:REL]->(b)`
without the right relationship key properties creates a new edge on every run. This is invisible
to a node-count-only check.

**Why save before-counts to a file rather than a variable?**
The second pipeline run (`--force-llm`) spawns a subprocess that may take 30–120 seconds. Any
in-memory Python variable from before the run is lost after the subprocess exits. Saving to
`/tmp/<spec>_counts_before.json` ensures the before-state is available for comparison regardless
of shell session or process boundaries.

**Why use `count(DISTINCT ...)` for node counts?**
Cypher's `count()` with `OPTIONAL MATCH` can return inflated counts when patterns fan out.
`count(DISTINCT r)` returns the true node count regardless of how many paths lead to each node
through the `OPTIONAL MATCH` chains.

---

## Level 7 — Edge-case paths

**Why test three sub-cases for multi-condition guards?**
A guard like `--skip-existing` that requires ALL of N conditions implements an AND. The most
common implementation mistake is checking N−1 conditions correctly and omitting one. Testing
all N "one condition absent" variants catches this class of bug.

For a 3-condition AND, that means:
- (A) All present → guard fires
- (B) Condition 1 absent → guard does not fire
- (C) Condition 2 absent → guard does not fire
- (implicitly, the symmetry argument covers condition 3)

Testing only the happy path misses partial implementation bugs entirely.

**Why restore deleted files/nodes before the next sub-check?**
Sub-checks within Level 7 are designed to be run in sequence by a developer who may not re-run
from the top if one check fails. If sub-check (B) deletes a file and sub-check (C) expects it
to exist, a failure in (C) could be caused by the missing file rather than a bug. Restoration
between sub-checks makes each sub-check independently reproducible.

---

## Adapting the protocol for non-pipeline specs

Not every spec has an LLM call, a graph database, or artifact caching. Here is how to adapt:

| Missing concern | Drop or replace |
|-----------------|----------------|
| No LLM calls | Skip Level 4 entirely; Level 5 becomes "full integration run" |
| No graph database | Drop Level 3, 5, 6; replace with appropriate data store checks |
| No artifact caching | Drop Level 2 except warning/flag checks if those exist |
| No CLI | Replace Level 1 with API surface checks (endpoint shape, required params, error responses) |
| No idempotency requirement | Drop Level 6 (but check if the spec's SC-* criteria mention it first) |
| No multi-condition guards | Drop Level 7 or replace with other error-mode checks |

The level numbering stays the same — gaps are fine. Never renumber to fill gaps.
