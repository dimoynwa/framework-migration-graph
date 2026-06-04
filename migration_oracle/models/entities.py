"""Pydantic models for migration entity extraction batches."""

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class EntityKind(str, Enum):
    CLASS = "class"
    PROPERTY = "property"
    DEPENDENCY = "dependency"


class EntityRole(str, Enum):
    REMOVED = "removed"
    REPLACEMENT = "replacement"
    CO_REQUIRED = "co-required"
    MENTIONED = "mentioned"


class StepType(str, Enum):
    REMOVE = "remove"
    RENAME = "rename"
    REPLACE = "replace"
    CONFIGURE = "configure"
    VERIFY = "verify"
    NAMESPACE = "namespace"


class Effort(str, Enum):
    MECHANICAL = "mechanical"
    MODERATE = "moderate"
    ARCHITECTURAL = "architectural"


class ScopeLevel(str, Enum):
    API_SURFACE = "api-surface"
    RUNTIME = "runtime"
    CONFIG = "config"
    BUILD = "build"
    TEST = "test"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AffectedEntity(BaseModel):
    kind: EntityKind
    name: str
    role: EntityRole


class BreakingScopeInput(BaseModel):
    scope: ScopeLevel
    severity: Severity


class MigrationStep(BaseModel):
    index: int
    step_type: StepType
    summary: str
    instruction: str
    effort: Effort
    automatable: bool
    requires: List[int] = Field(default_factory=list)
    verification: str
    cli_operation: str = Field(default="")


class MigrationEntity(BaseModel):
    source_section: Literal[
        "breaking_change",
        "security_fix",
        "component_upgrade",
        "security_config",
        "behavioral",
        "deprecation",
        "new_capability",
    ]
    title: str
    jira_keys: List[str] = Field(default_factory=list)
    source_url: str = Field(default="")
    change_type: str
    reason_type: Optional[str] = Field(default="")
    reason: str
    scopes: List[BreakingScopeInput] = Field(default_factory=list)
    entities: List[AffectedEntity] = Field(default_factory=list)
    steps: List[MigrationStep] = Field(default_factory=list)
    subsystem: str = Field(default="")


class MigrationEntitiesBatch(BaseModel):
    entities: List[MigrationEntity]


SOURCE_SECTION_TO_RULE_TYPE: dict[str, str] = {
    "breaking_change": "breaking",
    "security_fix": "mandatory_migration",
    "component_upgrade": "mandatory_migration",
    "security_config": "mandatory_migration",
    "behavioral": "behavioral",
    "deprecation": "deprecation",
    "new_capability": "behavioral",
}
