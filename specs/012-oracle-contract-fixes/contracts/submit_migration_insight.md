# Contract: `submit_migration_insight`

**Work-stream**: WS4 — Tool API Alignment
**FR**: FR-013
**File**: `migration_oracle/mcp/tools/community.py`, `migration_oracle/mcp/graph/queries/community.py`

---

## Purpose

Submit a developer-contributed migration insight. Near-duplicate detection fires before the write; if a near-duplicate is found, no new insight is created and the existing one's ID is returned. Documents the dedup threshold and produces a consistent response shape across all three status paths.

---

## Inputs

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `statement` | string | yes | — |
| `spring_boot_version` | string | yes | — |
| `solution` | string | no | `None` |
| `affected_properties` | list[string] | no | `None` |
| `affected_classes` | list[string] | no | `None` |
| `affected_dependencies` | list[string] | no | `None` |
| `evidence_url` | string | no | `None` |
| `confidence` | float | no | `None` |
| `framework` | string | no | `"Spring Boot"` |

---

## Outputs — Three Status Paths

### `status="ok"` — new insight created

```json
{
  "status": "ok",
  "insight_id": "<element-id of new MigrationRule>",
  "duplicate_of": null,
  "message": "Insight submitted"
}
```

`insight_id`: the element ID of the newly-created `MigrationRule` node.
`duplicate_of`: `null` — no duplicate was found.

### `status="duplicate"` — near-duplicate already exists

```json
{
  "status": "duplicate",
  "insight_id": null,
  "duplicate_of": "<element-id of existing MigrationRule>",
  "message": "Near-duplicate insight already exists"
}
```

`insight_id`: `null` — **no new insight was created**.
`duplicate_of`: element ID of the existing insight that triggered the duplicate detection.

> **Bug fix required**: The current code returns `{"insight_id": existing_id, "duplicate_of": existing_id}` for duplicates. Both fields contain the same value, making it impossible to distinguish "new ID" from "existing ID" without reading the status field. The corrected semantics set `insight_id=null` on `status="duplicate"`.

### `status="error"` — submission failed

```json
{
  "status": "error",
  "insight_id": null,
  "duplicate_of": null,
  "message": "<error description>"
}
```

`insight_id` and `duplicate_of` are both `null` on error. `message` contains the exception message (e.g. `"Version not found: Spring Boot 3.x"`).

---

## Dedup Pipeline (FR-013)

The dedup pipeline runs **before** any `CREATE` statement. Three detection passes in order:

| Pass | Mechanism | Threshold |
|------|-----------|-----------|
| 1 — Exact match | `MATCH (r:MigrationRule) WHERE r.statement = $statement AND r.ruleType = 'community_insight'` | Identical string = duplicate |
| 2 — Vector similarity | `db.index.vector.queryNodes('migration_knowledge_vector_mr', 5, $embedding)` with `min_similarity=0.92` | Cosine ≥ **0.92** = duplicate |
| 3 — BM25 shortlist + cosine | Top-5 from `rule_statement` fulltext index; compute cosine for each | Cosine ≥ **0.92** = duplicate |

**Cosine similarity threshold: 0.92** (value of `_DUPLICATE_SIMILARITY_THRESHOLD` in `community.py`)

The model used for embeddings is `all-mpnet-base-v2` (768-dimensional sentence-transformer). If embedding generation fails (e.g. model unavailable), only exact-statement matching runs.

This threshold and pipeline must be stated in the tool docstring.

### Pass 1 — Exact match Cypher

```cypher
MATCH (r:MigrationRule)
WHERE r.statement = $statement
  AND r.ruleType = 'community_insight'
RETURN elementId(r) AS insight_id
LIMIT 1
```

If this returns a record, the submitted insight is a duplicate. Return `status="duplicate"` with `duplicate_of=insight_id`. Do not proceed to Pass 2 or 3.

### Pass 2 — Vector similarity Cypher

```cypher
CALL db.index.vector.queryNodes('migration_knowledge_vector_mr', 5, $embedding)
YIELD node, score
WHERE score >= 0.92
RETURN elementId(node) AS insight_id, score
ORDER BY score DESC
LIMIT 1
```

`$embedding` is the `all-mpnet-base-v2` embedding vector for the submitted `statement`. If this returns a record, the submission is a near-duplicate. Return `status="duplicate"` with `duplicate_of=insight_id`. Do not proceed to Pass 3.

If embedding generation fails, skip Passes 2 and 3 silently; only exact-statement matching applies.

### Pass 3 — BM25 shortlist + cosine Cypher

```cypher
CALL db.index.fulltext.queryNodes('rule_statement', $statement, {limit: 5})
YIELD node, score
RETURN elementId(node) AS insight_id, node.statement AS candidate_statement
```

For each returned candidate, compute cosine similarity between the submitted statement embedding and `candidate_statement` embedding in Python. If any candidate's cosine similarity ≥ 0.92, the submission is a near-duplicate. Return `status="duplicate"` with `duplicate_of` = the element ID of the first candidate that exceeds the threshold.

If no pass detects a duplicate, proceed with the `CREATE` statement for the new `MigrationRule` node.

---

## Docstring update (required)

```
Submit a developer-contributed migration insight. Writes a MigrationRule node
with ruleType='community_insight'.

Near-duplicate detection runs before write using a three-pass pipeline:
  1. Exact statement match
  2. Vector similarity (cosine ≥ 0.92 using all-mpnet-base-v2 embeddings)
  3. BM25 shortlist + cosine ≥ 0.92 fallback

Returns:
  status="ok":        insight_id=<new element ID>, duplicate_of=null
  status="duplicate": insight_id=null, duplicate_of=<existing element ID>
  status="error":     insight_id=null, duplicate_of=null, message=<error>

Not idempotent — call once per unique finding.
```

---

## FR-019 Compliance

`submit_migration_insight` writes the new `MigrationRule` node through its own Cypher (`submit_insight` in `community.py`). `execute_custom_cypher` is read-only and must not be used as an alternative for the write or the dedup queries.

---

## Error Shapes (updated)

The error shape now explicitly includes `insight_id: null` and `duplicate_of: null`. The `message` field was already present. The existing `except ValueError` handler in the tool function returns an error dict — update it to match the three-field shape:

```python
except ValueError as e:
    return {"status": "error", "insight_id": None, "duplicate_of": None, "message": str(e)}
```

All other error paths are preserved (FR-018).
