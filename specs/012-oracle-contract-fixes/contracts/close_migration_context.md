# Contract: `close_migration_context`

**Work-stream**: WS2 — Graph-State Contract
**FR**: FR-007
**File**: `migration_oracle/mcp/tools/context.py`

---

## Purpose

Set `completedAt`, `status`, and `notes` on a `MigrationContext`. Now accepts `"abandoned"` as a valid `final_status` value in addition to `"complete"` and `"partial"`.

---

## Inputs

| Parameter | Type | Required | Valid values |
|-----------|------|----------|-------------|
| `context_id` | string | yes | Element ID of an existing `MigrationContext` |
| `final_status` | string | yes | **One of**: `"complete"`, `"partial"`, `"abandoned"` |
| `notes` | string | no | Free-form notes to record on the context |

---

## Outputs — Success

```json
{
  "tool_status": "ok",
  "context_id": "<element-id>",
  "migration_status": "<string>",
  "completed_steps": ["<element-id>"],
  "skipped_steps": ["<element-id>"],
  "completed_at": "<ISO-8601-string>",
  "notes": "<string>"
}
```

`migration_status`: reflects the newly-set status value (`"complete"`, `"partial"`, or `"abandoned"`).

---

## Outputs — Error (invalid final_status)

```json
{
  "tool_status": "error",
  "error_code": "invalid_final_status",
  "hint": "final_status must be one of: complete, partial, abandoned"
}
```

Returned **before** any Cypher is executed. The context is not modified.

---

## Outputs — Error (context not found)

Raised by the Cypher layer when no context exists for the given element ID. Currently surfaces as a Python `ValueError` — this propagates as an MCP-level error. This behaviour is **unchanged** (FR-018).

---

## Implementation Change

### What changes

Add input validation at the top of the tool function before calling `context_queries.close_migration_context`:

```python
_VALID_FINAL_STATUSES = {"complete", "partial", "abandoned"}
if final_status not in _VALID_FINAL_STATUSES:
    return {
        "tool_status": "error",
        "error_code": "invalid_final_status",
        "hint": f"final_status must be one of: {', '.join(sorted(_VALID_FINAL_STATUSES))}",
    }
```

### What does NOT change

- `_CLOSE_CONTEXT` Cypher: already performs `SET ctx.status = $final_status` without validation — it works correctly for any valid string. No Cypher change needed.
- Return structure: `tool_status`, `context_id`, `migration_status`, `completed_steps`, `skipped_steps`, `completed_at`, `notes` — all unchanged.

### FR-019 Compliance

`close_migration_context` writes through `_CLOSE_CONTEXT` only. `execute_custom_cypher` is read-only and must not be used as an alternative write path.

### Docstring update (required)

```
Set completedAt, migration_status, and notes on a context. Call at the end of every session.

final_status: one of 'complete' (all steps done), 'partial' (steps were skipped or deferred),
or 'abandoned' (session cancelled or deferred indefinitely).

Note: update_step_status auto-closes the context when all steps complete — call this tool
explicitly only when ending a session with skipped steps, adding notes, or abandoning.
Returns: context_id, migration_status, completed_steps, skipped_steps, completed_at, notes.
```
