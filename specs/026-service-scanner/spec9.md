# Feature Specification 026.9: Incremental Cache, Parallel Parsing, Packaging

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Draft

**Depends on**: spec1–spec8 (all extractors in place; the cache stores their per-file facts).
Shared context: see `spec1.md`.

**Scope**: make warm re-scans fast, parse in parallel, split the install extras, finish docs.
No new facts in the profile.

## Requirements

### FR-10 Incremental scan

- `.migration/scan-cache.json` stores per file `(size, mtime_ns, sha256, extracted facts)`.
- A re-scan parses only files whose `(size, mtime_ns)` changed, and whose content hash then
  differs. Manifests are always re-read (they are few). Post-passes (barrels, own packages) run
  every time on the cached + fresh per-file facts.
- When `inputs_hash` is unchanged, the profile is not rewritten and stdout says `unchanged`.
  `inputs_hash` already includes the output-changing options (spec1 FR-9), so changing
  `--max-locations`, `--include-tests` or `--no-values` always rewrites the profile.
- `--force` ignores the cache. A different scanner version invalidates it.
- The cache is written atomically; a corrupt cache → diagnostic, full scan.

### Parallel parsing

- Parsing files is independent, so it runs in a process pool (`--jobs N`, default CPU count;
  `--jobs 1` runs in-process). Barrel resolution and other post-passes run after, on the
  collected facts. Output is identical for any `--jobs` value.

### Packaging

- The planner must install in a service repo without Neo4j, LangChain or the model clients.
  Extra `pip install paysafe-migration[planner]` pulls only `tree-sitter*`, `pyyaml` and
  `pydantic`; the ingestion dependencies move to an `[ingest]` extra. The AC-10 import guard
  (spec1) stays.

### Docs

- Finish the scanner page in `docs/` (all sections, cache, `--jobs`, install with
  `[planner]`), `CHANGELOG.md`.

## Acceptance Criteria

- **AC-9b Incremental**: re-scan with no change → `unchanged`, no file parsed. One edited file
  → only that file parsed, profile equal to a `--force` scan. Scanner version bump → full scan.
  Corrupt cache → full scan + diagnostic.
- **AC-9c**: `--jobs 1` and `--jobs 8` → byte-identical profiles (except `generated.at`).
- **AC-10b Packaging**: in a fresh venv, `pip install .[planner]` → `migration-scan` runs on a
  fixture; `neo4j` and `langchain*` are not installed.
- **AC-11 (timings)** on the two services from spec5 / spec8: < 30 s cold, < 3 s warm (no
  changes) on a laptop. Results appended to `ac11-angular.md` / `ac11-spring.md`.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec8 in the default order) must still pass unchanged; a failing earlier test is a regression, not an outdated test.

## How to test after spec9

```bash
time migration-scan /path/to/service --force   # cold
time migration-scan /path/to/service           # → "unchanged", < 3 s
touch-and-edit one file; migration-scan /path/to/service   # only one file parsed
```

## Implementation Notes

- Module: `migration_planner/scanner/cache.py`; `--jobs` wiring in `cli.py`.

## Estimate

~4 h: cache and determinism 2 h; process pool 0.5 h; packaging extras 0.5 h; timings and docs 1 h.
