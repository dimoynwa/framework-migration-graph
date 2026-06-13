# Research — Spec 011a: check_version_availability Latency

Phase 0 research artifact. Resolves the technical unknowns for fixing the 15–20 second response
time on `check_version_availability` confirmed by the 2026-06-11 re-probe.

---

## Spike 1 — Root cause: two sequential blocking HTTP calls at timeout=10s

### Finding

`migration_oracle/mcp/tools/upgrade.py:210-230` makes **two sequential `requests.get` calls** to
`https://search.maven.org/solrsearch/select`, each with `timeout=10`:

1. GA-presence check: `?q=g:{group}+AND+a:{artifact}+AND+v:{version}&rows=1`
2. Latest-patch lookup: `?q=g:{group}+AND+a:{artifact}&rows=1&sort=version+desc`

Worst-case wall time is **2 × 10 = 20 seconds** before the exception path fires. The probe
measured 15–20s on the network, which matches. The MCP transport default for many clients is 5s;
this tool reliably times out at the client before the server responds.

The graph-lookup portion (`read_session()` + `_CHECK_VERSION_IN_GRAPH`) is fast — it is only the
Maven Central calls that are slow.

---

## Spike 2 — Fix option analysis

### Option A — Reduce per-request timeout (minimal change)

Drop `timeout=10` to `timeout=3` on both calls. Total worst-case: **6 seconds**. Still sequential
but now fits within a generous MCP timeout.

**Pros:** one-line change per call, zero new dependencies, trivially safe.  
**Cons:** 3s is still too slow for latency-sensitive clients (e.g. Claude Desktop default is ~5s).
If Maven Central is slow but not down, you still pay up to 6s.

### Option B — Reduce timeout + run requests in parallel (recommended)

Use `concurrent.futures.ThreadPoolExecutor` (already available in stdlib) to fire both Maven
requests concurrently with a short timeout. Both calls share the same `_maven_base` URL and are
independent. Total worst-case wall time: **max(3, 3) = 3 seconds** — a single timeout instead of
two sequential ones.

**Pros:** worst-case drops from 20s to 3s; no new dependencies; correct for callers with 5s
timeouts.  
**Cons:** marginally more complex than Option A; adds ~4 lines.

### Option C — In-process TTL cache (additive to B)

Wrap the combined Maven result `(ga_available, latest_patch)` in a `functools.lru_cache`-style
dict with a timestamp. TTL of **1 hour** per `(group_id, artifact_id, normalised_version)` key.

**Rationale:** Maven Central release data for a given version is immutable — once a version is GA
it stays GA. Caching the result means the first call per version is slow (up to 3s with Option B)
and every subsequent call is instantaneous. In practice, an agent checking the same version
multiple times in a session (e.g. confirm before create, confirm before close) pays zero latency
after the first call.

**Pros:** eliminates repeated network calls within a session and across sessions while the process
is running.  
**Cons:** adds ~10 lines; stale on a 1-hour horizon (acceptable for release metadata).

### Option D — Make Maven check truly optional (skip parameter)

Add `check_maven: bool = True` to the tool signature. When `False`, skip both Maven calls and
return `ga_available: null`.

**Pros:** callers that only care about `exists_in_graph` are never blocked.  
**Cons:** changes the tool signature and shifts the complexity to the caller; agents that do not
pass the flag still block. Lower priority — Options B+C solve the problem transparently.

---

## Decision

**Implement Options B + C:** parallel requests with `timeout=3` each, wrapped in a 1-hour
in-process TTL cache.

- The parallel execution eliminates the 2× sequential penalty.
- The 3s timeout fits within any sane MCP client timeout with headroom.
- The TTL cache makes repeated calls in a session free.
- No new dependencies; stdlib only (`concurrent.futures`, plain `dict` + `time.time()`).
- The exception handler on line 238 already exists; on timeout it returns a graceful
  `ga_available: False` with a clear hint — that fallback is retained.

Option D (skip flag) is explicitly **not** included: it complicates the tool signature for a
problem that B+C already solve transparently.

---

## Spike 3 — Cache invalidation and correctness

### Key: `(group_id, artifact_id, normalised_version)`

`group_id` and `artifact_id` come from `_MAVEN_COORDS[cf.slug]` (static, never changes at
runtime). `normalised_version` is `to_minor_zero(version)`, which is deterministic. The triple is
stable for the lifetime of the process.

### TTL: 1 hour (`3600` seconds)

Maven Central does not un-publish released versions. The only case where the cached result could
be stale is a version transitioning from "not yet GA" to "GA" during the TTL window. For a
migration-planning tool, a 1-hour delay in recognizing a brand-new release is acceptable. The
`latest_patch` value can change (new patch released), but again a 1-hour lag is immaterial.

### Thread safety

The server may handle concurrent requests. A plain `dict` with `time.time()` checks is safe for
reads; a `threading.Lock` around writes prevents a race where two concurrent misses both fire
network requests. The lock is only held for the dict write (microseconds), so it does not
introduce contention.

### Cache location

Module-level `_MAVEN_CACHE: dict[tuple, tuple]` (key → `(ga_available, latest_patch, expires_at)`)
in `migration_oracle/mcp/tools/upgrade.py`. No separate file needed; the module is already the
authoritative home for this tool.

---

## Spike 4 — Impact on existing tests

`tests/mcp/test_check_version_availability.py` likely patches `requests.get`. With parallel
execution the patch target is the same (`requests.get`); the test only needs to verify both mock
calls are made. The TTL cache must be **bypassed or cleared** in tests to avoid cross-test
pollution — expose a `_clear_maven_cache()` helper or use `unittest.mock.patch.dict` on the cache
dict directly.
