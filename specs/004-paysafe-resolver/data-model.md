# Data Model: 004-paysafe-resolver

**Branch**: `004-paysafe-resolver` | **Date**: 2026-06-06

---

## ResolveRequest

Input parameters accepted by `resolve()`. All fields except `service_name` are optional.

| Field                 | Type            | Default  | Notes |
|-----------------------|-----------------|----------|-------|
| `service_name`        | `str`           | —        | Required. Name of the Paysafe internal library to look up in FindIt |
| `target_version`      | `str \| None`   | `None`   | Target framework version (e.g. `"3.5.6"`); omit to get latest |
| `framework`           | `str \| None`   | `None`   | Framework hint (e.g. `"spring-boot"`, `"angular"`); informational |
| `allow_latest_overall`| `bool`          | `False`  | If `True`, fall back to newest parseable tag when no compatible tag found. The resolver does NOT default this; the MCP layer sets it explicitly |
| `max_tags`            | `int`           | `100`    | Maximum number of tags to scan (newest-first) before stopping |
| `pinned_version`      | `str \| None`   | `None`   | When set, resolver returns immediately with this version; no FindIt or GitLab calls are made |
| `pinned_tag`          | `str \| None`   | `None`   | Git tag to echo in the pinned result; `null` if not supplied alongside `pinned_version` |

---

## ResolverResult

Returned by `resolve()` on success (`status="ok"`).

| Field              | Type            | Required | Notes |
|--------------------|-----------------|----------|-------|
| `status`           | `str`           | Yes      | Always `"ok"` |
| `service_name`     | `str`           | Yes      | Echo of the input `service_name` |
| `selected_tag`     | `str \| None`   | Yes      | Git tag string (e.g. `"3.5.10"`, `"v3.5.10"`); `null` in pinned mode when `pinned_tag` was not supplied |
| `selected_version` | `str`           | Yes      | Parsed version string (e.g. `"3.5.10"`) |
| `framework`        | `str \| None`   | Yes      | Detected framework (e.g. `"spring-boot"`, `"angular"`); `null` in pinned mode |
| `framework_version`| `str \| None`   | Yes      | Framework version declared in the build file (e.g. `"3.5.10"`); `null` when unreadable or pinned |
| `selection_strategy`| `str`          | Yes      | One of `"latest_compatible"`, `"latest_overall"`, `"latest_with_known_compatibility"`, `"pinned"` |
| `target_version`   | `str \| None`   | Yes      | Echo of the caller-supplied `target_version`; `null` if omitted |
| `code_repo_link`   | `str \| None`   | Yes      | GitLab HTTPS URL from the FindIt record; `null` in pinned mode |
| `compatibility`    | `CompatibilityInfo \| None` | Yes | The `CompatibilityInfo` object from the selected tag's build file parse; `null` when no `target_version` was given or in pinned mode |
| `effective_settings` | `dict`        | Yes      | Runtime configuration that was active during this resolve call — see sub-fields below |
| `name_resolution`  | `NameResolution \| absent` | Conditional | Present only when name matching was non-exact; absent in pinned mode and on exact match |

### `effective_settings` sub-fields

| Sub-field              | Type          | Notes |
|------------------------|---------------|-------|
| `max_tags_returned`    | `int`         | The `max_tags` value used for this call (default 100) |
| `git_timeout_seconds`  | `int`         | Timeout in seconds applied to each git operation (default 30) |
| `retries`              | `int`         | Number of retries attempted on transient failures (default 2) |
| `backoff_seconds`      | `list[float]` | Per-retry delay sequence in seconds (default `[1.0, 3.0]`) |

### Pinned-mode shape (all fields)

```json
{
  "status": "ok",
  "service_name": "<input>",
  "selected_tag": "<pinned_tag | null>",
  "selected_version": "<pinned_version>",
  "framework": null,
  "framework_version": null,
  "selection_strategy": "pinned",
  "target_version": "<input target_version | null>",
  "code_repo_link": null,
  "compatibility": null,
  "effective_settings": {
    "max_tags_returned": 100,
    "git_timeout_seconds": 30,
    "retries": 2,
    "backoff_seconds": [1.0, 3.0]
  }
}
```

`name_resolution` key is **absent** in pinned-mode responses.

---

## NameResolution

Present in `ResolverResult` only when FindIt name matching was non-exact.

| Field            | Type             | Required        | Notes |
|------------------|------------------|-----------------|-------|
| `method`         | `str`            | Yes             | One of `"case_insensitive"`, `"alphanumeric_normalized"`, `"fuzzy"` |
| `matched_name`   | `str`            | Yes             | The canonical service name from the FindIt registry |
| `similarity`     | `float`          | Fuzzy-only      | Numeric similarity score (0.0–1.0); present only when `method="fuzzy"` |
| `threshold_used` | `float`          | Fuzzy-only      | The configured threshold at the time of the match; present only when `method="fuzzy"` |
| `alternatives`   | `list[str]`      | Fuzzy-only      | Other close candidate names from FindIt; may be empty list; present only when `method="fuzzy"` |

### Alphanumeric normalization definition

Strip all non-alphanumeric characters, lowercase the result, then compare.
Example: `"My-Internal.Lib"` → `"myinternallib"`.

### Example (fuzzy match)

```json
{
  "method": "fuzzy",
  "matched_name": "payment-gateway-service",
  "similarity": 0.82,
  "threshold_used": 0.68,
  "alternatives": ["payment-gateway-lib", "payment-service"]
}
```

---

## CompatibilityInfo

Produced by `gitlab.fetch_framework_version()` for each scanned tag and returned as the
`compatibility` field of `ResolverResult`. Callers (including `mcp/tools/paysafe.py`) read
`result["compatibility"]["source_precedence"]` etc. — it is part of the public response shape,
not an internal-only object.

| Field               | Type          | Notes |
|---------------------|---------------|-------|
| `framework_version` | `str`         | Parsed framework version string extracted from the build file (e.g. `"3.5.10"`) |
| `source_file`       | `str`         | Relative path of the build file where the version was found (e.g. `"pom.xml"`, `"build.gradle"`, `"package.json"`) |
| `source_precedence` | `str`         | The specific parser rule that matched, in descending precedence order: `"spring-boot-starter-parent"` → `"spring-boot.version-property"` → `"gradle-plugin-version"` → `"angular-core-dep"` |

### Compatibility states during tag scanning

| State                  | Meaning |
|------------------------|---------|
| `compatible`           | `CompatibilityInfo` returned; declared `(major, minor, patch)` ≥ target's tuple AND same major |
| `incompatible`         | `CompatibilityInfo` returned; different major, or same major but tuple < target |
| `compatibility_unknown`| Build file found at tag but declares no parseable framework version; tag skipped for `latest_compatible`, eligible for `latest_overall` |
| `build_file_missing`   | No build file found at tag ref; tag silently skipped entirely |

**Compatibility rule** (precise):

```
compatible(declared, target) =
  declared.major == target.major
  AND (declared.major, declared.minor, declared.micro) >= (target.major, target.minor, target.micro)
```

---

## ErrorResponse

Returned by `resolve()` on any failure. Errors are always returned as structured dicts;
they never propagate as uncaught exceptions.

**Top-level shape**:

```json
{
  "status": "error",
  "error": { ... }
}
```

**`error` sub-dict fields**:

| Field            | Type    | Required | Notes |
|------------------|---------|----------|-------|
| `error_code`     | `str`   | Yes      | One of the canonical codes below |
| `message`        | `str`   | Yes      | Human-readable description |
| `recoverable`    | `bool`  | Yes      | `True` if a retry or config change may succeed |
| `actionable_hint`| `str`   | Yes      | Concrete suggestion for the caller or operator |
| `details`        | `dict`  | Yes      | Additional context (may be empty dict `{}`) |

Callers MUST read errors via `result["error"]["error_code"]`, **not** `result["error_code"]`.

### Canonical `error_code` values

| `error_code`           | `recoverable` | Trigger condition |
|------------------------|---------------|-------------------|
| `invalid_service_name` | `False`       | `service_name` is empty, null, or whitespace-only |
| `service_not_found`    | `False`       | FindIt returns no match at any of the four matching levels |
| `no_repo_url`          | `False`       | Matched FindIt record contains no `codeRepoLink` |
| `no_tags_found`        | `False`       | GitLab repository has no git tags at all |
| `no_parseable_tags`    | `False`       | Repository has tags but none parse as semantic versions (after v-prefix strip) |
| `no_compatible_version`| `False`       | Tags scanned; none satisfy the compatibility rule; `allow_latest_overall=False` |
| `compatibility_unknown`| `False`       | All scanned tags have build files that exist but declare no parseable framework version; `allow_latest_overall=False` |
| `http_timeout`         | `True`        | FindIt HTTP call times out after all retries |
| `http_request_failed`  | `True`        | FindIt HTTP returns non-success status or non-timeout network error after all retries |
| `git_ls_remote_failed` | `True`        | `git ls-remote` fails (network error, auth failure, non-zero exit) after all retries |

### Example error response

```json
{
  "status": "error",
  "error": {
    "error_code": "service_not_found",
    "message": "No FindIt service matched 'my-nonexistent-lib' at any matching level.",
    "recoverable": false,
    "actionable_hint": "Verify the service name against the FindIt registry at https://findit-api.icd.paysafe.cloud.",
    "details": {
      "input_name": "my-nonexistent-lib",
      "candidates_checked": 4,
      "fuzzy_threshold": 0.68
    }
  }
}
```

---

## Internal: FindItCache

Module-level dict in `findit.py`; never exposed to callers. Keyed by the FindIt base URL
so that different base URLs (e.g. test vs. prod) do not share entries.

```python
# Module-level in findit.py — initialized as empty dict, never re-assigned
from datetime import datetime, timezone

_cache: dict[str, tuple[list[dict], datetime]] = {}
# key   = FINDIT_BASE_URL (stable cache key)
# value = (service_list, fetched_at_utc)  — fetched_at is timezone-aware UTC
```

The TTL check happens at the start of every `lookup()` call:

```python
entry = _cache.get(base_url)
if entry and (datetime.now(timezone.utc) - entry[1]).days < 30:
    return entry[0]   # cache hit
# else: fetch, store, return
```

The cache has **no explicit invalidation path** — it simply expires after 30 days and is
re-fetched on the next call. No eviction or force-refresh mechanism exists.
