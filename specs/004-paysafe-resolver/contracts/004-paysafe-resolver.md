# Interface Contract: 004-paysafe-resolver

**Consumer**: `mcp/tools/paysafe.py`
**Provider**: `migration_oracle/paysafe/`
**Date**: 2026-06-06

---

## Public API

### Only permitted import

```python
from migration_oracle.paysafe.resolver import resolve
```

`mcp/tools/paysafe.py` MUST import `resolve` directly from
`migration_oracle.paysafe.resolver` (or equivalently via the re-export in
`migration_oracle.paysafe`). All resolution logic is delegated entirely to `resolve()` —
the MCP tool MUST NOT call any function in `findit.py` or `gitlab.py` directly.

Prohibited imports:

- `migration_oracle.paysafe.findit` (implementation detail — delegated to `resolver.py`)
- `migration_oracle.paysafe.gitlab` (implementation detail — delegated to `resolver.py`)

---

## `resolve()` Signature

```python
def resolve(
    service_name: str,
    target_version: str | None = None,
    framework: str | None = None,
    allow_latest_overall: bool = False,
    max_tags: int = 50,
    pinned_version: str | None = None,
    pinned_tag: str | None = None,
) -> dict:
    ...
```

**Return value**: Always a `dict`. Never raises. Shape is either `ResolverResult` or
`ErrorResponse` — see `data-model.md`.

---

## Caller Responsibilities

| Responsibility | Detail |
|----------------|--------|
| Pinned bypass  | When the caller already knows the version, supply `pinned_version` (and optionally `pinned_tag`). The resolver returns immediately without touching FindIt or GitLab. |
| `allow_latest_overall` default | When `target_version` is omitted, the MCP layer MUST explicitly pass `allow_latest_overall=True`. The resolver does NOT default this to `True` internally. |
| Error handling | The caller reads `result["status"]`; on `"error"`, it reads `result["error"]["error_code"]` — NOT `result["error_code"]`. |
| No re-export   | The MCP tool MUST NOT re-export or wrap any symbol from `migration_oracle.paysafe.*` beyond calling `resolve()`. |

---

## Boundary Rules

### `migration_oracle/paysafe/` MUST NOT:

- Import from `migration_oracle.pipeline.*`
- Import from `migration_oracle.graph.*`
- Import or instantiate any graph database driver (Neo4j driver, Memgraph driver, or any
  wrapper thereof). **No graph driver import is permitted anywhere in this package.**
- Write, update, merge, or delete any node or relationship in Neo4j/Memgraph.
  `paysafe/` modules must not write to Neo4j/Memgraph under any code path.
- Read environment variables directly (all config comes from `migration_oracle.config`)
- Make subprocess git calls outside of `gitlab.py`
- Instantiate the FindIt cache per-call (it is a module-level dict in `findit.py`)

### `migration_oracle/paysafe/` MAY:

- Import from `migration_oracle.config` for env var values
- Import from `migration_oracle.models` if shared data models are needed (read-only)
- Use `httpx`, `rapidfuzz`, `packaging`, and the standard library freely

---

## Module Responsibilities

| Module        | Responsibility |
|---------------|----------------|
| `__init__.py` | Exports only `resolve`. No logic. |
| `resolver.py` | Orchestrates the seven-step resolve flow and pinned-mode short-circuit. Calls `findit.py` and `gitlab.py`; contains no HTTP or git code. |
| `findit.py`   | FindIt HTTP client, 30-day in-memory cache (module singleton), four-level name matching. |
| `gitlab.py`   | `git ls-remote`, `git archive` fetch, build-file parsing, framework detection at HEAD. All subprocess calls isolated here. |

---

## Seven-Step Resolve Flow (for `resolver.py`)

1. **Pinned short-circuit** — if `pinned_version` is set, return pinned result immediately.
2. **Validate input** — if `service_name` is blank, return `invalid_service_name` error.
3. **FindIt lookup** — call `findit.lookup(service_name)` → `FindItServiceRecord` or error.
4. **Repo URL extraction** — extract `codeRepoLink`; if absent, return `no_repo_url` error.
5. **Tag enumeration** — call `gitlab.list_tags(repo_url)` → sorted list or error.
6. **Tag scan** — iterate tags newest-first, up to `max_tags`; for each tag call
   `gitlab.fetch_framework_version(repo_url, tag)` and apply compatibility rule.
7. **Strategy selection** — choose `latest_compatible`, `latest_overall`, or
   `latest_with_known_compatibility` based on findings; return `ResolverResult`.

---

## Version: 1.0 | Status: Draft
