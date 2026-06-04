"""Graph population from MigrationEntitiesBatch."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from migration_oracle.graph.driver import get_driver, write_session
from migration_oracle.graph.indexes import ensure_indexes
from migration_oracle.graph.queries import pipeline as pipeline_queries
from migration_oracle.models.entities import (
    AffectedEntity,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
    MigrationEntity,
    MigrationStep,
    StepType,
)
from migration_oracle.models.graph import sortable_version

# Authoritative mapping owned by this module (see spec FR-003).
SOURCE_SECTION_TO_RULE_TYPE: dict[str, str] = {
    "breaking_change": "breaking",
    "security_fix": "mandatory_migration",
    "component_upgrade": "mandatory_migration",
    "security_config": "mandatory_migration",
    "behavioral": "behavioral",
    "deprecation": "deprecation",
    "new_capability": "behavioral",
}


class UnknownSourceSectionError(ValueError):
    """Raised when source_section is not in SOURCE_SECTION_TO_RULE_TYPE."""


@dataclass(frozen=True)
class PopulationResult:
    rules_written: int
    steps_written: int
    scopes_written: int
    entities_written: int
    version_created: bool
    skipped: bool = False


def derive_entity_classification(entity: MigrationEntity) -> str:
    if len(entity.steps) > 0:
        return "actionable"
    if len(entity.entities) > 0:
        return "incomplete"
    return "informational"


def rule_type_for(source_section: str) -> str:
    try:
        return SOURCE_SECTION_TO_RULE_TYPE[source_section]
    except KeyError as exc:
        raise UnknownSourceSectionError(
            f"Unrecognized source_section {source_section!r}"
        ) from exc


def _entity_label(kind: EntityKind) -> str:
    return {
        EntityKind.CLASS: "Class",
        EntityKind.PROPERTY: "ApplicationProperty",
        EntityKind.DEPENDENCY: "Dependency",
    }[kind]


def _edge_type(kind: EntityKind) -> str:
    return {
        EntityKind.CLASS: "AFFECTS_CLASS",
        EntityKind.PROPERTY: "AFFECTS_PROPERTY",
        EntityKind.DEPENDENCY: "AFFECTS_DEPENDENCY",
    }[kind]


def _replacement_pairs(entity: MigrationEntity) -> list[tuple[str, str, EntityKind]]:
    removed = [e for e in entity.entities if e.role == EntityRole.REMOVED]
    replacements = [e for e in entity.entities if e.role == EntityRole.REPLACEMENT]
    pairs: list[tuple[str, str, EntityKind]] = []
    for kind in EntityKind:
        removed_names = [e.name for e in removed if e.kind == kind]
        replacement_names = [e.name for e in replacements if e.kind == kind]
        for removed_name, replacement_name in product(removed_names, replacement_names):
            pairs.append((removed_name, replacement_name, kind))
    return pairs


def populate_graph(
    *,
    batch: MigrationEntitiesBatch,
    framework_display: str,
    to_version: str,
    raw_md_path: str,
    filtered_md_path: str,
    entities_json_path: str,
    dry_run: bool = False,
    skip_if_version_exists: bool = True,
) -> PopulationResult:
    if dry_run:
        return PopulationResult(0, 0, 0, 0, False, skipped=True)

    if skip_if_version_exists and pipeline_queries.version_exists(
        framework_display, to_version
    ):
        return PopulationResult(0, 0, 0, 0, False, skipped=True)

    sortable = sortable_version(to_version)
    rules_written = 0
    steps_written = 0
    scopes_written = 0
    entities_written = 0

    ensure_indexes(get_driver())
    pipeline_queries.merge_version(
        framework=framework_display,
        version=to_version,
        sortable_version=sortable,
    )

    with write_session() as session:
        for entity in batch.entities:
            _write_entity(
                session,
                entity=entity,
                framework_display=framework_display,
                to_version=to_version,
            )
            rules_written += 1
            steps_written += len(entity.steps)
            scopes_written += len(entity.scopes)
            entities_written += len(entity.entities)

    pipeline_queries.upsert_version_artifact_paths(
        framework=framework_display,
        version=to_version,
        raw_md_path=raw_md_path,
        filtered_md_path=filtered_md_path,
        entities_json_path=entities_json_path,
    )

    return PopulationResult(
        rules_written=rules_written,
        steps_written=steps_written,
        scopes_written=scopes_written,
        entities_written=entities_written,
        version_created=True,
    )


def _write_entity(
    session,
    *,
    entity: MigrationEntity,
    framework_display: str,
    to_version: str,
) -> None:
    source_url = (
        entity.source_url
        or f"pipeline://{framework_display}/{to_version}/{entity.title}"
    )
    rule_record = session.run(
        """
        MATCH (v:Version {framework: $framework, version: $version})
        MERGE (rule:MigrationRule {sourceUrl: $source_url})
        ON CREATE SET
          rule.statement = $reason,
          rule.title = $title,
          rule.jiraKeys = $jira_keys,
          rule.ruleType = $rule_type,
          rule.changeType = $change_type,
          rule.reasonType = $reason_type,
          rule.entityClassification = $classification,
          rule.subsystem = $subsystem
        ON MATCH SET
          rule.statement = $reason,
          rule.title = $title,
          rule.jiraKeys = $jira_keys,
          rule.ruleType = $rule_type,
          rule.changeType = $change_type,
          rule.reasonType = $reason_type,
          rule.entityClassification = $classification,
          rule.subsystem = $subsystem
        MERGE (v)-[:INCLUDES_RULE]->(rule)
        RETURN elementId(rule) AS rule_id
        """,
        framework=framework_display,
        version=to_version,
        source_url=source_url,
        reason=entity.reason,
        title=entity.title,
        jira_keys=entity.jira_keys,
        rule_type=rule_type_for(entity.source_section),
        change_type=entity.change_type,
        reason_type=entity.reason_type or "",
        classification=derive_entity_classification(entity),
        subsystem=entity.subsystem,
    ).single()
    rule_id = rule_record["rule_id"]

    for scope in entity.scopes:
        session.run(
            """
            MATCH (rule:MigrationRule)
            WHERE elementId(rule) = $rule_id
            MERGE (bs:BreakingScope {scope: $scope, severity: $severity})
            MERGE (rule)-[:HAS_SCOPE]->(bs)
            """,
            rule_id=rule_id,
            scope=scope.scope.value,
            severity=scope.severity.value,
        )

    for step in entity.steps:
        _write_step(session, rule_id=rule_id, step=step, entity=entity)

    for step in entity.steps:
        for prereq_index in step.requires:
            session.run(
                """
                MATCH (cur:MigrationStep {ruleId: $rule_id, stepIndex: $current})
                MATCH (pre:MigrationStep {ruleId: $rule_id, stepIndex: $prereq})
                MERGE (cur)-[:REQUIRES]->(pre)
                """,
                rule_id=rule_id,
                current=step.index,
                prereq=prereq_index,
            )

    for affected in entity.entities:
        _write_affected_entity(
            session,
            rule_id=rule_id,
            entity=entity,
            affected=affected,
            framework_display=framework_display,
            to_version=to_version,
        )

    for removed_name, replacement_name, kind in _replacement_pairs(entity):
        label = _entity_label(kind)
        session.run(
            f"""
            MATCH (old:{label} {{name: $removed_name}})
            MATCH (new:{label} {{name: $replacement_name}})
            MERGE (old)-[:REPLACED_BY]->(new)
            """,
            removed_name=removed_name,
            replacement_name=replacement_name,
        )


def _write_step(
    session,
    *,
    rule_id: str,
    step: MigrationStep,
    entity: MigrationEntity,
) -> None:
    session.run(
        """
        MERGE (s:MigrationStep {ruleId: $rule_id, stepIndex: $step_index})
        ON CREATE SET
          s.stepType = $step_type,
          s.summary = $summary,
          s.instruction = $instruction,
          s.effort = $effort,
          s.automatable = $automatable,
          s.verificationHint = $verification,
          s.cliOperation = $cli_operation
        ON MATCH SET
          s.stepType = $step_type,
          s.summary = $summary,
          s.instruction = $instruction,
          s.effort = $effort,
          s.automatable = $automatable,
          s.verificationHint = $verification,
          s.cliOperation = $cli_operation
        WITH s
        MATCH (rule:MigrationRule)
        WHERE elementId(rule) = $rule_id
        MERGE (rule)-[:REQUIRES_STEP]->(s)
        """,
        rule_id=rule_id,
        step_index=step.index,
        step_type=step.step_type.value,
        summary=step.summary,
        instruction=step.instruction,
        effort=step.effort.value,
        automatable=step.automatable,
        verification=step.verification,
        cli_operation=step.cli_operation,
    )

    if step.automatable:
        session.run(
            """
            MATCH (s:MigrationStep {ruleId: $rule_id, stepIndex: $step_index})
            MERGE (s)-[ab:AUTOMATED_BY]->(e:OpenRewriteRecipe {recipeId: $stub_id})
            ON CREATE SET
              ab.auto = false,
              ab.confidence = 0.0,
              ab.method = 'deterministic',
              ab.missingRequiredParams = []
            ON MATCH SET
              ab.auto = CASE WHEN e.verifiedBy IS NULL THEN false ELSE ab.auto END,
              ab.confidence = CASE WHEN e.verifiedBy IS NULL THEN 0.0 ELSE ab.confidence END,
              ab.method = CASE WHEN e.verifiedBy IS NULL THEN 'deterministic' ELSE ab.method END,
              ab.missingRequiredParams = CASE
                WHEN e.verifiedBy IS NULL THEN [] ELSE ab.missingRequiredParams
              END
            """,
            rule_id=rule_id,
            step_index=step.index,
            stub_id=f"stub:{rule_id}:{step.index}",
        )

    if step.step_type in (StepType.REMOVE, StepType.REPLACE, StepType.RENAME):
        for affected in entity.entities:
            edge = _edge_type(affected.kind)
            label = _entity_label(affected.kind)
            session.run(
                f"""
                MATCH (s:MigrationStep {{ruleId: $rule_id, stepIndex: $step_index}})
                MERGE (e:{label} {{name: $name}})
                MERGE (s)-[rel:{edge}]->(e)
                SET rel.role = $role
                """,
                rule_id=rule_id,
                step_index=step.index,
                name=affected.name,
                role=affected.role.value,
            )


def _write_affected_entity(
    session,
    *,
    rule_id: str,
    entity: MigrationEntity,
    affected: AffectedEntity,
    framework_display: str,
    to_version: str,
) -> None:
    label = _entity_label(affected.kind)
    edge = _edge_type(affected.kind)
    role = affected.role.value

    session.run(
        f"""
        MERGE (e:{label} {{name: $name}})
        WITH e
        MATCH (rule:MigrationRule)
        WHERE elementId(rule) = $rule_id
        MERGE (rule)-[rel:{edge}]->(e)
        SET rel.role = $role
        """,
        name=affected.name,
        rule_id=rule_id,
        role=role,
    )

    if affected.role == EntityRole.REMOVED:
        session.run(
            f"""
            MATCH (v:Version {{framework: $framework, version: $version}})
            MATCH (e:{label} {{name: $name}})
            MERGE (e)-[:REMOVED_IN]->(v)
            MERGE (v)-[:REMOVES]->(e)
            """,
            framework=framework_display,
            version=to_version,
            name=affected.name,
        )
    elif affected.role == EntityRole.REPLACEMENT:
        session.run(
            f"""
            MATCH (v:Version {{framework: $framework, version: $version}})
            MATCH (e:{label} {{name: $name}})
            MERGE (e)-[:INTRODUCED_IN]->(v)
            MERGE (v)-[:INTRODUCES]->(e)
            """,
            framework=framework_display,
            version=to_version,
            name=affected.name,
        )
    elif entity.source_section == "deprecation":
        session.run(
            f"""
            MATCH (v:Version {{framework: $framework, version: $version}})
            MATCH (e:{label} {{name: $name}})
            MERGE (e)-[:DEPRECATED_IN]->(v)
            MERGE (v)-[:DEPRECATES]->(e)
            """,
            framework=framework_display,
            version=to_version,
            name=affected.name,
        )


populate = populate_graph
