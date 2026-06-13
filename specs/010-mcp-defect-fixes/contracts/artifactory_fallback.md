# Artifactory Fallback Contract

- **Transparency invariant:** Callers of `resolve()` receive the same `error_code` shape and response structure regardless of whether the version list came from GitLab or Artifactory. The internal backend used is never exposed in the response
- **Trigger condition:** Fallback to Artifactory fires ONLY when `_GitError` with `error_code="git_ls_remote_failed"` is raised AND `ARTIFACTORY_BASE_URL` env var is set and non-empty
- **No-fallback condition:** When `ARTIFACTORY_BASE_URL` is absent or empty, the original `_GitError` is re-surfaced via `_build_error()` unchanged — no Artifactory attempt
- **Credentials:** Artifactory call MUST use anonymous read (no `Authorization` header, no credentials in URL). This is the only permitted mode. No additional environment variable for Artifactory credentials is introduced by this spec
- **Double-failure:** When both GitLab and Artifactory fail, `_build_error()` is called with the combined error context. The returned error_code should be `"git_ls_remote_failed"` (the primary error) with an `actionable_hint` noting the Artifactory fallback also failed
- **Scope:** This contract applies only to `migration_oracle/paysafe/resolver.py`. No other module implements or replicates the Artifactory fallback logic
