# Spec: Paysafe Resolver v2 — Startup Cache + Latest-Only Resolution

**ID:** `013b-paysafe-resolver-v2`
**Prerequisite:** `003-paysafe-resolver` ✅ (the original resolver must exist and pass its tests)
**Status:** 🔲 Not started

---

## Problem statement

The current `resolve_paysafe_dependency_by_service_name` tool has two pain points:

1. **FindIt is slow on every call.** Each resolution calls `findit.lookup(service_name)` to
   convert a service name into a `codeRepoLink`. This is a synchronous network call that
   frequently times out or stalls Loop II of the migration harness.

2. **Compatibility checking is unreliable in practice.** The per-tag build-file scan
   (`fetch_framework_version` + `_is_compatible`) fetches `pom.xml` or `build.gradle` at every
   tag ref, looking for a compatible framework version. In practice, Paysafe internal libraries
   always target the current platform version, so the check rarely filters anything but adds
   substantial latency and network calls.

---

## Goals

1. **A static registry provides a baseline mapping** of known Paysafe services to their
   `codeRepoLink`, committed to the repo and always loaded first at startup. This makes the
   most common services resolvable with zero network calls.

2. **FindIt is called once**, at MCP server startup, and its results are merged on top of the
   static registry. FindIt wins on any key conflict — its data is considered more authoritative
   and up to date. Per-tool-call FindIt I/O is eliminated from the hot path.

3. **Resolution returns the latest tag**, always. Compatibility scanning is removed. The
   result is faster, simpler, and honest about what it does (`selection_strategy:
   "latest_overall"`).

4. **No MCP tool contract breakage.** The tool's input parameters and output shape are
   unchanged. Fields that can no longer be populated (`framework_version`, `compatibility`)
   return `null`.

---

## Non-goals

- Refreshing the FindIt cache at runtime (e.g. on a TTL). Out of scope for this spec.
- Deleting deprecated functions from `gitlab.py`. A separate cleanup spec handles that.
- Changing any other MCP tool.
- Caching GitLab tag lists between calls (a future optimisation).

---

## Files changed

```
migration_oracle/
└── paysafe/
    ├── findit.py                          # Add populate_cache(), merge logic, cache dict
    ├── resolver.py                        # Remove compatibility loop; use cache for codeRepoLink lookup
    └── static_registry.json              # NEW — committed static service → codeRepoLink map
migration_oracle/
└── mcp/
    ├── server.py                          # Call findit.populate_cache() in lifespan startup hook
    └── skills/
        └── framework_migration_main.md   # Update call site + result interpretation
migration_oracle/
└── config.py                             # Add FINDIT_CACHE_LOAD_TIMEOUT_SECONDS env var
skills/user/framework-migration/
└── SKILL.md                              # Update Step 2c call site + dependency table wording
tests/
└── mcp/
    └── test_paysafe_resolver_v2.py       # New test file
```

`mcp-tools-skills-prompts.md` must be updated to reflect the new `selection_strategy` values
and the nullability of `framework_version` / `compatibility`.

---

## Design

### 1. Two-layer cache (`findit.py` + `static_registry.json`)

The runtime cache is built in two ordered layers at startup. **Layer 1 always loads first;
Layer 2 is merged on top, overwriting any conflicting keys.** A service present in both
sources uses the FindIt URL, not the static one.

```
Layer 1 — static registry   (migration_oracle/paysafe/static_registry.json)
         ↓  merged (FindIt wins on conflict)
Layer 2 — FindIt bulk/paginated/per-call
         ↓
_REPO_CACHE: dict[str, str]   (service_name normalised → codeRepoLink)
```

#### Layer 1 — static registry (`static_registry.json`)

A JSON file committed to the repository. Contains known Paysafe services and their GitLab
repo URLs. It is the source of last resort and the only source available when FindIt is
unreachable.

**File location:** `migration_oracle/paysafe/static_registry.json`

**Format:**
```json
{
  "payment-service":  "https://gitlab.paysafe.com/platform/payment-service",
  "risk-engine":      "https://gitlab.paysafe.com/platform/risk-engine",
  "fraud-detection":  "https://gitlab.paysafe.com/platform/fraud-detection"
}
```

**Rules:**
- The file must exist and be valid JSON. A missing or unparseable file raises at startup
  (not silently skipped) because it is a committed artefact, not an optional resource.
- An empty object `{}` is valid.
- Keys are service names in their canonical form (the same string a developer would pass as
  `service_name` to the tool). Name normalisation is applied on lookup, not on storage — keep
  the file human-readable.
- This file is maintained by hand (or by a CI job). The spec does not automate its population.

**Loading function:**
```python
def _load_static_registry() -> dict[str, str]:
    path = Path(__file__).parent / "static_registry.json"
    return json.loads(path.read_text())   # raises if missing or invalid JSON
```

#### Layer 2 — FindIt (startup merge)

After the static registry is loaded, `populate_cache()` attempts to fetch all services from
FindIt and merge them in. FindIt results overwrite static entries on key conflict.

```python
_REPO_CACHE: dict[str, str] = {}   # service_name (normalised) → codeRepoLink

def populate_cache(timeout_seconds: float | None = None) -> None:
    """
    Build the two-layer repo-link cache.

    1. Always load static_registry.json first.
    2. Attempt to fetch from FindIt using the strategy in FINDIT_CACHE_STRATEGY:
         "bulk"      — single GET /services call (requires FindIt API support)
         "paginated" — paginated GET /services?page=N loop
         "none"      — skip FindIt entirely; use static registry only
    3. Merge FindIt results into the cache (FindIt wins on conflict).
    4. On FindIt timeout or network failure: log WARNING and keep the static entries.
       The server continues with whatever the static registry provides.
    """
```

The `timeout_seconds` default comes from `config.FINDIT_CACHE_LOAD_TIMEOUT_SECONDS`
(default `30`). The `FINDIT_CACHE_STRATEGY` default is `"none"` until the FindIt bulk
endpoint is confirmed to exist (see `research.md` Question 1). Switch to `"bulk"` or
`"paginated"` once the endpoint is probed and confirmed.

#### Cache key normalisation

The cache stores normalised keys. Normalisation applies the same four-level matching from the
original spec: exact → case-insensitive → alphanumeric → fuzzy. All four forms are inserted as
keys pointing to the same `codeRepoLink` at load time, maximising hit rate.

#### `get_repo_link` — lookup with live fallback

```python
def get_repo_link(service_name: str) -> str | None:
    hit = _REPO_CACHE.get(_normalise(service_name))
    if hit:
        return hit
    # cache miss — fall back to per-call FindIt lookup (original slow path)
    # this covers services added to FindIt after server startup
    record = lookup(service_name)
    link = record.get("codeRepoLink")
    if link:
        _REPO_CACHE[_normalise(service_name)] = link   # warm the cache for next call
    return link
```

On a cache miss, the live fallback also warms the cache so repeat calls for the same service
do not hit FindIt again within the same server lifetime.

### 2. Server startup hook (`server.py`)

```python
@contextlib.asynccontextmanager
async def lifespan(server):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, findit.populate_cache)
    yield
```

If `populate_cache()` raises or times out, catch the exception, log `WARNING`, and let the
server start. Do not re-raise.

### 3. Simplified resolver (`resolver.py`)

Replace the FindIt per-call block (current Step 3) with a cache lookup:

```python
# Step 3 (new): cache lookup with per-call fallback
code_repo_link = findit.get_repo_link(service_name)
if not code_repo_link:
    return _build_error(
        "no_repo_url",
        f"No codeRepoLink found for {service_name!r} in cache or FindIt.",
        recoverable=False,
        actionable_hint="Check that the service is registered in FindIt.",
        details={"service_name": service_name},
    )
```

Replace the compatibility loop (current Steps 6–7) with a direct latest-tag return:

```python
# Step 5 (new): list tags, return the first (latest) one
tags = gitlab.list_tags(code_repo_link, max_tags=1)
best_tag = tags[0]

return _build_result(
    status="ok",
    service_name=service_name,
    selected_tag=best_tag,
    selected_version=_parse_selected_version(best_tag),
    framework=framework,
    framework_version=None,        # no longer fetched
    selection_strategy="latest_overall",
    target_version=target_version,
    code_repo_link=code_repo_link,
    compatibility=None,            # no longer checked
    effective_settings=_build_effective_settings(max_tags),
)
```

The `target_version`, `allow_latest_overall`, and `max_tags` parameters are still accepted by
the public function signature for backward compatibility. `target_version` and
`allow_latest_overall` are silently ignored. `max_tags` is passed to `list_tags()` but in
practice `max_tags=1` is sufficient and can be hardcoded there.

The `pinned_version` / `pinned_tag` short-circuit (Step 1) and the `service_name` validation
(Step 2) are unchanged.

#### Error codes that can no longer occur

`no_compatible_version` and `compatibility_unknown` can no longer be returned by the new
resolver path. Keep their dead-code `_build_error()` definitions with a comment:
`# unreachable in resolver v2 — retained for reference`. Do not remove them until the
cleanup spec.

### 4. New env vars (`config.py`)

| Variable | Default | Description |
|---|---|---|
| `FINDIT_CACHE_STRATEGY` | `"none"` | FindIt bulk-load strategy: `"bulk"`, `"paginated"`, or `"none"` (skip FindIt; use static registry only). Default is `"none"` until the FindIt bulk endpoint is confirmed. |
| `FINDIT_CACHE_LOAD_TIMEOUT_SECONDS` | `30` | Max seconds to wait for the FindIt bulk load before continuing with static registry only |

---

## Updated tool contract (`mcp-tools-skills-prompts.md`)

Update the `resolve_paysafe_dependency_by_service_name` entry:

**Parameters — additions/changes:**

| Name | Type | Required | Default | Change |
|---|---|---|---|---|
| `target_version` | string | no | `null` | Now **ignored**; documented as accepted for backward compat |
| `allow_latest_overall` | boolean | no | `false` | Now **ignored**; always behaves as `true` |

**Returns — changes:**

| Field | Old behaviour | New behaviour |
|---|---|---|
| `framework_version` | Populated when build file was readable | Always `null` |
| `compatibility` | Populated when compatible tag found | Always `null` |
| `selection_strategy` | One of `latest_compatible`, `latest_with_known_compatibility`, `latest_overall` | Always `latest_overall` |

Add a note:

> **v2 behaviour:** FindIt is queried once at server startup. Per-call resolution reads from
> the startup cache and falls back to a live FindIt call only on a cache miss. Compatibility
> checking has been removed — the tool always returns the latest semver-sorted tag. The agent
> harness should treat all results as needing human confirmation before deployment.

---

## Skill changes

Two skill files contain the Paysafe dependency resolution call site and must be updated to
match the new resolver behaviour. Neither file is auto-generated — both are committed source
that agents load at runtime.

### 1. `migration_oracle/mcp/skills/framework_migration_main.md`

**Location:** Loop II tier table row for Paysafe deps, and the query loop decision table.

#### Tier table row (Loop II)

Current:
```
| — | Paysafe deps | — | `resolve_paysafe_dependency_by_service_name` for every `com.paysafe`
dependency. Run concurrently with tier 1 — these are independent. |
```

Replace with:
```
| — | Paysafe deps | — | `resolve_paysafe_dependency_by_service_name` for every `com.paysafe`
dependency. Pass only `service_name` — do not pass `target_version` or `framework`. The tool
always returns the latest available version (`selection_strategy: "latest_overall"`). Run
concurrently with tier 1 — these are independent. |
```

#### Query loop decision table

Current row:
```
| Entity name starts with `com.paysafe` | Call `resolve_paysafe_dependency_by_service_name`
concurrently. Do not wait for it before proceeding with framework rule queries. |
```

Replace with:
```
| Entity name starts with `com.paysafe` | Call `resolve_paysafe_dependency_by_service_name(service_name=<dep>)`
concurrently — omit `target_version`. The tool returns the latest overall version; treat the
result as the recommended upgrade target regardless of the framework version being migrated.
Do not wait for it before proceeding with framework rule queries. |
```

#### Result handling (add after the fallback error table in Loop II)

Add a new note block after the T039 fallback rows:

```
**Paysafe dep result interpretation (v2):**

When `resolve_paysafe_dependency_by_service_name` returns `status="ok"`:
- `selected_version` is the latest semver tag on the library's GitLab repo. Use this as the
  recommended version to pin in `pom.xml` / `build.gradle`.
- `compatibility` and `framework_version` are always `null`. Do not treat their absence as an
  error — this is expected v2 behaviour.
- `selection_strategy` will always be `"latest_overall"`. Surface this to the engineer as
  "latest available — compatibility with the target framework version not verified".
- Record the result in the dependency upgrade table with a ⚠️ unverified badge rather than a
  ✅ verified badge. The engineer must confirm the library version is compatible after upgrading.
```

### 2. `skills/user/framework-migration/SKILL.md`

**Location:** Phase 2 — Step 2c, and the dependency table in the output section.

#### Step 2c call site

Current:
```
resolve_paysafe_dependency_by_service_name(
  service_name    = <dep>,
  target_version  = <TO_VERSION>,
  framework       = <FRAMEWORK>
)
```

Replace with:
```
resolve_paysafe_dependency_by_service_name(
  service_name = <dep>
)
```

Remove the `target_version` and `framework` arguments entirely. Add a comment in the
surrounding prose:

> The tool returns the latest overall version of the library — compatibility with the target
> framework is not verified. Mark the result as unverified in the dependency table (⚠️) and
> note that the engineer should confirm compatibility after upgrading.

#### Dependency table in output (Phase 4, Plan Mode and Assistant Mode)

The existing output shows a dependency table. Add a `Verified` column and populate it:

| Dependency | Current | Recommended | Notes | Verified |
|---|---|---|---|---|
| `payment-service` | `1.4.2` | `2.0.1` | Latest overall | ⚠️ unverified |

The `⚠️ unverified` badge must appear on every Paysafe internal dependency row. A note must
accompany the table:

> ⚠️ Paysafe internal dependency versions are the latest available tag, not the latest version
> verified compatible with `<TO_VERSION>`. Confirm compatibility before deploying.

---

## Tests (`tests/mcp/test_paysafe_resolver_v2.py`)

All tests use mocked HTTP (no live network calls).

| Test | Assertion |
|---|---|
| `test_cache_hit_skips_findit_lookup` | When `_REPO_CACHE` is pre-populated, `findit.lookup()` is never called during `resolver.resolve()` |
| `test_static_registry_loaded_on_startup` | `populate_cache()` with `FINDIT_CACHE_STRATEGY=none` loads entries from `static_registry.json`; `_REPO_CACHE` is non-empty |
| `test_static_registry_missing_raises` | `populate_cache()` raises if `static_registry.json` does not exist |
| `test_static_registry_invalid_json_raises` | `populate_cache()` raises if `static_registry.json` contains invalid JSON |
| `test_findit_overwrites_static_on_conflict` | When the same service key appears in both `static_registry.json` and the FindIt response, the FindIt `codeRepoLink` wins |
| `test_static_entry_kept_when_findit_absent` | When FindIt returns no record for a service that is in the static registry, the static URL is used |
| `test_cache_miss_falls_back_to_lookup` | When `_REPO_CACHE` is empty, `findit.lookup()` is called once and its `codeRepoLink` is used |
| `test_cache_miss_fallback_warms_cache` | After a live fallback, the result is stored in `_REPO_CACHE` so a second call does not hit FindIt |
| `test_returns_latest_tag` | Given two tags `["2.0.0", "1.9.0"]`, `selected_version` is `"2.0.0"` |
| `test_selection_strategy_is_always_latest_overall` | `result["selection_strategy"] == "latest_overall"` regardless of `target_version` |
| `test_compatibility_is_null` | `result["compatibility"] is None` always |
| `test_framework_version_is_null` | `result["framework_version"] is None` always |
| `test_target_version_ignored` | Passing `target_version="2.7"` returns same result as `target_version=None` |
| `test_populate_cache_timeout` | When the FindIt loader exceeds the timeout, static entries are retained and no exception propagates |
| `test_server_starts_when_findit_unreachable` | FindIt failure during `populate_cache()` does not prevent server lifespan from completing; static entries still present |
| `test_pinned_version_still_works` | `pinned_version="1.5.0"` short-circuit returns before any cache or GitLab call |
| `test_invalid_service_name` | Empty `service_name` still returns `error_code="invalid_service_name"` |
| `test_no_repo_url_error` | Cache miss + `lookup()` returns no `codeRepoLink` → `error_code="no_repo_url"` |
| `test_no_tags_found_error` | GitLab returns empty tag list → `error_code="no_tags_found"` |

Existing tests from `003-paysafe-resolver` that cover the compatibility loop
(`test_no_compatible_version`, `test_compatibility_unknown`) must be **updated** to assert that
those code paths are no longer reachable (or simply removed, documented in the PR).

---

## Completion gate

- [ ] `static_registry.json` is committed under `migration_oracle/paysafe/` and contains at least one entry
- [ ] `populate_cache()` always loads `static_registry.json` first, before any FindIt call
- [ ] FindIt results overwrite static registry entries on key conflict (verified by `test_findit_overwrites_static_on_conflict`)
- [ ] Static entries are preserved when FindIt is unreachable (verified by `test_server_starts_when_findit_unreachable`)
- [ ] Missing or invalid `static_registry.json` raises at startup (verified by two raise tests)
- [ ] `resolver.resolve()` never calls `fetch_framework_version()` on any code path
- [ ] `selection_strategy` is always `"latest_overall"` in non-pinned results
- [ ] `framework_version` and `compatibility` are always `null` in non-pinned results
- [ ] All 19 tests above pass with mocked HTTP
- [ ] `mcp-tools-skills-prompts.md` updated with v2 contract note
- [ ] `config.py` has `FINDIT_CACHE_STRATEGY` (default `"none"`) and `FINDIT_CACHE_LOAD_TIMEOUT_SECONDS`
- [ ] Old compatibility-loop error codes retained as unreachable dead code with comments
- [ ] `pytest tests/mcp/` passes (including all pre-existing tests)
- [ ] `framework_migration_main.md` tier table row omits `target_version` and `framework` from the call
- [ ] `framework_migration_main.md` query loop decision table updated to omit `target_version`
- [ ] `framework_migration_main.md` has the new "Paysafe dep result interpretation (v2)" note block
- [ ] `SKILL.md` Step 2c call site passes only `service_name`
- [ ] `SKILL.md` dependency output table has `Verified` column with `⚠️ unverified` on Paysafe rows
- [ ] `SKILL.md` dependency table is accompanied by the unverified compatibility warning note