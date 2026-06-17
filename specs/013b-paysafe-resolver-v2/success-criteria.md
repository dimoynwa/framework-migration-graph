# Success Criteria: Paysafe Resolver v2

**Spec:** `013b-paysafe-resolver-v2`

Success criteria are organised into four tiers: **startup**, **resolution**, **error handling**, and **skill correctness**. Each criterion states the observable outcome, how to verify it, and which spec goal it validates.

---

## Tier 1 — Startup behaviour

These criteria must hold before any tool call is made.

### SC-01 · Static registry loads unconditionally

**What must be true:** When the MCP server starts with `FINDIT_CACHE_STRATEGY=none`, `_REPO_CACHE` contains every entry from `static_registry.json` before the first tool call arrives.

**How to verify:**
```python
from migration_oracle.paysafe import findit
findit._REPO_CACHE.clear()
findit.populate_cache()   # strategy=none
assert len(findit._REPO_CACHE) >= 1
assert "payment-service" in findit._REPO_CACHE   # or any known key from the file
```

**Validates:** Goal 1 (static registry as baseline).

---

### SC-02 · Missing `static_registry.json` fails fast at startup

**What must be true:** If `static_registry.json` does not exist, `populate_cache()` raises before the server becomes available. The server does not start silently with an empty cache.

**How to verify:**
```python
import pytest
from unittest.mock import patch
from pathlib import Path

with patch.object(Path, "read_text", side_effect=FileNotFoundError):
    with pytest.raises(FileNotFoundError):
        findit.populate_cache()
```

**Validates:** The static registry is a committed artefact, not optional.

---

### SC-03 · Invalid `static_registry.json` fails fast at startup

**What must be true:** If `static_registry.json` contains invalid JSON, `populate_cache()` raises `json.JSONDecodeError` before the server becomes available.

**How to verify:** Write `"not json"` to a temp file, monkeypatch the path, confirm `JSONDecodeError` is raised.

**Validates:** Same as SC-02.

---

### SC-04 · FindIt failure at startup does not prevent server start

**What must be true:** When `FINDIT_CACHE_STRATEGY=bulk` and the FindIt endpoint is unreachable, the server starts successfully and `_REPO_CACHE` still contains the static registry entries.

**How to verify:**
```python
with patch("migration_oracle.paysafe.findit._load_findit_bulk", side_effect=Exception("network error")):
    findit.populate_cache()   # must not raise
    assert len(findit._REPO_CACHE) >= 1   # static entries still present
```

**Validates:** Goal 2 (FindIt failure is non-fatal).

---

### SC-05 · FindIt timeout at startup does not prevent server start

**What must be true:** When the FindIt loader exceeds `FINDIT_CACHE_LOAD_TIMEOUT_SECONDS`, `populate_cache()` returns normally (does not raise, does not hang), and static entries are retained.

**How to verify:** Mock the loader to `time.sleep(60)`, set timeout to `0.1`, confirm `populate_cache()` returns within 2 seconds with static entries intact.

**Validates:** Goal 2 (timeout resilience).

---

### SC-06 · FindIt entries overwrite static entries on conflict

**What must be true:** When the same service name appears in both `static_registry.json` and the FindIt response, the `_REPO_CACHE` entry holds the FindIt URL, not the static URL.

**How to verify:**
```python
static = {"payment-service": "https://static.example.com/payment-service"}
findit_data = {"payment-service": "https://findit.example.com/payment-service"}

# populate with both
findit._REPO_CACHE.update(static)   # simulates static layer
findit._REPO_CACHE.update(findit_data)   # simulates FindIt merge
assert findit._REPO_CACHE["payment-service"] == "https://findit.example.com/payment-service"
```

**Validates:** Goal 2 (FindIt has higher priority).

---

## Tier 2 — Resolution behaviour

These criteria apply to every call to `resolve_paysafe_dependency_by_service_name`.

### SC-07 · Cache hit eliminates FindIt I/O

**What must be true:** When `_REPO_CACHE` contains the requested service, `findit.lookup()` is never called during `resolver.resolve()`.

**How to verify:**
```python
with patch("migration_oracle.paysafe.findit.lookup") as mock_lookup:
    findit._REPO_CACHE["payment-service"] = "https://gitlab.paysafe.com/platform/payment-service"
    result = resolver.resolve("payment-service")
    mock_lookup.assert_not_called()
```

**Validates:** Goal 2 (per-call FindIt I/O eliminated).

---

### SC-08 · Cache miss falls back to live `lookup()` and warms the cache

**What must be true:** When a service is not in `_REPO_CACHE`, `findit.lookup()` is called once. After the call, the service is in `_REPO_CACHE` so a second call does not hit `lookup()` again.

**How to verify:**
```python
findit._REPO_CACHE.clear()
with patch("migration_oracle.paysafe.findit.lookup", return_value={"codeRepoLink": "https://..."}) as mock_lookup:
    resolver.resolve("new-service")   # cache miss → lookup called
    mock_lookup.assert_called_once()
    resolver.resolve("new-service")   # now in cache → lookup not called again
    mock_lookup.assert_called_once()  # still only one call
```

**Validates:** Live fallback correctness and cache warming.

---

### SC-09 · `selection_strategy` is always `"latest_overall"`

**What must be true:** Every successful (non-pinned) resolution returns `selection_strategy == "latest_overall"`, regardless of whether `target_version` is supplied.

**How to verify:**
```python
result_with = resolver.resolve("payment-service", target_version="3.2.0")
result_without = resolver.resolve("payment-service", target_version=None)
assert result_with["selection_strategy"] == "latest_overall"
assert result_without["selection_strategy"] == "latest_overall"
```

**Validates:** Goal 3 (latest-only resolution).

---

### SC-10 · `compatibility` and `framework_version` are always `null`

**What must be true:** Every successful (non-pinned) resolution returns `compatibility is None` and `framework_version is None`.

**How to verify:**
```python
result = resolver.resolve("payment-service")
assert result["compatibility"] is None
assert result["framework_version"] is None
```

**Validates:** Goal 3 and Goal 4 (no contract breakage — fields still present, now always null).

---

### SC-11 · Latest semver tag is always selected

**What must be true:** When GitLab returns tags `["2.0.0", "1.9.0", "1.8.5"]`, `selected_version` is `"2.0.0"`.

**How to verify:**
```python
with patch("migration_oracle.paysafe.gitlab.list_tags", return_value=["2.0.0", "1.9.0", "1.8.5"]):
    result = resolver.resolve("payment-service")
    assert result["selected_version"] == "2.0.0"
```

**Validates:** Goal 3.

---

### SC-12 · `target_version` parameter is silently ignored

**What must be true:** Passing `target_version="2.7"` returns the same `selected_version` as passing `target_version=None`. No error or warning is raised to the caller.

**How to verify:**
```python
r1 = resolver.resolve("payment-service", target_version=None)
r2 = resolver.resolve("payment-service", target_version="2.7")
assert r1["selected_version"] == r2["selected_version"]
assert r1["status"] == r2["status"] == "ok"
```

**Validates:** Goal 4 (no contract breakage for callers that still pass `target_version`).

---

### SC-13 · `pinned_version` short-circuit still works

**What must be true:** When `pinned_version` is supplied, the function returns immediately with `selection_strategy="pinned"` and never touches the cache, FindIt, or GitLab.

**How to verify:**
```python
with patch("migration_oracle.paysafe.findit.get_repo_link") as mock_cache, \
     patch("migration_oracle.paysafe.gitlab.list_tags") as mock_tags:
    result = resolver.resolve("payment-service", pinned_version="1.5.0", pinned_tag="v1.5.0")
    assert result["selected_version"] == "1.5.0"
    assert result["selection_strategy"] == "pinned"
    mock_cache.assert_not_called()
    mock_tags.assert_not_called()
```

**Validates:** Goal 4 (pinned override unchanged).

---

### SC-14 · `fetch_framework_version()` is never called

**What must be true:** On no code path through `resolver.resolve()` is `gitlab.fetch_framework_version()` called.

**How to verify:**
```python
with patch("migration_oracle.paysafe.gitlab.fetch_framework_version") as mock_ffv:
    resolver.resolve("payment-service")
    mock_ffv.assert_not_called()
```

Run this assertion across multiple call variants: with and without `target_version`, with and without `allow_latest_overall`.

**Validates:** Goal 3 (compatibility scanning eliminated).

---

## Tier 3 — Error handling

### SC-15 · Empty `service_name` returns `error_code="invalid_service_name"`

**What must be true:** `resolver.resolve("")` returns `{"status": "error", "error": {"error_code": "invalid_service_name"}}` without touching the cache or GitLab.

**Validates:** Pre-existing error contract preserved.

---

### SC-16 · Service not in cache or FindIt returns `error_code="no_repo_url"`

**What must be true:** When `_REPO_CACHE` is empty and `findit.lookup()` returns no `codeRepoLink`, the resolver returns `error_code="no_repo_url"` with an `actionable_hint` mentioning `static_registry.json`.

**How to verify:**
```python
findit._REPO_CACHE.clear()
with patch("migration_oracle.paysafe.findit.lookup", return_value={}):
    result = resolver.resolve("unknown-service")
    assert result["error"]["error_code"] == "no_repo_url"
    assert "static_registry.json" in result["error"]["actionable_hint"]
```

**Validates:** Error contract updated with v2 hint.

---

### SC-17 · GitLab returning no tags yields `error_code="no_tags_found"`

**What must be true:** When `gitlab.list_tags()` raises `_GitError(error_code="no_tags_found")`, the resolver returns the corresponding error shape.

**Validates:** Pre-existing error contract preserved.

---

## Tier 4 — Skill correctness

These criteria are verified by reading the updated skill files, not by running code.

### SC-18 · `framework_migration_main.md` Paysafe call omits `target_version`

**What must be true:** The Loop II tier table row for Paysafe deps instructs the agent to call `resolve_paysafe_dependency_by_service_name(service_name=<dep>)` with no other arguments. The `target_version` and `framework` parameters do not appear in the call example.

**How to verify:** `grep -n "target_version" migration_oracle/mcp/skills/framework_migration_main.md` returns no hits in the Paysafe deps row or the query loop decision table row.

---

### SC-19 · `framework_migration_main.md` has v2 result interpretation block

**What must be true:** The file contains the "Paysafe dep result interpretation (v2)" note block immediately after the T039 fallback rows. The block instructs the agent to treat `compatibility=null` as expected (not an error) and to show `⚠️ unverified` rather than `✅`.

**How to verify:** `grep -n "result interpretation" migration_oracle/mcp/skills/framework_migration_main.md` returns a hit.

---

### SC-20 · `SKILL.md` dependency table has `Verified` column with `⚠️ unverified`

**What must be true:** The output dependency table in the assistant-mode skill includes a `Verified` column. Every Paysafe internal dependency row shows `⚠️ unverified`. The table is followed by a warning note about unverified compatibility.

**How to verify:** `grep -n "unverified" migration_oracle/mcp/skills/framework-migration_main.md` returns at least two hits (one in the table, one in the note).

---

## Full test suite gate

```bash
pytest tests/mcp/ -v --tb=short
```

**Must exit 0.** All pre-existing tests pass (with compatibility-loop tests updated or removed). All 19 new tests in `test_paysafe_resolver_v2.py` pass. No live network calls made during the test run (enforced by the absence of any non-patched HTTP calls in the new test file).

---

## Acceptance summary

| # | Criterion | Tier | Automated |
|---|---|---|---|
| SC-01 | Static registry loads unconditionally at startup | Startup | ✅ |
| SC-02 | Missing `static_registry.json` fails fast | Startup | ✅ |
| SC-03 | Invalid JSON in `static_registry.json` fails fast | Startup | ✅ |
| SC-04 | FindIt network failure does not prevent startup | Startup | ✅ |
| SC-05 | FindIt timeout does not prevent startup | Startup | ✅ |
| SC-06 | FindIt overwrites static on key conflict | Startup | ✅ |
| SC-07 | Cache hit eliminates FindIt I/O | Resolution | ✅ |
| SC-08 | Cache miss falls back and warms cache | Resolution | ✅ |
| SC-09 | `selection_strategy` always `"latest_overall"` | Resolution | ✅ |
| SC-10 | `compatibility` and `framework_version` always null | Resolution | ✅ |
| SC-11 | Latest semver tag selected | Resolution | ✅ |
| SC-12 | `target_version` silently ignored | Resolution | ✅ |
| SC-13 | `pinned_version` short-circuit unchanged | Resolution | ✅ |
| SC-14 | `fetch_framework_version()` never called | Resolution | ✅ |
| SC-15 | Empty service name → `invalid_service_name` | Errors | ✅ |
| SC-16 | Unknown service → `no_repo_url` with updated hint | Errors | ✅ |
| SC-17 | No tags → `no_tags_found` | Errors | ✅ |
| SC-18 | Harness skill omits `target_version` from call | Skill | 👁 manual |
| SC-19 | Harness skill has v2 result interpretation block | Skill | 👁 manual |
| SC-20 | Assistant skill table has `⚠️ unverified` column | Skill | 👁 manual |