"""Tests for Pydantic models and graph value objects."""

import pytest

from migration_oracle.models import (
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
    ScopeLevel,
    SOURCE_SECTION_TO_RULE_TYPE,
    sortable_version,
)

FULL_FIXTURE = {
    "entities": [
        {
            "source_section": "breaking_change",
            "title": "Remove legacy API",
            "jira_keys": ["PROJ-1", "PROJ-2"],
            "source_url": "https://example.com/changelog#1",
            "change_type": "removal",
            "reason_type": "security",
            "reason": "Deprecated endpoint removed in 3.0",
            "subsystem": "web",
            "scopes": [
                {"scope": "api-surface", "severity": "high"},
                {"scope": "runtime", "severity": "medium"},
            ],
            "entities": [
                {"kind": "class", "name": "LegacyClient", "role": "removed"},
                {
                    "kind": "dependency",
                    "name": "legacy-lib",
                    "role": "co-required",
                },
            ],
            "steps": [
                {
                    "index": 0,
                    "step_type": "remove",
                    "summary": "Delete LegacyClient",
                    "instruction": "Remove all references to LegacyClient",
                    "effort": "mechanical",
                    "automatable": True,
                    "requires": [1],
                    "verification": "Compile succeeds",
                    "cli_operation": "grep -r LegacyClient",
                },
                {
                    "index": 1,
                    "step_type": "verify",
                    "summary": "Run integration tests",
                    "instruction": "Execute test suite",
                    "effort": "moderate",
                    "automatable": False,
                    "requires": [],
                    "verification": "All tests pass",
                    "cli_operation": "",
                },
            ],
        }
    ]
}


def test_full_round_trip() -> None:
    batch = MigrationEntitiesBatch.model_validate(FULL_FIXTURE)
    entity = batch.entities[0]
    assert entity.title == "Remove legacy API"
    assert entity.jira_keys == ["PROJ-1", "PROJ-2"]
    assert entity.scopes[0].scope == ScopeLevel.API_SURFACE
    assert entity.entities[1].role == EntityRole.CO_REQUIRED
    assert entity.steps[0].requires == [1]
    assert len(entity.steps) == 2
    assert len(entity.entities) == 2
    assert len(entity.scopes) == 2
    dumped = batch.model_dump()
    assert MigrationEntitiesBatch.model_validate(dumped) == batch


def test_enum_string_equality() -> None:
    assert EntityKind.CLASS == "class"
    assert EntityRole.CO_REQUIRED == "co-required"
    assert ScopeLevel.API_SURFACE == "api-surface"


def test_sortable_version_formula() -> None:
    assert sortable_version("3.2.1") == 3_002_001
    assert sortable_version("17.0") == 17_000_000
    with pytest.raises(ValueError, match="Cannot parse version"):
        sortable_version("bad")


def test_source_section_map_completeness() -> None:
    sections = [
        "breaking_change",
        "security_fix",
        "component_upgrade",
        "security_config",
        "behavioral",
        "deprecation",
        "new_capability",
    ]
    for section in sections:
        assert section in SOURCE_SECTION_TO_RULE_TYPE
