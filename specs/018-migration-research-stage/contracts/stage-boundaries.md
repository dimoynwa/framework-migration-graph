# Stage Boundaries and Contracts

This document defines the strict integration boundary between the new `/migration-research` stage and the amended `/migration-plan` stage.

## 1. Boundary Interface: `research.md`

The **ONLY** communication mechanism between Research and Plan is the `research.md` artifact.
- **Write Contract**: `/migration-research` MUST write a single, complete `research.md` file capturing all query knowledge to `ps-migration/{framework}-{from}-to-{to}/research.md`. It MUST overwrite existing files without error.
- **Read Contract**: `/migration-plan` MUST read `research.md` during its Step 1.5 Detection phase. The `/migration-gap-check` stage MAY read `research.md`'s header metadata block (fields: Generated, Truncated) for provenance verification. It MUST NOT parse sections below the header (Rule Results, Dependency Resolutions, Recipe Plan). No other stage (`clarify`, `preview`, `execute`) is permitted to read or parse `research.md`.

## 2. Plan Stage Detection Logic (Step 1.5)

`/migration-plan` implements the following validation rules at the boundary. The skip logic applies **ONLY** to Steps 3 and 4 (Version map and Knowledge queries). The codebase scan (Step 2) is NEVER skipped.

| Condition | Action |
|-----------|--------|
| `research.md` is absent | Run full pipeline (inline queries) |
| `research.md` fails parsing | Warn operator, run full pipeline |
| `From`/`To` versions mismatch | Warn operator, run full pipeline |
| Artifact age > 7 days | Warn operator, proceed with research artifact (operator decides) |
| Scan checksum mismatches | Warn operator, proceed with research artifact (operator decides) |
| File valid and accepted | Skip Steps 3–4 (version-map load and knowledge queries) |

**Invariant**: The codebase scan (Step 2) in the Plan stage MUST run *before* the detection logic processes the checksum mismatch, to generate the current checksum.

## 3. Data Equivalence Guarantee

The `/migration-plan` stage MUST guarantee that rendering from a valid `research.md` produces `plan.md`, `tasks.md`, and `verification.md` outputs that are functionally identical to running the inline knowledge queries, except for the addition of the `Research:` and `Research-generated:` provenance headers in `plan.md`.

No transformations or filtering of rule results may occur during the transition from `research.md` to the render classification table that would differ from the full inline knowledge-query pipeline (all tools in Steps 0–4).

## 4. Checksum Algorithm Guarantee

The checksum computed in `research.md` AND `plan.md` Step 2 must be exact.
- **Algorithm**: SHA-256
- **Input Format**: Sorted (lexicographically), deduplicated, newline-joined list of ALL scanned entity names across all 5 extraction types (FQCNs, annotations, properties, dependencies, npm packages). Encoding MUST be UTF-8.
