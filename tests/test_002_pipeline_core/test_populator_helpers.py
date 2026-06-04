"""Tests for entity classification derivation."""

from migration_oracle.models.entities import (
    AffectedEntity,
    EntityKind,
    EntityRole,
    MigrationEntity,
    MigrationStep,
    Effort,
    StepType,
)
from migration_oracle.pipeline.populator import derive_entity_classification


def test_actionable_when_steps_present() -> None:
    entity = MigrationEntity(
        source_section="breaking_change",
        title="t",
        change_type="breaking_change",
        reason="r",
        steps=[
            MigrationStep(
                index=0,
                step_type=StepType.VERIFY,
                summary="verify",
                instruction="do it",
                effort=Effort.MODERATE,
                automatable=False,
                requires=[],
                verification="ok",
            )
        ],
    )
    assert derive_entity_classification(entity) == "actionable"


def test_incomplete_when_entities_only() -> None:
    entity = MigrationEntity(
        source_section="behavioral",
        title="t",
        change_type="behavior_change",
        reason="r",
        entities=[
            AffectedEntity(kind=EntityKind.CLASS, name="Foo", role=EntityRole.MENTIONED)
        ],
    )
    assert derive_entity_classification(entity) == "incomplete"


def test_informational_when_empty() -> None:
    entity = MigrationEntity(
        source_section="behavioral",
        title="t",
        change_type="behavior_change",
        reason="r",
    )
    assert derive_entity_classification(entity) == "informational"
