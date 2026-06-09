"""Idempotent graph index and constraint DDL."""

import logging

import neo4j
from neo4j.exceptions import ClientError, CypherSyntaxError, DatabaseError

logger = logging.getLogger(__name__)

_INDEXES = [
    "CREATE CONSTRAINT version_unique IF NOT EXISTS FOR (v:Version) REQUIRE (v.framework, v.version) IS UNIQUE",
    "CREATE CONSTRAINT migration_rule_id IF NOT EXISTS FOR (r:MigrationRule) REQUIRE r.ruleId IS UNIQUE",
    "CREATE CONSTRAINT class_name IF NOT EXISTS FOR (c:Class) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT property_name IF NOT EXISTS FOR (p:ApplicationProperty) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT dependency_name IF NOT EXISTS FOR (d:Dependency) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT breaking_scope_pair IF NOT EXISTS FOR (bs:BreakingScope) REQUIRE (bs.scope, bs.severity) IS UNIQUE",
    "CREATE CONSTRAINT migration_context_key IF NOT EXISTS FOR (mc:MigrationContext) REQUIRE (mc.projectId, mc.fromVersion, mc.toVersion) IS UNIQUE",
    "CREATE INDEX version_sortable IF NOT EXISTS FOR (v:Version) ON (v.sortableVersion)",
    "CREATE INDEX version_framework IF NOT EXISTS FOR (v:Version) ON (v.framework)",
    "CREATE FULLTEXT INDEX rule_statement IF NOT EXISTS FOR (r:MigrationRule) ON EACH [r.statement]",
    "CREATE FULLTEXT INDEX step_instruction IF NOT EXISTS FOR (s:MigrationStep) ON EACH [s.instruction, s.summary]",
    "CREATE INDEX step_rule_index IF NOT EXISTS FOR (s:MigrationStep) ON (s.ruleId, s.stepIndex)",
    "CREATE INDEX step_effort IF NOT EXISTS FOR (s:MigrationStep) ON (s.effort)",
    "CREATE INDEX breaking_scope_scope IF NOT EXISTS FOR (bs:BreakingScope) ON (bs.scope)",
    "CREATE INDEX context_project IF NOT EXISTS FOR (mc:MigrationContext) ON (mc.projectId)",
    "CREATE FULLTEXT INDEX migration_text IF NOT EXISTS "
    "FOR (n:MigrationRule|CommunityInsight) ON EACH [n.statement, n.reason, n.solution]",
    "CREATE FULLTEXT INDEX openrewrite_recipe_description IF NOT EXISTS "
    "FOR (r:OpenRewriteRecipe) ON EACH [r.description, r.displayName]",
]

_EXPECTED_CONSTRAINTS = {
    "version_unique",
    "migration_rule_id",
    "class_name",
    "property_name",
    "dependency_name",
    "breaking_scope_pair",
    "migration_context_key",
}

_EXPECTED_INDEXES = {
    "version_sortable",
    "version_framework",
    "rule_statement",
    "step_instruction",
    "step_rule_index",
    "step_effort",
    "breaking_scope_scope",
    "context_project",
    "migration_text",
    "openrewrite_recipe_description",
}


def ensure_indexes(driver: neo4j.Driver) -> None:
    """Apply all index/constraint DDL statements; log and continue on failure."""
    for statement in _INDEXES:
        try:
            with driver.session(default_access_mode=neo4j.WRITE_ACCESS) as session:
                session.run(statement)
        except (ClientError, CypherSyntaxError, DatabaseError) as exc:
            logger.warning(
                "Index DDL failed (continuing): %s — %s",
                statement,
                exc,
            )
