# Tasks: Paysafe Resolver v2 — Startup Cache + Latest-Only Resolution

**Spec:** `013b-paysafe-resolver-v2`
**Prerequisite:** `003-paysafe-resolver` ✅

Tasks are ordered so each task's dependencies are complete before it begins.
`[P]` marks tasks that are safe to run in parallel with other `[P]` tasks in the same group.

---

## Group A — Foundation (must complete before all other groups)

### A-1 · Add env vars to `config.py`

**File:** `migration_oracle/config.py`

Add two new env var constants:

```python
FINDIT_CACHE_STRATEGY: str = os.getenv("FINDIT_CACHE_STRATEGY", "none")
# Valid values: "bulk", "paginated", "none"

FINDIT_CACHE_LOAD_TIMEOUT_SECONDS: float = float(
    os.getenv("FINDIT_CACHE_LOAD_TIMEOUT_SECONDS", "30")
)
```

No other changes to this file.

**Done when:** `from migration_oracle.config import FINDIT_CACHE_STRATEGY, FINDIT_CACHE_LOAD_TIMEOUT_SECONDS` imports without error.

---

### A-2 · Create `static_registry.json` [P]

**File:** `migration_oracle/paysafe/static_registry.json`

Create the committed static registry file. Populate it with all Paysafe internal services whose GitLab URLs are known. The file must be valid JSON and contain at least one entry — an empty `{}` is not acceptable for the initial commit (use it only in tests).

Format:
```json
{
  "service-name-a": "https://gitlab.paysafe.com/group/service-name-a",
  "service-name-b": "https://gitlab.paysafe.com/group/service-name-b"
}
```

**Rules:**
- Keys are canonical service name strings — what a developer would pass as `service_name` to the tool.
- Values are full GitLab HTTPS URLs, no trailing slash.
- Keys must be unique (JSON parsers silently overwrite duplicates — avoid them).
- Alphabetical key order for readability and clean diffs.

**Done when:** `json.loads(Path("migration_oracle/paysafe/static_registry.json").read_text())` succeeds and returns a non-empty dict.

---

## Group B — Cache layer in `findit.py` (depends on A-1, A-2)

### B-1 · Add module-level cache dict and `_load_static_registry()`

**File:** `migration_oracle/paysafe/findit.py`

Add at the top of the module (after imports):

```python
_REPO_CACHE: dict[str, str] = {}
```

Add the private loader:

```python
def _load_static_registry() -> dict[str, str]:
    """Load static_registry.json. Raises FileNotFoundError or json.JSONDecodeError on failure."""
    path = Path(__file__).parent / "static_registry.json"
    return json.loads(path.read_text(encoding="utf-8"))
```

This function intentionally does not catch exceptions — callers handle them.

**Done when:** The function is importable and returns the correct dict when the file exists, and raises the correct exception types when the file is missing or malformed.

---

### B-2 · Implement FindIt loader functions (depends on B-1) [P]

**File:** `migration_oracle/paysafe/findit.py`

Add two private loader functions for the FindIt bulk strategies. Both return a `dict[str, str]` of `service_name → codeRepoLink`. Both are called inside `populate_cache()` only when the corresponding strategy is selected.

```python
def _load_findit_bulk() -> dict[str, str]:
    """Single GET /services call. Raises _FindItError on failure."""
    ...

def _load_findit_paginated() -> dict[str, str]:
    """Paginated GET /services?page=N loop. Raises _FindItError on failure."""
    ...
```

Implementation notes:
- Use the existing auth token from `os.environ["FINDIT_AUTH_TOKEN"]`.
- Return an empty dict `{}` if the endpoint returns an empty list (not an error).
- Raise `_FindItError` with `error_code="http_request_failed"` on non-2xx responses.
- Raise `_FindItError` with `error_code="http_timeout"` on request timeout.
- If the FindIt API shape is not yet confirmed, implement both as stubs that raise `NotImplementedError("FindIt bulk endpoint not yet confirmed — set FINDIT_CACHE_STRATEGY=none")`. Leave a `# TODO: implement once endpoint is confirmed` comment.

**Done when:** Both functions are importable. Stub implementations are acceptable; stubs must raise `NotImplementedError`, not silently return `{}`.

---

### B-3 · Implement `populate_cache()` (depends on B-1, B-2)

**File:** `migration_oracle/paysafe/findit.py`

```python
def populate_cache(timeout_seconds: float | None = None) -> None:
    """
    Build the two-layer repo-link cache. Always called once at server startup.

    Layer 1 (always): load static_registry.json into _REPO_CACHE.
    Layer 2 (optional): fetch from FindIt per FINDIT_CACHE_STRATEGY and merge in.
    FindIt entries overwrite static entries on key conflict.

    Raises if static_registry.json is missing or invalid JSON.
    Logs WARNING and continues if FindIt is unreachable or times out.
    """
```

Implementation sequence inside the function:
1. Call `_load_static_registry()`. Let any exception propagate — missing or broken static registry is a hard startup failure.
2. Normalise all keys from the static registry and write them into `_REPO_CACHE`.
3. Read `config.FINDIT_CACHE_STRATEGY`. If `"none"`, log `INFO "FINDIT_CACHE_STRATEGY=none; skipping FindIt merge"` and return.
4. Call the appropriate loader (`_load_findit_bulk` or `_load_findit_paginated`) inside a `concurrent.futures.ThreadPoolExecutor` with the configured timeout (from `config.FINDIT_CACHE_LOAD_TIMEOUT_SECONDS`).
5. On timeout: log `WARNING "FindIt cache load timed out after {N}s; using static registry only"`. Return without raising.
6. On `_FindItError` or any other exception from the loader: log `WARNING "FindIt cache load failed: {exc}; using static registry only"`. Return without raising.
7. Merge the FindIt results into `_REPO_CACHE`, normalising keys first. FindIt values overwrite existing static values.
8. Log `INFO "Cache populated: {N} static entries, {M} FindIt entries, {total} total"`.

**Done when:** All four scenarios work correctly — static only (strategy=none), FindIt merge success, FindIt timeout, FindIt error — verified by the tests in Group D.

---

### B-4 · Implement `get_repo_link()` with live fallback (depends on B-3)

**File:** `migration_oracle/paysafe/findit.py`

```python
def get_repo_link(service_name: str) -> str | None:
    """
    Look up a service's codeRepoLink.

    1. Check _REPO_CACHE (populated at startup from static registry + FindIt).
    2. On cache miss: call lookup() live (original slow path).
    3. On live hit: warm _REPO_CACHE for subsequent calls.
    4. Return None if neither source has a record.
    """
```

The live fallback warms the cache: `_REPO_CACHE[_normalise(service_name)] = link` before returning.

**Done when:** Cache hit skips `lookup()` entirely; cache miss calls `lookup()` exactly once and stores the result; a second call for the same service after a miss hits the cache.

---

## Group C — Resolver simplification (depends on B-4)

### C-1 · Replace FindIt per-call block with `get_repo_link()` in `resolver.py`

**File:** `migration_oracle/paysafe/resolver.py`

Replace the entire Step 3 block (the `ThreadPoolExecutor` wrapping `findit.lookup()`) with:

```python
# Step 3 (v2): cache lookup with per-call fallback
code_repo_link = findit.get_repo_link(service_name)
if not code_repo_link:
    return _build_error(
        "no_repo_url",
        f"No codeRepoLink found for {service_name!r} in cache or FindIt.",
        recoverable=False,
        actionable_hint=(
            "Check that the service is registered in FindIt or add it to "
            "migration_oracle/paysafe/static_registry.json."
        ),
        details={"service_name": service_name},
    )
```

Remove the `_FINDIT_TIMEOUT_SECONDS` constant and its associated `ThreadPoolExecutor` import if no longer used anywhere else.

**Done when:** `resolver.resolve("some-service")` no longer spawns a thread or calls `findit.lookup()` when the cache is warm.

---

### C-2 · Remove compatibility loop, return latest tag directly (depends on C-1)

**File:** `migration_oracle/paysafe/resolver.py`

Replace the entire compatibility scanning block (Steps 5–7 in the current code — the `deadline` / `compatible_tags` / `unknown_tags` loop) with:

```python
# Step 5 (v2): list tags, return the first (latest) one
tags = gitlab.list_tags(code_repo_link, max_tags=1)
best_tag = tags[0]

result_kwargs = dict(
    status="ok",
    service_name=service_name,
    selected_tag=best_tag,
    selected_version=_parse_selected_version(best_tag),
    framework=framework,
    framework_version=None,          # no longer fetched — see resolver v2 spec
    selection_strategy="latest_overall",
    target_version=target_version,
    code_repo_link=code_repo_link,
    compatibility=None,              # no longer checked — see resolver v2 spec
    effective_settings=_build_effective_settings(max_tags),
)
if name_resolution is not None:
    result_kwargs["name_resolution"] = name_resolution
return _build_result(**result_kwargs)
```

Remove the `_TAG_SCAN_BUDGET_SECONDS` constant. Remove the `CompatibilityInfoObj` import if it is no longer used.

**Deprecation comments (do not delete the functions):** Add `# unreachable in resolver v2 — retained for reference` above `_build_error("no_compatible_version", ...)` and `_build_error("compatibility_unknown", ...)` if they remain in the file.

**`allow_latest_overall` parameter:** Keep in the function signature. Add a log line:
```python
if allow_latest_overall is False:
    import logging
    logging.getLogger(__name__).warning(
        "allow_latest_overall=False is ignored in resolver v2; latest_overall is always returned."
    )
```

**Done when:** `resolver.resolve("any-service")` never calls `gitlab.fetch_framework_version()` on any code path. `selected_version` is always the first tag. `selection_strategy` is always `"latest_overall"`.

---

## Group D — Tests (depends on B-3, B-4, C-1, C-2) [P]

**File:** `tests/mcp/test_paysafe_resolver_v2.py`

All tests use `unittest.mock` (`patch`, `MagicMock`). No live network calls. Where `static_registry.json` content is needed, use `tmp_path` fixtures to write a temporary file and monkeypatch `Path(__file__).parent` or pass the path directly.

Implement all 19 tests from the spec's test table, grouped as follows:

**Cache population (6 tests):**
- `test_static_registry_loaded_on_startup`
- `test_static_registry_missing_raises`
- `test_static_registry_invalid_json_raises`
- `test_populate_cache_timeout`
- `test_server_starts_when_findit_unreachable`
- `test_findit_overwrites_static_on_conflict`

**Cache lookup (3 tests):**
- `test_static_entry_kept_when_findit_absent`
- `test_cache_hit_skips_findit_lookup`
- `test_cache_miss_falls_back_to_lookup`
- `test_cache_miss_fallback_warms_cache`

**Resolver behaviour (5 tests):**
- `test_returns_latest_tag`
- `test_selection_strategy_is_always_latest_overall`
- `test_compatibility_is_null`
- `test_framework_version_is_null`
- `test_target_version_ignored`

**Error paths (3 tests):**
- `test_pinned_version_still_works`
- `test_invalid_service_name`
- `test_no_repo_url_error`
- `test_no_tags_found_error`

**Existing test updates:**
- Find tests in the existing resolver test file that cover `no_compatible_version` and `compatibility_unknown` error codes.
- Update each to assert `NotImplementedError` or remove them, with a comment in the PR: `"removed: compatibility loop eliminated in resolver v2"`.

**Done when:** `pytest tests/mcp/test_paysafe_resolver_v2.py -v` passes all 19 tests with no live network calls.

---

## Group E — MCP server startup hook (depends on B-3)

### E-1 · Wire `populate_cache()` into the server lifespan

**File:** `migration_oracle/mcp/server.py`

Locate the lifespan context manager (or create one if absent). Add the cache population call:

```python
@contextlib.asynccontextmanager
async def lifespan(server):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, findit.populate_cache)
    except Exception as exc:
        # static_registry.json missing or invalid — hard fail with clear message
        logger.error("Failed to populate Paysafe resolver cache: %s", exc)
        raise
    yield
```

Note: `populate_cache()` only propagates exceptions from the static registry load. FindIt failures are caught inside the function and logged as warnings. The `try/except` here handles the rare case where `static_registry.json` is broken.

**Done when:** Starting the MCP server loads `static_registry.json` entries into `_REPO_CACHE` before the first tool call can arrive, and the server fails fast with a clear message if the static registry is broken.

---

## Group F — Documentation updates (depends on C-2) [P]

All three tasks in this group are independent of each other and can run in parallel.

### F-1 · Update `mcp-tools-skills-prompts.md` [P]

**File:** `mcp-tools-skills-prompts.md`

In the `resolve_paysafe_dependency_by_service_name` entry:

1. Mark `target_version`, `framework`, and `allow_latest_overall` parameters as **ignored in v2**. Update the description column for each.

2. Update the Returns table:

| Field | Change |
|---|---|
| `framework_version` | Change description to `Always null in v2` |
| `compatibility` | Change description to `Always null in v2` |
| `selection_strategy` | Change description to `Always "latest_overall" in v2` |

3. Add a `> **v2 behaviour:**` note block (exact text in spec.md § "Updated tool contract").

**Done when:** The entry accurately reflects that `target_version` is ignored, `compatibility` is always null, and `selection_strategy` is always `latest_overall`.

---

### F-2 · Update `framework_migration_main.md` [P]

**File:** `migration_oracle/mcp/skills/framework_migration_main.md`

Three targeted edits — do not reformat or rewrite surrounding sections:

1. **Tier table row** — remove `target_version` and `framework` from the Paysafe deps row. Add "Pass only `service_name`" and the `latest_overall` note (exact replacement text in spec.md § "Tier table row").

2. **Query loop decision table** — update the `com.paysafe` row to omit `target_version` from the call signature (exact replacement text in spec.md § "Query loop decision table").

3. **New note block** — insert the "Paysafe dep result interpretation (v2)" block immediately after the T039 fallback rows table (exact text in spec.md § "Result handling").

**Done when:** An agent reading this skill file will call `resolve_paysafe_dependency_by_service_name(service_name=<dep>)` with no other parameters, and will correctly interpret `compatibility=null` as expected behaviour rather than an error.

---

### F-3 · Update `migration_oracle/mcp/skills/framework_migration_main.md` [P]

**File:** `migration_oracle/mcp/skills/framework_migration_main.md`

Two targeted edits:

1. **Step 2c call site** — replace the three-argument call with `service_name`-only call. Add the unverified-compatibility prose note (exact text in spec.md § "Step 2c call site").

2. **Dependency output table** — add `Verified` column. Add `⚠️ unverified` on every Paysafe row. Add the warning note below the table (exact text in spec.md § "Dependency table in output").

**Done when:** An agent following this skill file will produce a dependency table with `⚠️ unverified` on Paysafe rows and the engineer-visible warning note beneath it.

---

## Group G — Full test suite (depends on D, E, F-1, F-2, F-3)

### G-1 · Run full test suite and fix any regressions

```bash
pytest tests/mcp/ -v
```

Expected: all pre-existing tests pass (with the compatibility-loop tests updated or removed per D), and all 19 new tests pass.

If pre-existing tests import symbols removed from `resolver.py` (e.g. `_TAG_SCAN_BUDGET_SECONDS`, `CompatibilityInfoObj`), update the imports in those test files.

**Done when:** `pytest tests/mcp/` exits 0 with no failures or errors.

---

## Dependency graph

```
A-1 ──────────────────────────────────────────► B-3
A-2 [P] ──────────────────────────────────────► B-1 ──► B-2 [P] ──► B-3 ──► B-4
                                                                              │
                                                                              ▼
                                                                          C-1 ──► C-2
                                                                              │
                                        ┌─────────────────────────────────────┤
                                        ▼                                     ▼
                                      D [P] ──────────────────────────────► G-1
                                      E   ──────────────────────────────► G-1
                                      F-1 [P] ────────────────────────► G-1
                                      F-2 [P] ────────────────────────► G-1
                                      F-3 [P] ────────────────────────► G-1
```