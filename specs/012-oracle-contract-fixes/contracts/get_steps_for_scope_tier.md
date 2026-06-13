# Contract: `get_steps_for_scope_tier`

**Work-stream**: WS3 — Query Correctness
**FR**: FR-008
**File**: `migration_oracle/mcp/tools/context.py`, `migration_oracle/mcp/graph/queries/context.py`

---

## Purpose

Return the migration steps for a given scope that are at or above a severity threshold. Used in Loop II to query one tier at a time before calling `analyze_upgrade_path`.

---

## Inputs

| Parameter | Type | Required | Default | Valid values |
|-----------|------|----------|---------|-------------|
| `context_id` | string | yes | — | Element ID of an existing `MigrationContext` |
| `scope` | string | yes | — | One of: `"api-surface"`, `"runtime"`, `"config"`, `"build"`, `"test"`, `"general"` |
| `severity_threshold` | string | no | `"medium"` | **Exactly one of**: `"low"`, `"medium"`, `"high"`, `"critical"` |

> **`force_refresh` is not a parameter of this tool.** Cache bypass for `queriedEntities` is a Loop II agent-loop concept applied per-entity in `framework_migration_main.md`. This tool returns steps for a scope tier; it does not read or write `queriedEntities`.

---

## Severity Filter Semantics

### Rank mapping

| Severity | Integer rank |
|----------|-------------|
| `"low"` | 1 |
| `"medium"` | 2 |
| `"high"` | 3 |
| `"critical"` | 4 |

Defined in `migration_oracle/mcp/graph/queries/_severity.py` as `SEVERITY_RANK`.

### Inclusion condition

A step is **included** when: `SEVERITY_RANK[step_severity] >= SEVERITY_RANK[threshold]`

A step is **excluded** when: `SEVERITY_RANK[step_severity] < SEVERITY_RANK[threshold]`

(Rows with `step_severity = null` — no matching `BreakingScope` — are always excluded when any threshold is set, because `severity_meets_threshold(None, threshold)` returns `False`.)

### Filter table

| `severity_threshold` | Threshold rank | Included (rank ≥ threshold) | Excluded (rank < threshold) |
|----------------------|---------------|-----------------------------|-----------------------------|
| `"low"` | 1 | low(1), medium(2), high(3), critical(4) | — |
| `"medium"` | 2 | medium(2), high(3), critical(4) | low(1) |
| `"high"` | 3 | high(3), critical(4) | low(1), medium(2) |
| `"critical"` | 4 | critical(4) | low(1), medium(2), high(3) |

---

## Outputs — Success

```json
{
  "status": "ok",
  "context_id": "<element-id>",
  "scope": "<scope-value>",
  "severity_threshold": "<threshold-value>",
  "entities": ["<entity_name>", ...],
  "rule_count": <integer>,
  "hits": [
    {
      "entity_name": "<string>",
      "entity_type": "<string>",
      "step_id": "<element-id>",
      "rule_id": "<element-id>",
      "summary": "<string>",
      "scope": "<string>",
      "severity": "<string>"
    }
  ],
  "total": <integer>
}
```

`entities`: sorted list of unique entity names that have hits. `hits`: all (entity, step) pairs. `rule_count`: count of distinct rule IDs in hits.

---

## Outputs — Error (invalid severity_threshold)

Triggered when `severity_threshold` is not one of the four valid values. Returned **before** any Cypher query runs.

```json
{
  "status": "error",
  "error_code": "invalid_severity_threshold",
  "hint": "severity_threshold must be one of: low, medium, high, critical. Got: '<value>'"
}
```

No other fields are returned on this error path.

---

## Outputs — Error (context not found)

```json
{
  "status": "error",
  "error_code": "context_not_found",
  "hint": "Context '<context_id>' not found"
}
```

---

## Implementation Notes

### Validation (new — required by FR-008)

Add a validation guard at the top of the tool function before any Cypher call:

```python
_VALID_THRESHOLDS = {"low", "medium", "high", "critical"}
if severity_threshold not in _VALID_THRESHOLDS:
    return {
        "status": "error",
        "error_code": "invalid_severity_threshold",
        "hint": f"severity_threshold must be one of: {', '.join(sorted(_VALID_THRESHOLDS))}. Got: '{severity_threshold}'",
    }
```

### Severity filtering

Filtering is applied Python-side using `severity_meets_threshold(row["severity"], severity_threshold)` from `_severity.py`. This implements `SEVERITY_RANK[severity] >= SEVERITY_RANK[threshold]`. No change to the Cypher query is required — the existing `SEVERITY_RANK` map and `severity_meets_threshold` function are correct for valid threshold values.

The validation guard (above) must fire **before** the Cypher call so that invalid threshold values are rejected rather than silently falling through to a `SEVERITY_RANK.get("invalid", 0) = 0` lookup that makes the filter a no-op.

### FR-019 compliance

This tool is read-only. It does not write to the graph. `execute_custom_cypher` must not be used as an alternative.

### Docstring update (required)

The tool docstring must be updated to document:
1. The severity ordering: `critical > high > medium > low`
2. The "at or above" inclusion semantics
3. That unrecognised threshold values return `status="error"` with `error_code="invalid_severity_threshold"`
