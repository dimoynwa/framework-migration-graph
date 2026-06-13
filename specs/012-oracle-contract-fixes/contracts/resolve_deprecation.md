# Contract: `resolve_deprecation`

**Work-stream**: WS4 — Tool API Alignment
**FR**: FR-010
**File**: `migration_oracle/mcp/graph/queries/deprecation.py` (`_RESOLVE_DEPRECATION`), `migration_oracle/mcp/tools/deprecation.py`

---

## Purpose

Return deprecation metadata and replacement for a single entity name. The response field `entity_name` must contain the entity's actual name from the graph — not `null`.

---

## Inputs

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity_name` | string | yes | — |
| `framework` | string | no | `"Spring Boot"` |

---

## Outputs — Success

```json
{
  "status": "ok",
  "entity_name": "<string>",
  "entity_type": "<string>",
  "deprecated_in": "<version-string|null>",
  "removed_in": "<version-string|null>",
  "replaced_by": "<string|null>",
  "rules": [
    {
      "rule_id": "<string>",
      "statement": "<string>",
      "rule_type": "<string>",
      "action_step": "<string>",
      "source_url": "<string>",
      "change_type": "<string>",
      "reason": "<string>",
      "entity_classification": "<string>",
      "steps": [],
      "scopes": [],
      "recipes": []
    }
  ]
}
```

**`entity_name`** must be the entity's actual name as stored in the graph (e.g. `"org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter"`). It must never be `null` on a successful response.

> **Note on `rules[]` shape**: The fields shown above (`rule_id`, `statement`, `rule_type`, `action_step`, `source_url`, `change_type`, `reason`, `entity_classification`, `steps`, `scopes`, `recipes`) are inherited from the pre-existing `_RESOLVE_DEPRECATION` Cypher collect. The actual Cypher collects `type`, `statement`, `reason`, `solution`, `action_step` — the richer fields (`source_url`, `steps`, `scopes`, `recipes`) may be absent or empty in practice. This shape mismatch predates FR-010 and is out of scope; only the `entity_name` alias is corrected here. Callers should treat extended `rules[]` fields as potentially absent.

---

## Outputs — Not Found

```json
{
  "status": "not_found",
  "entity_name": "<input-entity-name>",
  "message": "No deprecation records found"
}
```

---

## Bug Fix: Cypher Alias Rename (FR-010)

### Current bug

The `_RESOLVE_DEPRECATION` Cypher query returns the entity name under the alias `original_entity`:

```cypher
RETURN
  labels(e)[0] AS entity_type,
  e.name AS original_entity,   -- ← wrong alias
  ...
```

The tool then reads `record.get("original_entity")` and maps it to the `entity_name` response field. If `original_entity` is unexpectedly `null`, the tool falls back to the user-supplied `entity_name` input — masking any Cypher-level bug silently.

### Fix

Rename the Cypher alias from `original_entity` to `entity_name`:

```cypher
RETURN
  labels(e)[0] AS entity_type,
  e.name AS entity_name,       -- ← corrected alias
  replacement.name AS replaced_by,
  coalesce(depV.version, introV.version) AS deprecated_in,
  coalesce(remV.version, removedByV.version) AS removed_in,
  rules
```

Update the Python tool to read `record.get("entity_name")` instead of `record.get("original_entity")`:

```python
return {
    "status": "ok",
    "entity_name": record.get("entity_name") or entity_name,  # ← updated key
    ...
}
```

Update `resolve_deprecation` in `deprecation.py` to check `record.get("entity_name") is None` (instead of `record.get("original_entity") is None`) for the null guard.

### Documentation alignment

Both the Cypher alias and the tool's Returns table must use `entity_name`. After the fix, the Returns table in the docstring and the Cypher alias agree.

---

## Error Shapes (unchanged)

All existing error shapes are preserved (FR-018). The only changes are:
1. The Cypher alias rename
2. The Python key reference update
3. The docstring Returns table
