# Feature Specification: check_version_availability Latency Fix

**Spec**: `011a-check-version-availability-latency`

**Feature Branch**: `011a-check-version-availability-latency`

**Created**: 2026-06-11

**Status**: Draft

**Source**: `ISSUES.md` Issue A — re-probe of `http://localhost:8080/sse` on 2026-06-11.

---

## Overview

`check_version_availability` takes 15–20 seconds to respond because it makes **two sequential
blocking HTTP calls** to Maven Central, each with a 10-second timeout. Most MCP clients time out
at 5 seconds, so the tool returns `no_response` even though the logic is correct.

The fix is two changes to `migration_oracle/mcp/tools/upgrade.py`:

1. **Run both Maven calls in parallel** using `concurrent.futures.ThreadPoolExecutor` and drop
   the per-request timeout from 10s to 3s. Worst-case wall time drops from 20s to 3s.
2. **Cache results in-process** with a 1-hour TTL so repeated calls for the same version (common
   in agent orchestration sessions) are instantaneous after the first.

No new dependencies. No changes to the tool signature, response shape, or any other tool.

---

## Functional Requirements

### FR-001 — Parallel Maven requests, 3-second timeout

Both Maven Central HTTP calls (GA-presence check and latest-patch lookup) **MUST** be issued
concurrently via `concurrent.futures.ThreadPoolExecutor`. Each call **MUST** use
`timeout=3` (reduced from 10).

The result is collected after both futures complete (or time out). If either future raises an
exception or times out, treat it as though that call returned a miss (same behaviour as the
existing `except Exception` path).

**Acceptance:** `check_version_availability("Spring Boot", "3.5.0")` responds in ≤ 5 seconds
under normal network conditions.

### FR-002 — In-process TTL cache, 1-hour expiry

Results from the Maven Central calls **MUST** be cached in a module-level dict
`_MAVEN_CACHE: dict[tuple, tuple]` keyed by `(group_id, artifact_id, normalised_version)`.
Each entry stores `(ga_available, latest_patch, expires_at)` where `expires_at = time.time() + 3600`.

On a cache hit (entry present and `time.time() < expires_at`), skip both Maven HTTP calls and
return the cached values directly. On a miss (absent or expired), execute FR-001 and write the
result into the cache.

Cache writes **MUST** be protected by a `threading.Lock` to prevent duplicate network calls from
concurrent requests. The lock is only held for the dict write.

**Acceptance:** a second call with the same `(framework, version)` within 60 minutes returns in
< 50 ms and makes zero HTTP requests.

### FR-003 — Graceful degradation unchanged

The existing exception handler that returns `ga_available: False` with hint
`"Maven Central unavailable — could not verify GA status"` **MUST** be preserved. It **MUST**
fire when both parallel futures fail or time out.

**Acceptance:** with Maven Central unreachable (mock), the tool returns `status=ok`,
`ga_available=False`, and a non-empty hint — never raises an unhandled exception.

### FR-004 — Response shape unchanged

The response dict keys (`status`, `exists_in_graph`, `ga_available`, `latest_patch`, `hint`)
**MUST NOT** change. The tool signature **MUST NOT** change (no new parameters).

### FR-005 — Test cache clearance helper

A module-level function `_clear_maven_cache() -> None` **MUST** be exposed to allow tests to
reset the cache between test cases. It simply calls `_MAVEN_CACHE.clear()`.

---

## User Scenario

An AI agent starts a Spring Boot 3.5.0 → 4.0.0 migration session. Before calling
`create_migration_context` it calls `check_version_availability("Spring Boot", "4.0.0")` to
confirm the target version exists in the graph and is released on Maven Central.

**Before this fix:** the call times out at the MCP transport layer (~5s), the agent receives
`no_response`, and either halts or skips the check entirely. The user sees an error.

**After this fix:** both Maven requests fire concurrently and complete in ~2–3s. The agent
receives `{"exists_in_graph": true, "ga_available": false, "hint": "Version 4.0.0 is not
available on Maven Central."}` and proceeds to create the context. If the agent calls the
same tool again later in the session, the response is immediate from cache.

---

## Implementation Plan

All changes are in **`migration_oracle/mcp/tools/upgrade.py`** only. No graph queries, no
ingestion pipeline, no other tool is touched.

### Step 1 — Add imports

```python
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
```

### Step 2 — Add module-level cache and lock

```python
_MAVEN_CACHE: dict[tuple, tuple] = {}
_MAVEN_CACHE_TTL = 3600  # seconds
_MAVEN_CACHE_LOCK = threading.Lock()


def _clear_maven_cache() -> None:
    _MAVEN_CACHE.clear()
```

### Step 3 — Replace the Maven block in `check_version_availability`

Replace lines 210–245 (the two sequential `requests.get` calls and their exception handler) with:

```python
cache_key = (group_id, artifact_id, normalised)
cached = _MAVEN_CACHE.get(cache_key)
if cached and time.time() < cached[2]:
    ga_available, latest_patch = cached[0], cached[1]
else:
    try:
        def _fetch_ga():
            r = requests.get(
                f"{_maven_base}?q=g:{group_id}+AND+a:{artifact_id}+AND+v:{normalised}&rows=1&wt=json",
                timeout=3,
            )
            r.raise_for_status()
            return r.json()["response"]["numFound"] >= 1

        def _fetch_latest():
            r = requests.get(
                f"{_maven_base}?q=g:{group_id}+AND+a:{artifact_id}&rows=1&wt=json&sort=version+desc",
                timeout=3,
            )
            r.raise_for_status()
            docs = r.json()["response"]["docs"]
            return docs[0]["v"] if docs else None

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_ga = executor.submit(_fetch_ga)
            fut_lp = executor.submit(_fetch_latest)
            ga_available = fut_ga.result(timeout=4)
            latest_patch = fut_lp.result(timeout=4)

        with _MAVEN_CACHE_LOCK:
            _MAVEN_CACHE[cache_key] = (ga_available, latest_patch, time.time() + _MAVEN_CACHE_TTL)

    except Exception:
        return {
            "status": "ok",
            "exists_in_graph": exists_in_graph,
            "ga_available": False,
            "latest_patch": None,
            "hint": "Maven Central unavailable — could not verify GA status",
        }
```

The `fut_ga.result(timeout=4)` / `fut_lp.result(timeout=4)` gives a 1-second margin above the
per-request timeout to account for connection setup.

---

## Test Plan

File: `tests/mcp/test_check_version_availability.py`

| # | Test | Assertion |
|---|---|---|
| T1 | Both Maven calls succeed, result returned | `ga_available` and `latest_patch` from mock; both mock URLs called exactly once |
| T2 | Cache hit on second call | Mock called once total across two tool invocations; second call returns same result |
| T3 | GA call times out, falls back gracefully | `ga_available=False`, hint contains "unavailable", no exception raised |
| T4 | Latest-patch call fails, GA call succeeds | `ga_available` is correct; `latest_patch` is `None` |
| T5 | Framework name variants | `"Spring Boot"`, `"spring-boot"`, `"spring boot"` all reach the Maven block without `unsupported_framework` |
| T6 | Version not in graph, Maven says GA | `exists_in_graph=False`, `ga_available=True` — two independent fields |
| T7 | Cache cleared between tests | `_clear_maven_cache()` called in `setUp`/fixture; no cross-test pollution |

---

## Out of Scope

- Making the Maven check optional via a `check_maven: bool` parameter — not needed once latency
  is fixed.
- Persistent cross-process caching (Redis, disk) — in-process TTL is sufficient for an agent
  session; cross-process caching would require a separate service.
- Changes to any other tool or query file.
