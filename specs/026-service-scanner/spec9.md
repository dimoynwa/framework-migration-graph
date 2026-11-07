# Feature Specification 026.9: Incremental Cache, Parallel Parsing, Packaging

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Implemented (2026-11-07). AC-9b, AC-9c, AC-10b and the AC-11 timings are met; the
timing results are in `ac11-spring.md` / `ac11-angular.md`.

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

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec8 in the default order) must still pass. A failing earlier test that checks **behavior** is a regression, not an outdated test. A test that pins an internal detail (the exact contents of a registry, a private helper's shape) may be changed deliberately when this spec extends that detail; such a change is named in the spec's CHANGELOG entry.

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

## Review fixes (2026-11-07)

The implementation record below is the first version; these changed after verification:

1. **Dead worker → hang.** `multiprocessing.Pool` waits forever for a task whose worker died (a
   native crash, `os._exit`); verified with an extractor that kills its worker. Now
   `concurrent.futures.ProcessPoolExecutor`: the batches that did not return are re-parsed one
   file per process, and the file that kills its worker again is an `extractor_crash` diagnostic,
   no facts, not cached. A parser that loops forever is still not guarded against.
2. **Stale `cache_corrupt`.** It went into the profile, and the next scans were `unchanged`, so the
   profile kept it forever (even `--force` did not clear it) while the summary said
   `0 diagnostics`. A cache problem is about the run: `ScanResult.run_diagnostics`, stderr
   (`warning: cache_corrupt: …`) and `--json-summary` `run_diagnostics`; never the profile.
3. **`--force` always rewrites the profile.** The record below defended "`--force` still reports
   `unchanged`"; that left no way to regenerate a profile that is stale for a reason
   `inputs_hash` cannot see.
4. **`fork` on Linux only.** The record said macOS gets `spawn`, but the code chose `fork` wherever
   it was offered, macOS included. Cold timings with `spawn` are in `ac11-*.md`.
5. **Package name.** The docs said `paysafe-migration-oracle[planner]`; the distribution is
   `migration-oracle` (this spec's `paysafe-migration` is the same package).
6. `pyproject.toml` comments corrected (`default-extras` does not exist; `--no-dev` drops the dev
   group, hence the Dockerfile's `--extra ingest`).
7. **Cache per root**: `scan-cache-<root digest>.json` for an `--out` outside the repo, and the root
   recorded in the cache (`CACHE_SCHEMA` 2).
8. **Racy stat**: a file modified within 2 s of the caching scan's start is re-hashed.
9. **`--jobs` default** = usable CPUs (`os.process_cpu_count()` / affinity mask).
10. `environment_digest` over every `ModuleEnv` field; `mypy` clean for the four modules; the unused
    test import removed. Counts: `tests/scanner` **689 passed**; with `test_shared_keys.py` and
    `test_canonical_*.py` **763 passed, 0 skipped**.

## Implementation record (2026-11-07)

### The cache (`migration_planner/scanner/cache.py`)

- **What is stored, per source file**: `size`, `mtime_ns`, `sha256`, the extractor's per-file
  facts, and two cache keys the spec does not name but the requirement implies — the **module
  environment digest** and the **extractor identity**.
- **The environment digest is not optional.** A source's facts also depend on what the manifest
  readers learned about its module (own package names, the effective tsconfig path map, declared
  and owned groupIds, detected frameworks), and none of that is in the file's bytes. Without it,
  editing a `package.json` would leave cached facts a fresh parse would not produce — an
  incremental profile that differs from a `--force` one, which AC-9b forbids. `ModuleEnv` is
  digested field by field (sorted, JSON, sha256).
- **The extractor identity** matters because one language tag can be served by a different
  extractor (a caller registering its own, a later spec swapping a parser). The entry names
  `module.qualname` of the extractor that produced the facts.
- **The cache lives next to the profile**, not always under the scan root. With the default
  `--out` that is `<root>/.migration/scan-cache.json`, exactly as the spec says; with `--out
  /tmp/x/profile.json` it is `/tmp/x/scan-cache.json`, which is how the AC-11 runs leave the
  service work tree untouched. Writing into the scanned repo when the caller asked for output
  elsewhere would be a surprise.
- **Facts are stored without a per-fact file path.** An extractor only reports facts about the
  file it was given, so the path is restored from the entry key on load. That halved the cache on
  the Spring service (14 MB → 6.6 MB for 1 448 Java files).
- **Atomic writes** reuse a new `profile.atomic_write_text` (the profile writer's body, extracted),
  so a crashed scan cannot leave a half-written cache and a crashed cache read is not possible
  without a corrupt file to begin with.
- **Invalidations**: a scanner or `CACHE_SCHEMA` mismatch drops the cache silently (it is our own
  file, and a version bump is a deliberate act); an unreadable or unparsable cache is one
  `cache_corrupt` diagnostic and a full scan; a file whose stat did not move is not read; a
  file whose stat moved but whose hash did not keeps its facts; a file whose extractor raised is
  **not** cached, so the next scan retries it.
- **`--force` still reports `unchanged`** when the inputs did not change: `unchanged` is about
  the *inputs* in `inputs_hash`, while `--force` is about the *cache*. Both are true at once, and
  the profile is correctly not rewritten. (A test pins this; it is the case a reader is most
  likely to find surprising.)

### `inputs_hash` over stored digests

`inputs_hash` was computed from file **contents**, which a warm scan no longer reads. A new
`inputs_hash_from_digests` takes `(path, sha256)` pairs instead, and the scan feeds it the stored
digest for every cached file. The hash is therefore byte-identical to a full scan's, which is what
makes "warm equals forced" true rather than approximately true. `inputs_hash` itself is now a thin
wrapper over it, so the 025 tests and every caller are unchanged.

### Parallel parsing (`migration_planner/scanner/parallel.py`)

- The parent does discovery, manifest reading, hashing and cache decisions; a worker only runs
  extractors. That split is why a warm scan never starts a pool.
- Results cross the process boundary in the **cache's own JSON encoding**, not as pickled pydantic
  models: one code path to test, and the parent can write them straight into the cache.
- `MIN_FILES_FOR_POOL = 32`: starting a pool costs tens of ms per process, so a small repo (and
  every fixture) parses in-process even with the default `--jobs`. The output is the same either
  way, which the AC-9c test proves on a repo above the threshold.
- **`fork` where available, `spawn` where not.** `fork` start-up is nearly free on Linux; macOS
  and Windows get `spawn`, which imports the package per worker — fine, because every shipped
  extractor is a module-level function. A pool that cannot start at all (sandbox, an unpicklable
  registry) is caught and the same files are parsed in-process: a slower scan, never a failed one.
- Results are keyed by path and merged in discovery order; post-passes sort their own output. No
  list in the profile depends on the order facts arrive in, which is what AC-9c checks.

### Packaging

- Base dependencies are now the scanner's: `pydantic`, `pyyaml`, `tree-sitter*`. The same list is
  `[planner]`; ingestion (Neo4j, LangChain, embeddings, MCP, Streamlit, `httpx`, `structlog`,
  `tqdm`, `packaging`, `rapidfuzz`, `anyio`, `beautifulsoup4`, `click`) is `[ingest]`.
- **`uv` cannot express "install this extra by default"**, so the dev group depends on
  `migration-oracle[ingest]`: `uv sync` and the Dockerfile's `uv sync --frozen --no-dev --extra
  ingest` keep the full stack. The Dockerfile needed the explicit `--extra ingest`.
- AC-10b was verified for real: wheel → fresh `uv venv` → `uv pip install '<wheel>[planner]'` →
  11 packages, `migration-scan` runs on `tests/fixtures/scanner/angular-app`, and `neo4j`,
  `langchain`, `langchain_core`, `httpx`, `mcp`, `sentence_transformers`, `streamlit` all raise
  `ModuleNotFoundError`. `tests/scanner/test_packaging.py` automates it (skipped when a wheel
  cannot be built) and always asserts the dependency split from `pyproject.toml`.

### Decisions taken where the spec is silent

- **`--jobs` default is the CPU count only above the pool threshold**; below it, in-process. The
  spec says "default CPU count", which is about the *flag's* value — `--jobs` is still the CPU
  count — not about starting 12 processes for a 9-file fixture.
- **`use_cache=False`** on `scan()` disables the cache entirely instead of only skipping the read.
  A caller that asked for no cache does not want a 6 MB file written either.
- **Summary line** gains `(N parsed)` on a cold-with-some-hits scan and `unchanged` on a no-change
  scan; `--json-summary` carries `parsed_files` / `cached_files`. The spec's "stdout says
  `unchanged`" needs the first; the counts are how a user sees the cache working.
- **A cached file whose extractor now raises is replaced by the failure**, not by the old facts:
  the entry is not stored, the diagnostic is reported, and the next scan retries.

### Regression

`pytest tests/scanner` → **677 passed, 4 skipped** (the 4 are the native-git skips of this
sandbox). With the 025 suites that use `migration_keys/`
(`test_shared_keys.py`, `test_canonical_normalize.py`, `test_canonical_api_index.py`) → **734
passed, 4 skipped**. No earlier test needed changing: the two `Summary` fields and the three
`scan()` keyword arguments are additive, and `inputs_hash` keeps its signature and its value for
the same inputs. One earlier test was **tightened**, not relaxed: `test_cli` now also asserts the
`.gitignore` hint is silent when `--out` points outside the repo.

`tests/mcp/test_upgrade.py` fails to **collect** (`build_recipe_plan` is not exported from
`migration_oracle.mcp.tools.upgrade`). It does so with this work stashed too, so it predates
spec9 and is unrelated to the scanner.

### Estimate vs actual

~4 h estimated. Actual ≈ 4 h: cache and determinism 2 h (the environment digest and the
`inputs_hash`-from-digests change were most of it), process pool 0.5 h, packaging 0.5 h (plus the
Dockerfile and the lock), timings and docs 1 h.
