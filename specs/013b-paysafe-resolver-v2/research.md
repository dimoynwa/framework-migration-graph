# Research: Paysafe Resolver Simplification

**Spec:** `013b-paysafe-resolver-v2`
**Status:** Pre-implementation spike
**Covers:** Two design questions that must be settled before implementation begins.

---

## Question 1 — Does FindIt expose a bulk "list all services" endpoint?

### Why it matters

The startup-cache design requires fetching all `service_name → codeRepoLink` pairs once, at
MCP server boot. The feasibility of this depends entirely on whether FindIt has a bulk listing
endpoint or whether the client would have to scrape a paginated search.

### What is known from the existing code

`findit.py` currently exposes a `lookup(service_name)` call used per-resolution. The
`SPEC_ORGANIZATION.md` describes FindIt as an internal registry, and `resolver.py` calls it
with a timeout guard because it is "super slow". No bulk endpoint is mentioned anywhere in the
project documentation.

### Options and trade-offs

| Approach | Feasibility | Trade-off |
|---|---|---|
| **A — Bulk `/services` endpoint** | Unknown until the API is probed | If it exists, this is the clean path: one HTTP call at startup populates the FindIt layer of the cache. Ask the FindIt team. |
| **B — Paginated search (`?page=N`)** | Likely, if the registry has a web UI | Requires looping until `next_page` is null. May be slow but only runs once at boot. Acceptable. |
| **C — Skip FindIt bulk load entirely** | Always feasible | Set `FINDIT_CACHE_STRATEGY=none`. Resolution relies on the static registry + per-call live fallback only. This is the safe default until the bulk endpoint is confirmed. |

Note: a "seed file as the only source" option is no longer on the table. The static registry
(`static_registry.json`) is **always** loaded — it is Layer 1 of the cache regardless of
which FindIt strategy is chosen. The question here is only about what happens in Layer 2.

### Recommendation

Ask the FindIt platform team: _"Does your API expose a `GET /services` or `GET /services?page=N`
endpoint that returns all registered services with their `codeRepoLink`?"_

If yes → set `FINDIT_CACHE_STRATEGY` default to `"bulk"` or `"paginated"` once confirmed.

If no → leave `FINDIT_CACHE_STRATEGY` defaulting to `"none"`. The static registry plus
per-call live fallback covers all known services adequately.

### Files to inspect before implementing

- `migration_oracle/paysafe/findit.py` — understand current HTTP client, base URL env var, auth header
- `migration_oracle/config.py` — check whether `FINDIT_BASE_URL` is already declared
- `migration_oracle/mcp/server.py` — find the startup hook (lifespan handler or `@app.on_event("startup")`)

---

## Question 2 — Can "return the latest tag" be done without fetching build files?

### Why it matters

The current resolver scans tags looking for a compatible framework version by fetching and
parsing `pom.xml` / `build.gradle(.kts)` at each tag ref. This is the source of most of the
per-call latency. Switching to "just return the latest tag" means that per-tag build-file
fetching can be eliminated entirely, not just short-circuited.

### What the current code does

`gitlab.py` exposes `list_tags()` (returns sorted tag list) and `fetch_framework_version()` (one
HTTP call per tag to read the build file). The compatibility loop in `resolver.py` calls
`fetch_framework_version()` for up to `max_tags` tags, scanning until it finds a compatible one.

### The proposed simplification

Return `tags[0]` (the latest semver-sorted tag) directly, without calling `fetch_framework_version()`
at all. Set `selection_strategy = "latest_overall"` and `compatibility = None`.

### What is lost

| Field currently populated | After simplification |
|---|---|
| `framework_version` | `null` |
| `compatibility` object | `null` |
| `selection_strategy` | `"latest_overall"` (was sometimes `"latest_compatible"`) |

The MCP tool's return shape already accommodates `null` for these fields — the harness in
`framework_migration_main.md` treats `compatibility=null` as an unverified result and logs it
for human review rather than halting. No downstream contract changes are needed.

### Risk: does the latest tag always build against the target framework version?

In practice, Paysafe internal libraries are released continuously and the trunk is always kept
compatible with the current platform version. The previous compatibility check was defensive
for cases where a library explicitly supported only an older framework major — a situation that,
based on the user's experience, has not been a problem in practice.

The residual risk is surfaced to the agent/engineer via `selection_strategy = "latest_overall"`,
which the harness already treats as "needs human confirmation". No silent failures.

### What can be removed from `gitlab.py`

- `fetch_framework_version()` — no longer called by the resolver. Keep it in the module but
  mark it `# deprecated — not used by resolver v2` so it can be deleted in a future cleanup.
- `_is_compatible()` — same: keep, mark deprecated.
- `detect_framework_at_head()` — same.

**Do not delete these functions in this spec.** A separate cleanup spec should do that after
the new behaviour is confirmed in production. Keeping them avoids breaking any code that
imports them directly.

### Env var for `max_tags`

The current `max_tags` parameter defaults to `15` in `resolver.py` and `100` in the MCP tool
handler. After the simplification, only `tags[0]` is used, so `max_tags` only controls how
many tags `list_tags()` fetches. Setting `max_tags=1` in `list_tags()` after the change would
be a further optimisation. The MCP tool parameter `max_tags` should remain in the public
contract (for forward compatibility) but the resolver can ignore it when using latest-only mode.

---

## Question 3 — Where does the startup cache live in the MCP server lifecycle?

### Finding the right hook

MCP servers built with the `mcp` SDK (FastMCP or the low-level server) expose a lifespan
context manager. The cache should be populated there, before tools are registered and before
the first tool call can arrive.

Pseudo-code target:

```python
# migration_oracle/mcp/server.py

@contextlib.asynccontextmanager
async def lifespan(server):
    await findit.populate_cache()   # blocking I/O; run in executor if async server
    yield

app = FastMCP("PaysafeMigrationOracle", lifespan=lifespan)
```

### Thread-safety of the cache

The cache is written once at startup and read-only thereafter. A plain `dict` is safe for
concurrent reads in CPython (GIL). No lock needed unless the cache is ever refreshed at
runtime (not in scope for this spec).

### Failure behaviour at startup

If FindIt is unreachable at startup, the server must still start. Log a `WARNING` and leave the
cache empty. Per-call fallback: if `cache[service_name]` is a miss, fall back to the current
`findit.lookup(service_name)` path so no resolution is silently broken.

### Startup timeout

The cache load must not block the server indefinitely. Apply a configurable timeout via
`FINDIT_CACHE_LOAD_TIMEOUT_SECONDS` (default `30`). On timeout, log `WARNING` and continue
with empty cache.

---

## Summary of decisions for the implementer

| Decision | Resolution |
|---|---|
| Static registry | `migration_oracle/paysafe/static_registry.json` — always loaded first at startup; raises if missing or invalid |
| FindIt merge | FindIt results merged on top of static registry; FindIt wins on conflict |
| FindIt bulk strategy | Controlled by `FINDIT_CACHE_STRATEGY`; default `"none"` until bulk endpoint is confirmed with FindIt team |
| Cache structure | Single `_REPO_CACHE: dict[str, str]` in `findit.py`; built from static layer then FindIt layer |
| Compatibility check | **Removed** — always return `tags[0]`, `selection_strategy="latest_overall"` |
| Build-file fetching | **Eliminated from hot path** — `fetch_framework_version()` not called by resolver v2 |
| `target_version` parameter | Accepted but ignored; document in tool description |
| `allow_latest_overall` parameter | Always behaves as `True`; keep in signature for backward compat, log deprecation notice if `False` is passed |
| Deprecated functions in `gitlab.py` | Keep, mark with comments, do not delete |
| MCP tool contract changes | Minimal — only `selection_strategy` value and `compatibility`/`framework_version` nullability change |
| Error codes retired | `no_compatible_version`, `compatibility_unknown` — these can no longer occur; keep as dead code with a comment |