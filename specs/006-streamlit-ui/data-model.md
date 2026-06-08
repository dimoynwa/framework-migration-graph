# Data Model: Streamlit Operator UI (006-streamlit-ui)

**Date**: 2026-06-08  
**Source**: Actual tool function return values (verified against source code)

All shapes below reflect **what the tool functions actually return**, not the spec's assumed shapes. See `research.md` §Critical Discrepancies for mismatches found during planning.

---

## Tool Response Shapes

### PipelineRun

Returned per entry in `list_pipeline_runs()["runs"]`.

```python
class PipelineRun(TypedDict):
    framework: str           # e.g. "spring-boot"
    from_version: str        # always "" in current implementation
    to_version: str          # e.g. "3.2"
    raw_md_path: str         # filesystem path or ""
    filtered_md_path: str | None
    entities_json_path: str | None
```

**Display label**: `f"{run['framework']} → {run['to_version']}"` (omit from_version when blank).

---

### ArtifactContent

Returned by `get_artifact_content(framework, from_version, to_version, artifact_type)`.

```python
class ArtifactContent(TypedDict):
    status: str              # "ok" | "not_found" | "error"
    content: str             # full file text when status=="ok", else ""
    path_resolved: str       # resolved filesystem path
    framework: str
    from_version: str
    to_version: str
    artifact_type: str       # "raw_md" | "filtered_md" | "entities_json"
```

---

### SearchHit

Returned per entry in `search_migration_knowledge(...)["hits"]`.

```python
class SearchHit(TypedDict):
    node_id: str             # Neo4j element ID
    node_type: str           # e.g. "MigrationRule", "CommunityInsight"
    statement: str           # full statement text
    score: float             # RRF fusion score
    source_url: str          # may be ""
    action_step: str         # may be ""
    rule_type: str           # e.g. "breaking-change", may be ""
```

**Note**: No `title`, `changeType`, `steps`, `scopes`, or `severity` fields. Rule Explorer cards
display `statement[:80]` as the card title and `rule_type` as the type badge.

---

### PendingStep

Returned per entry in `get_pending_steps(context_id)["pending_steps"]`.

```python
class PendingStep(TypedDict):
    step_id: str
    step_type: str
    rule_id: str
    summary: str
    instruction: str
    verification_hint: str
    effort: str              # e.g. "mechanical", "substantial"
    automatable: bool
    scope: str               # may be ""
    severity: str            # may be ""
    requires: list[str]      # step IDs this step depends on
    recipe_id: str | None
```

---

### CommunityInsight

Returned per entry in `get_community_insights(...)["insights"]`.

```python
class CommunityInsight(TypedDict):
    insight_id: str
    statement: str
    solution: str
    source_url: str          # always "" (stored as evidence_url in graph)
    submitted_by: str
    created_at: str
    confidence: float
    votes: int
    verified: bool
    version: str             # framework version string
```

**Note**: The submit form uses `evidence_url` (not `source_url`) as the parameter name.

---

### MigrationContextResponse

Returned by `create_migration_context(...)`.

```python
class MigrationContextResponse(TypedDict):
    status: str
    context_id: str
    project_id: str
    from_version: str
    to_version: str
    framework: str
    migration_status: str    # "in-progress" | "complete" | "partial" | "abandoned"
    scanned_entities: list[str]
    completed_steps: list[str]
    skipped_steps: list[str]
    created_at: str
    completed_at: str | None
```

---

### UpdateStepResponse

Returned by `update_step_status(context_id, step_id, outcome, reason="")`.

```python
class UpdateStepResponse(TypedDict):
    status: str
    step_id: str
    outcome: str
    context_id: str
    context_auto_closed: bool
    context_status: str
    completed_count: int
    skipped_count: int
```

---

### CloseContextResponse

Returned by `close_migration_context(context_id, final_status, notes="")`.

```python
class CloseContextResponse(TypedDict):
    tool_status: str         # note: "tool_status" not "status"
    context_id: str
    migration_status: str
    completed_steps: list[str]
    skipped_steps: list[str]
    completed_at: str | None
    notes: str
```

---

### VoteInsightResponse

Returned by `vote_insight(insight_id, delta=1)`.

```python
class VoteInsightResponse(TypedDict):
    status: str
    insight_id: str
    new_vote_count: int
```

---

## Session State

The Context Dashboard stores individual flat keys in `st.session_state` with a `context_` prefix. All eight keys are set together after a successful `create_migration_context` call and are absent before a context is loaded.

| `st.session_state` key | Type | Source field |
|---|---|---|
| `"context_id"` | `str` | `response["context_id"]` |
| `"context_project_id"` | `str` | `response["project_id"]` |
| `"context_from_version"` | `str` | `response["from_version"]` |
| `"context_to_version"` | `str` | `response["to_version"]` |
| `"context_framework"` | `str` | `response["framework"]` |
| `"context_status"` | `str` | `response["migration_status"]` |
| `"context_completed_count"` | `int` | `response["completed_steps"]` length |
| `"context_skipped_count"` | `int` | `response["skipped_steps"]` length |

**Presence check**: `"context_id" in st.session_state` — truthy when a context is loaded.  
**No other page reads or writes these keys** — they are private to `04_context_dashboard.py`.

---

## SubprocessResult

Ephemeral, held in local variables within the Pipeline Trigger page callback.

```python
class SubprocessResult(TypedDict):
    exit_code: int
    stdout_lines: list[str]
    stderr_lines: list[str]
```

---

## Submit Insight Form Fields

Maps to `submit_migration_insight(...)` parameters (actual, not spec-assumed).

| Form label | Parameter name | Type |
|---|---|---|
| Statement | `statement` | `str` |
| Solution | `solution` | `str \| None` |
| Version | `spring_boot_version` | `str` |
| Affected classes (comma-sep) | `affected_classes` | `list[str] \| None` |
| Evidence URL | `evidence_url` | `str \| None` |
| Framework | `framework` | `str` (default "Spring Boot") |
