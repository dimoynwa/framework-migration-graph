# Contract: resolve_paysafe_dependency_by_service_name — Auth and Transport Errors

**Spec anchor**: FR-D01, FR-D02, US6  
**Updated in**: 013-real-run-hardening

---

## Current State

`resolve_paysafe_dependency_by_service_name` delegates to `migration_oracle/paysafe/resolver.py`. The resolver currently returns `status: "error"` with a variety of `error_code` values (`service_not_found`, `http_timeout`, `http_request_failed`, `git_ls_remote_failed`, etc.) but does not distinguish credential failures from connectivity failures at the MCP tool response level.

---

## Required Changes

### 1. `auth_error` — Credential Failure

When `FINDIT_AUTH_TOKEN` or `GITLAB_API_KEY` is missing or invalid, the tool must return:

```json
{
  "status": "RESOLUTION_FAILED",
  "subStatus": "auth_error",
  "failureReason": "string — which credential is missing/invalid",
  "remediationSteps": [
    "Set FINDIT_AUTH_TOKEN env var: export FINDIT_AUTH_TOKEN=<token>",
    "Set GITLAB_API_KEY env var: export GITLAB_API_KEY=<token>"
  ],
  "unresolvedDependencies": ["string — service names that could not be resolved"],
  "fallbackInstructions": "string — e.g. 'Run gradle dependencies --configuration runtimeClasspath and inspect output manually'"
}
```

**Trigger conditions**:
- `FINDIT_AUTH_TOKEN` env var is absent or empty
- `FINDIT_AUTH_TOKEN` is set but the FindIt API returns HTTP 401 or 403
- `GITLAB_API_KEY` is set but GitLab API returns HTTP 401

The existing resolver error code `http_request_failed` with a 401/403 status must be mapped to `auth_error`.

### 2. `transport_error` — Network or Connectivity Failure

When the endpoint is reachable but the request times out or returns a 5xx, or when DNS resolution fails:

```json
{
  "status": "RESOLUTION_FAILED",
  "subStatus": "transport_error",
  "failureReason": "string — timeout, DNS, or 5xx description",
  "remediationSteps": [
    "Check VPN connection",
    "Verify FINDIT_BASE_URL is reachable: curl -s $FINDIT_BASE_URL/health"
  ],
  "unresolvedDependencies": ["string"],
  "fallbackInstructions": "string"
}
```

**Trigger conditions**:
- `requests.exceptions.Timeout` or `FuturesTimeout`
- HTTP 5xx response
- `requests.exceptions.ConnectionError` (DNS / network unreachable)

The existing `http_timeout` error code maps to `transport_error`.

### 3. Backlog Emission (FR-D02)

After any `RESOLUTION_FAILED` response, the Loop II harness must emit each entry in `unresolvedDependencies` as a backlog item for Loop IV. The harness — not the tool — is responsible for this emission.

---

## Loop II Fallback Row

Add this row to the Loop II decision table in `framework_migration_main.md`:

| Condition | Action |
|---|---|
| `resolve_paysafe_dependency_by_service_name` returns `subStatus: "auth_error"` | Log `auth_error` with `remediationSteps`. Emit `unresolvedDependencies` as backlog items. Surface `fallbackInstructions` to engineer. Continue to next entity — do not halt Loop II. |
| `resolve_paysafe_dependency_by_service_name` returns `subStatus: "transport_error"` | Log `transport_error` with `remediationSteps`. Emit `unresolvedDependencies` as backlog items. Surface `fallbackInstructions`. Continue. |

---

## Backward Compatibility

The existing `status: "error"` responses for `service_not_found`, `no_tags_found`, and `no_parseable_tags` are unchanged. Only `auth_error` and `transport_error` are new outer-level `RESOLUTION_FAILED` wrappers.
