# Data Model — 000 Foundations

> All Pydantic types, enums, dataclass value objects, and storage formats defined by this spec.

---

## Pydantic models (`migration_oracle/models/entities.py`)

Verbatim from `migration-oracle-redesign.md` §4.5. No aliases. No field renames.

### Enums

```python
class EntityKind(str, Enum):
    CLASS      = "class"
    PROPERTY   = "property"
    DEPENDENCY = "dependency"

class EntityRole(str, Enum):
    REMOVED      = "removed"
    REPLACEMENT  = "replacement"
    CO_REQUIRED  = "co-required"   # hyphen, not underscore — this is the serialised value
    MENTIONED    = "mentioned"

class StepType(str, Enum):
    REMOVE    = "remove"
    RENAME    = "rename"
    REPLACE   = "replace"
    CONFIGURE = "configure"
    VERIFY    = "verify"
    NAMESPACE = "namespace"

class Effort(str, Enum):
    MECHANICAL    = "mechanical"
    MODERATE      = "moderate"
    ARCHITECTURAL = "architectural"

class ScopeLevel(str, Enum):
    API_SURFACE = "api-surface"    # hyphen — graph property value is "api-surface"
    RUNTIME     = "runtime"
    CONFIG      = "config"
    BUILD       = "build"
    TEST        = "test"

class Severity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"
```

### Core models

```python
class AffectedEntity(BaseModel):
    kind: EntityKind
    name: str
    role: EntityRole

class BreakingScopeInput(BaseModel):
    scope:    ScopeLevel
    severity: Severity

class MigrationStep(BaseModel):
    index:         int
    step_type:     StepType
    summary:       str
    instruction:   str
    effort:        Effort
    automatable:   bool
    requires:      List[int]   = Field(default_factory=list)
    verification:  str
    cli_operation: str         = Field(default="")

class MigrationEntity(BaseModel):
    source_section: Literal[
        "breaking_change", "security_fix", "component_upgrade",
        "security_config", "behavioral", "deprecation", "new_capability"
    ]
    title:       str
    jira_keys:   List[str]             = Field(default_factory=list)
    source_url:  str                   = Field(default="")
    change_type: str
    reason_type: Optional[str]         = Field(default="")
    reason:      str
    scopes:      List[BreakingScopeInput] = Field(default_factory=list)
    entities:    List[AffectedEntity]  = Field(default_factory=list)
    steps:       List[MigrationStep]   = Field(default_factory=list)
    subsystem:   str                   = Field(default="")

class MigrationEntitiesBatch(BaseModel):
    entities: List[MigrationEntity]
```

---

## `source_section` → `ruleType` mapping

Used by `pipeline/populator.py` when writing `MigrationRule.ruleType`.
Defined here as a module-level constant in `models/entities.py` so it has one home.

```python
SOURCE_SECTION_TO_RULE_TYPE: dict[str, str] = {
    "breaking_change":   "breaking",
    "security_fix":      "mandatory_migration",
    "component_upgrade": "mandatory_migration",
    "security_config":   "mandatory_migration",
    "behavioral":        "behavioral",
    "deprecation":       "deprecation",
    "new_capability":    "behavioral",
}
```

---

## Graph value objects (`migration_oracle/models/graph.py`)

Plain `@dataclass` — not Pydantic. Used as typed return objects from Cypher result rows.
Not persisted. Never serialised to disk.

```python
@dataclass
class VersionNode:
    framework: str
    version: str
    sortable_version: int
    raw_md_path: str | None = None
    filtered_md_path: str | None = None
    entities_json_path: str | None = None

@dataclass
class MigrationRuleNode:
    element_id: str
    statement: str
    rule_type: str
    change_type: str
    entity_classification: str
    title: str | None = None
    jira_keys: list[str] = field(default_factory=list)
    source_url: str = ""

@dataclass
class MigrationStepNode:
    element_id: str
    step_type: str
    summary: str
    instruction: str
    effort: str
    automatable: bool
    verification_hint: str
    cli_operation: str = ""

@dataclass
class BreakingScopeNode:
    scope: str       # ScopeLevel value
    severity: str    # Severity value

@dataclass
class MigrationContextNode:
    element_id: str
    project_id: str
    from_version: str
    to_version: str
    framework: str
    status: str
    completed_steps: list[str]
    skipped_steps: list[str]
    created_at: str
    completed_at: str | None = None
    notes: str = ""
```

---

## `sortable_version` utility

```python
def sortable_version(version: str) -> int:
    """
    Compute major * 1_000_000 + minor * 1_000 + patch.

    Accepts "3.2.1", "3.2", "17.0.0". The patch component defaults to 0
    when only major.minor is given. Raises ValueError for anything else.
    """
    parts = version.split(".")
    if len(parts) < 2 or len(parts) > 3:
        raise ValueError(f"Cannot parse version: {version!r}")
    try:
        major, minor = int(parts[0]), int(parts[1])
        patch = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        raise ValueError(f"Cannot parse version: {version!r}")
    return major * 1_000_000 + minor * 1_000 + patch
```

---

## Environment variable reference (`migration_oracle/config.py`)

| Variable | Required | Default | Type | Notes |
|---|---|---|---|---|
| `NEO4J_URI` | Yes | — | `str` | Bolt URI |
| `NEO4J_PASSWORD` | Yes | — | `str` | Empty string treated as absent |
| `NEO4J_USERNAME` | No | `"neo4j"` | `str` | |
| `MODEL_PROVIDER` | No | `"anthropic"` | `str` | `bedrock\|openai\|anthropic\|ollama\|litellm` |
| `MODEL_ID` | No | `""` | `str` | Provider default used when empty |
| `GITHUB_TOKEN` | No | `""` | `str` | |
| `FINDIT_AUTH_TOKEN` | No | `""` | `str` | Required at runtime for Paysafe resolution |
| `FINDIT_BASE_URL` | No | `"https://findit.paysafe.com"` | `str` | |
| `SENTENCE_TRANSFORMERS_MODEL` | No | `"all-mpnet-base-v2"` | `str` | |
| `SSL_VERIFY` | No | `"true"` | `bool` | Falsy: `"false"`, `"False"`, `"FALSE"`, `"0"` |
| `MCP_TRANSPORT` | No | `"stdio"` | `str` | `stdio\|sse\|streamable-http` |
| `MCP_HOST` | No | `"0.0.0.0"` | `str` | |
| `MCP_PORT` | No | `"8080"` | `int` | |
| `ARTIFACT_CACHE_DIR` | No | `"./artifacts"` | `str` | Root for pipeline output files |
| `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` | No | `"0.68"` | `float` | |
| `LOG_LEVEL` | No | `"INFO"` | `str` | |

---

## Graph indexes (`migration_oracle/graph/indexes.py`)

### Uniqueness constraints

| Constraint name | Node | Key |
|---|---|---|
| `version_unique` | `Version` | `(framework, version)` |
| `migration_rule_url` | `MigrationRule` | `sourceUrl` |
| `class_name` | `Class` | `name` |
| `property_name` | `ApplicationProperty` | `name` |
| `dependency_name` | `Dependency` | `name` |
| `breaking_scope_pair` | `BreakingScope` | `(scope, severity)` |
| `migration_context_key` | `MigrationContext` | `(projectId, fromVersion, toVersion)` |

### Range indexes

| Index name | Node | Property |
|---|---|---|
| `version_sortable` | `Version` | `sortableVersion` |
| `version_framework` | `Version` | `framework` |
| `step_rule_index` | `MigrationStep` | `(ruleId, stepIndex)` |
| `step_effort` | `MigrationStep` | `effort` |
| `breaking_scope_scope` | `BreakingScope` | `scope` |
| `context_project` | `MigrationContext` | `projectId` |

### Full-text indexes (may fail on Memgraph — caught and logged)

| Index name | Node | Properties |
|---|---|---|
| `rule_statement` | `MigrationRule` | `statement` |
| `step_instruction` | `MigrationStep` | `instruction`, `summary` |
