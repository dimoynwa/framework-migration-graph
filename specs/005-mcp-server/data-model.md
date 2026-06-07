# Data Model: PaysafeMigrationOracle MCP Server (005)

**Phase 1 output** | Branch: `005-mcp-server` | Date: 2026-06-07

All types are Python `TypedDict` or dataclass definitions used in `mcp/tools/` return values. Serialisation to JSON is handled by `FastMCP` when the tool returns a dict or list.

---

## Enumerations

### `artifact_type` (string literal union)

Used as a parameter to `get_artifact_content`.

| Value | Version node property |
|---|---|
| `raw_md` | `rawMdPath` |
| `filtered_md` | `filteredMdPath` |
| `entities_json` | `entitiesJsonPath` |

### `outcome` (string literal union)

Used as a parameter to `update_step_status`.

| Value | Meaning |
|---|---|
| `completed` | Step was applied and verified |
| `skipped` | Step was intentionally skipped |
| `failed` | Step was attempted and failed |

### `migration_status` (string literal union)

Used as a parameter to `close_migration_context` and as a field in `MigrationContextResult`.

| Value | Meaning |
|---|---|
| `in-progress` | Active migration session |
| `blocked` | Waiting on an unresolved dependency or decision |
| `complete` | All steps resolved (set by auto-close or `close_migration_context`) |
| `partial` | Session ended with some steps remaining |
| `abandoned` | Session explicitly abandoned |

---

## Generic wrapper

### `ToolResponse`

Every tool returns a top-level dict that includes a `status` field. Errors use the shape below; success shapes are tool-specific.

```python
class ToolErrorResponse(TypedDict):
    status: Literal["error"]
    error_code: str
    message: str
    recoverable: bool
```

---

## Upgrade tool return types

### `MigrationRuleRecord`

Returned inside `UpgradePlanResult.rules`.

```python
class MigrationRuleRecord(TypedDict):
    rule_id: str          # elementId from Neo4j
    statement: str
    rule_type: str        # breaking | deprecation | behavioral | …
    action_step: str      # may be empty on new nodes
    source_url: str
    change_type: str
    reason: str
    entity_classification: str   # actionable | incomplete | informational
    steps: list[MigrationStepRecord]    # empty when no REQUIRES_STEP edges
    scopes: list[BreakingScopeRecord]   # empty when no HAS_SCOPE edges
    recipes: list[RecipeRef]            # empty when no AUTOMATED_BY edges
```

### `MigrationStepRecord`

```python
class MigrationStepRecord(TypedDict):
    step_id: str
    step_type: str       # remove | rename | replace | configure | verify | namespace
    summary: str
    instruction: str
    effort: str          # mechanical | moderate | architectural
    automatable: bool
    verification_hint: str
    cli_operation: str
```

### `BreakingScopeRecord`

```python
class BreakingScopeRecord(TypedDict):
    scope: str      # api-surface | runtime | config | build | test
    severity: str   # low | medium | high | critical
```

### `RecipeRef`

```python
class RecipeRef(TypedDict):
    recipe_id: str
    display_name: str
    auto: bool
    missing_required_params: list[str]
```

### `UpgradePlanResult`

```python
class UpgradePlanResult(TypedDict):
    status: Literal["ok"]
    framework: str
    from_version: str
    to_version: str
    rules: list[MigrationRuleRecord]
    lifecycle_alerts: list[dict]   # deprecated/removed entities
    format: str                    # "markdown" | "json"
```

### `StepCard`

Used in `RecipePlanResult` manual track.

```python
class StepCard(TypedDict):
    step_id: str
    rule_id: str
    summary: str
    instruction: str
    verification_hint: str
    effort: str
    blocked_reason: str   # empty if not blocked
```

### `AutoTrackStep`

Used in `RecipePlanResult` auto track.

```python
class AutoTrackStep(TypedDict):
    step_id: str
    rule_id: str
    summary: str
    recipe_id: str
    rewrite_yml_fragment: str
```

### `RecipePlanResult`

```python
class RecipePlanResult(TypedDict):
    status: Literal["ok"]
    auto_track: list[AutoTrackStep]
    manual_track: list[StepCard]
    fallback_to_rule_cards: bool   # True when no MigrationStep nodes exist
```

---

## Deprecation tool return types

### `DeprecationResult`

```python
class DeprecationResult(TypedDict):
    status: Literal["ok"]
    entity_name: str
    entity_type: str            # class | property | dependency
    deprecated_in: str | None   # version string
    removed_in: str | None
    replaced_by: str | None     # one hop only
    rules: list[MigrationRuleRecord]
```

### `EvolutionNode`

```python
class EvolutionNode(TypedDict):
    entity_name: str
    entity_type: str
    deprecated_in: str | None
    removed_in: str | None
    rules: list[MigrationRuleRecord]
```

### `EntityEvolutionTimeline`

```python
class EntityEvolutionTimeline(TypedDict):
    status: Literal["ok"]
    origin: str
    chain: list[EvolutionNode]   # up to 5 hops, ordered from oldest to newest
```

---

## Search tool return types

### `SearchHit`

```python
class SearchHit(TypedDict):
    node_id: str
    node_type: str       # MigrationRule | CommunityInsight | OpenRewriteRecipe
    statement: str
    score: float         # RRF score
    source_url: str
    action_step: str     # may be empty
    rule_type: str       # MigrationRule only; empty for other types
```

### `SearchResult`

```python
class SearchResult(TypedDict):
    status: Literal["ok"]
    query: str
    hits: list[SearchHit]
    top_k: int
```

Both `search_migration_knowledge` and `search_openrewrite_recipes` return `SearchResult`. For `search_openrewrite_recipes`, `SearchHit.node_type` is always `"OpenRewriteRecipe"`, `SearchHit.rule_type` is always empty, and `SearchHit.statement` holds the recipe `description` field.

---

## Schema tool return types

### `GraphSchema`

```python
class GraphSchema(TypedDict):
    status: Literal["ok"]
    schema_markdown: str    # static string, no Cypher executed
```

### `CypherResult`

```python
class CypherResult(TypedDict):
    status: Literal["ok"] | Literal["blocked"] | Literal["error"]
    rows: list[dict]        # empty on blocked/error
    row_count: int
    blocked_keyword: str    # set when status == "blocked", empty otherwise
    message: str            # human-readable; empty on success
```

---

## Community tool return types

### `InsightSubmitResult`

```python
class InsightSubmitResult(TypedDict):
    status: Literal["ok"] | Literal["duplicate"]
    insight_id: str        # elementId of created or existing node
    duplicate_of: str      # set when status == "duplicate", empty otherwise
    message: str
```

### `InsightRecord`

```python
class InsightRecord(TypedDict):
    insight_id: str
    statement: str
    solution: str
    source_url: str
    submitted_by: str
    created_at: str        # ISO 8601
    confidence: float
    votes: int
    verified: bool
    version: str           # version string the insight is linked to
```

### `InsightQueryResult`

```python
class InsightQueryResult(TypedDict):
    status: Literal["ok"]
    insights: list[InsightRecord]
    total: int
```

### `VoteResult`

```python
class VoteResult(TypedDict):
    status: Literal["ok"]
    insight_id: str
    new_vote_count: int
```

### `VerifyResult`

```python
class VerifyResult(TypedDict):
    status: Literal["ok"]
    insight_id: str
    verified: bool
```

---

## Context tool return types

### `MigrationContextResult`

```python
class MigrationContextResult(TypedDict):
    status: Literal["ok"]
    context_id: str          # elementId of MigrationContext node
    project_id: str
    from_version: str
    to_version: str
    framework: str
    migration_status: str    # in-progress | blocked | complete | partial | abandoned
    scanned_entities: list[str]
    completed_steps: list[str]
    skipped_steps: list[str]
    created_at: str
    completed_at: str | None
    notes: str
    created: bool            # True if newly created, False if existing context returned
```

### `PendingStep`

```python
class PendingStep(TypedDict):
    step_id: str
    step_type: str            # remove | rename | replace | configure | verify | namespace
    rule_id: str
    summary: str
    instruction: str
    verification_hint: str
    effort: str               # mechanical | moderate | architectural
    automatable: bool
    scope: str                # from linked BreakingScope, empty if absent
    severity: str             # from linked BreakingScope, empty if absent
    requires: list[str]       # step_ids of REQUIRES-edge prerequisites (must complete first)
    recipe_id: str | None     # recipeId from AUTOMATED_BY edge where auto=true and
                              # missingRequiredParams=[]; None if no such edge exists
```

### `PendingStepsResult`

```python
class PendingStepsResult(TypedDict):
    status: Literal["ok"]
    context_id: str
    pending_steps: list[PendingStep]
    total_pending: int
```

### `StepStatusResult`

```python
class StepStatusResult(TypedDict):
    status: Literal["ok"]
    step_id: str
    outcome: str               # completed | skipped | failed
    context_id: str
    context_auto_closed: bool  # True if the context was auto-closed after this update
    context_status: str        # current migration_status of the context
    completed_count: int       # total completed steps for this context after this update
    skipped_count: int         # total skipped steps for this context after this update
```

### `ScopeTierStep`

```python
class ScopeTierStep(TypedDict):
    entity_name: str
    entity_type: str    # class | property | dependency
    step_id: str
    rule_id: str
    summary: str
    scope: str
    severity: str
```

### `ScopeTierResult`

```python
class ScopeTierResult(TypedDict):
    status: Literal["ok"]
    context_id: str
    scope: str
    severity_threshold: str
    entities: list[str]          # unique entity names that have graph hits at this tier
    rule_count: int              # number of distinct MigrationRules found at this tier
    hits: list[ScopeTierStep]    # one entry per (entity, step) pair
    total: int                   # len(hits)
```

### `CloseContextResult`

```python
class CloseContextResult(TypedDict):
    tool_status: Literal["ok"]     # ok/error discriminator — always "ok" on success
    context_id: str
    migration_status: str          # final state: complete | partial | abandoned
    completed_steps: list[str]
    skipped_steps: list[str]
    completed_at: str | None       # ISO datetime or null
    notes: str
```

Note: `tool_status` is the standard ok/error discriminator used by all tools. `migration_status` holds the `MigrationContext.status` value. They MUST be separate fields — do not conflate them. Consistent with `MigrationContextResult` which also keeps `status: Literal["ok"]` and `migration_status: str` distinct.

---

## Paysafe tool return types

### `PaysafeDependencyResult`

`resolve_paysafe_dependency_by_service_name` returns the result of `migration_oracle.paysafe.resolver.resolve()` directly — no wrapping, no transformation (Contract A). The shape mirrors the resolver's return type:

```python
class PaysafeDependencyResult(TypedDict):
    status: Literal["ok"] | Literal["error"]
    # On status == "ok":
    service_name: str
    selected_tag: str | None
    selected_version: str
    framework: str | None
    framework_version: str | None
    selection_strategy: str    # latest_compatible | latest_overall | latest_with_known_compatibility | pinned
    target_version: str | None
    code_repo_link: str | None
    compatibility: dict | None
    effective_settings: dict
    # Optional — present only when FindIt performed name disambiguation:
    name_resolution: dict      # not_required=True if no disambiguation happened
    # On status == "error":
    error: dict                # { error_code, message, recoverable, actionable_hint, details }
```

The MCP tool does NOT add extra fields; it does NOT suppress error cases. The full resolver result passes through unchanged.

---

## Install tool return types

### `InstallSkillResult`

```python
class InstallSkillResult(TypedDict):
    status: Literal["ok"] | Literal["error"]
    target: str               # "cursor" | "claude-code" | detected value when target="auto"
    installed_paths: list[str]  # absolute paths of the files written
    message: str              # human-readable summary; set on both ok and error
```

---

## Artifact tool return types

### `ArtifactRunRecord`

```python
class ArtifactRunRecord(TypedDict):
    framework: str
    from_version: str
    to_version: str
    raw_md_path: str
    filtered_md_path: str | None
    entities_json_path: str | None
```

### `ArtifactListResult`

```python
class ArtifactListResult(TypedDict):
    status: Literal["ok"]
    runs: list[ArtifactRunRecord]
    total: int
```

### `ArtifactContentResult`

```python
class ArtifactContentResult(TypedDict):
    status: Literal["ok"] | Literal["not_found"]
    framework: str
    from_version: str
    to_version: str
    artifact_type: str       # raw_md | filtered_md | entities_json
    content: str             # file content as string; empty on not_found
    path_resolved: str       # path read from Version node property; empty on not_found
    message: str             # set on not_found, empty on ok
```

---

## MCP Tool Parameter Types

### `analyze_upgrade_path` parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `framework` | `str` | required | |
| `current_version` | `str` | required | |
| `target_version` | `str` | required | |
| `user_entities` | `list[str]` | `[]` | FQCNs, property keys, dep names from codebase scan |
| `format` | `str` | `"json"` | `"markdown"` or `"json"` |
| `classification` | `str \| None` | `None` | Filter by entityClassification |
| `include_recipes` | `bool` | `False` | Include AUTOMATED_BY recipe metadata |
| `include_lifecycle` | `bool` | `True` | Include lifecycle alerts |
| `top_n` | `int` | `50` | Max rules to return |
| `verbose` | `bool` | `False` | Include full reasoning fields |
| `scope_filter` | `list[str]` | `[]` | NEW — filter by HAS_SCOPE scope values |
| `min_severity` | `str \| None` | `None` | NEW — minimum severity threshold |

### `build_recipe_plan` parameters

All pre-existing parameters are frozen (Contract G). `scope_filter` and `min_severity` are new optional additive parameters (redesign §6.7).

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `current_version` | `str` | required | Pre-existing — frozen |
| `target_version` | `str` | required | Pre-existing — frozen |
| `framework` | `str` | `"Spring Boot"` | Pre-existing — frozen |
| `user_entities` | `list[str] \| None` | `None` | Pre-existing — frozen; entity filter |
| `auto_only` | `bool` | `False` | Pre-existing — frozen; omit manual track when True |
| `classification` | `list[str]` | `["actionable","incomplete"]` | Pre-existing — frozen |
| `scope_filter` | `list[str]` | `[]` | NEW (redesign §6.7) |
| `min_severity` | `str \| None` | `None` | NEW (redesign §6.7) |

### `create_migration_context` parameters

| Parameter | Type | Default |
|---|---|---|
| `project_id` | `str` | required |
| `from_version` | `str` | required |
| `to_version` | `str` | required |
| `framework` | `str` | required |
| `scanned_entities` | `list[str]` | `[]` |

### `get_pending_steps` parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `context_id` | `str` | required | |
| `effort_filter` | `list[str]` | `[]` | Filter by effort level(s), e.g. `["mechanical"]` for auto track only |
| `scope_filter` | `list[str]` | `[]` | Filter by scope(s), e.g. `["api-surface", "runtime"]` for tier 1+2 |

### `update_step_status` parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `context_id` | `str` | required | |
| `step_id` | `str` | required | elementId of MigrationStep node |
| `outcome` | `str` | required | `completed \| skipped \| failed` |
| `reason` | `str` | `""` | Free text: "build passed", "user skipped: not applicable" (redesign §6.3 name) |

### `get_steps_for_scope_tier` parameters

| Parameter | Type | Default |
|---|---|---|
| `context_id` | `str` | required |
| `scope` | `str` | required | `api-surface \| runtime \| config \| build \| test` |
| `severity_threshold` | `str` | `"medium"` | Minimum severity |

### `close_migration_context` parameters

| Parameter | Type | Default |
|---|---|---|
| `context_id` | `str` | required |
| `final_status` | `str` | required | `complete \| partial \| abandoned` |
| `notes` | `str` | `""` | |

### `get_artifact_content` parameters

| Parameter | Type | Default |
|---|---|---|
| `framework` | `str` | required |
| `from_version` | `str` | required |
| `to_version` | `str` | required |
| `artifact_type` | `str` | required | `raw_md \| filtered_md \| entities_json` |

### `resolve_paysafe_dependency_by_service_name` parameters

| Parameter | Type | Default |
|---|---|---|
| `service_name` | `str` | required |
| `target_version` | `str \| None` | `None` |
| `framework` | `str \| None` | `None` |
| `allow_latest_overall` | `bool` | `False` |
| `max_tags` | `int` | `100` |
| `pinned_version` | `str \| None` | `None` |
| `pinned_tag` | `str \| None` | `None` |
