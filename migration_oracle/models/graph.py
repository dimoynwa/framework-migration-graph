"""Graph read value objects and version utilities."""

from dataclasses import dataclass, field


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
    scope: str
    severity: str


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


@dataclass
class VersionResolutionResult:
    resolvedVersion: str
    resolvedSortable: int
    nodeId: str
    requestedVersion: str
    rounded: bool
    aheadOfCatalogue: bool
    stubCreated: bool
    direction: str  # "exact" | "floor" | "ceil"


@dataclass
class VersionResolutionFailure:
    status: str  # always "NO_CANDIDATE"
    framework: str
    requestedVersion: str
    candidatesConsidered: list[str] = field(default_factory=list)


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
