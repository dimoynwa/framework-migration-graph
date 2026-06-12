# Credential Scrub Contract

- **Sole scrub point:** `_build_error()` in `migration_oracle/paysafe/resolver.py` is the ONLY place where credential patterns are redacted from error messages
- **Scrub regex:** `https?://[^:@/\s]+:[^@\s]+@` → replaces matched segment with `<redacted>@`; also covers `oauth2:[^@]+@`
- **Implementation:** A module-level compiled regex `_CRED_RE` and a `_scrub(s: str) -> str` helper function, both defined at the top of `resolver.py`. The `_build_error()` function applies `_scrub` to its `message` argument before storing it in the returned dict
- **Coverage:** This single scrub point covers ALL call sites automatically — no call site needs to scrub independently
- **Prohibition:** Raw exception strings from git or network operations MUST NEVER be passed directly to any MCP response field without passing through `_build_error()`. The outer `except Exception` block in `resolve()` also passes through `_build_error()`
- **Violation consequence:** OAuth2 tokens or basic-auth credentials leaked into the LLM context (security defect P0-2)
