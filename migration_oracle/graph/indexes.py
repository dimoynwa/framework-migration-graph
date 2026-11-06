"""Idempotent graph index and constraint DDL."""

import logging

import neo4j
from neo4j.exceptions import ClientError, CypherSyntaxError, DatabaseError

logger = logging.getLogger(__name__)

# The entity merge identity is the canonical `key` (spec 025 FR-4.3). `name`
# stays matchable but is no longer unique — `VERSION` exists in several Angular
# entry points — so it gets a plain index instead of a uniqueness constraint.
_DROPS = [
    "DROP CONSTRAINT class_name IF EXISTS",
    "DROP CONSTRAINT property_name IF EXISTS",
    "DROP CONSTRAINT dependency_name IF EXISTS",
]

_INDEXES = [
    "CREATE CONSTRAINT version_unique IF NOT EXISTS FOR (v:Version) REQUIRE (v.framework, v.version) IS UNIQUE",
    "CREATE CONSTRAINT migration_rule_id IF NOT EXISTS FOR (r:MigrationRule) REQUIRE r.ruleId IS UNIQUE",
    "CREATE CONSTRAINT class_key IF NOT EXISTS FOR (c:Class) REQUIRE c.key IS UNIQUE",
    "CREATE CONSTRAINT property_key IF NOT EXISTS FOR (p:ApplicationProperty) REQUIRE p.key IS UNIQUE",
    "CREATE CONSTRAINT dependency_key IF NOT EXISTS FOR (d:Dependency) REQUIRE d.key IS UNIQUE",
    "CREATE CONSTRAINT template_syntax_key IF NOT EXISTS FOR (t:TemplateSyntax) REQUIRE t.key IS UNIQUE",
    "CREATE CONSTRAINT diagnostic_code_key IF NOT EXISTS FOR (d:DiagnosticCode) REQUIRE d.key IS UNIQUE",
    "CREATE CONSTRAINT breaking_scope_pair IF NOT EXISTS FOR (bs:BreakingScope) REQUIRE (bs.scope, bs.severity) IS UNIQUE",
    "CREATE CONSTRAINT migration_context_key IF NOT EXISTS FOR (mc:MigrationContext) REQUIRE (mc.projectId, mc.fromVersion, mc.toVersion) IS UNIQUE",
    "CREATE INDEX version_sortable IF NOT EXISTS FOR (v:Version) ON (v.sortableVersion)",
    "CREATE INDEX version_framework IF NOT EXISTS FOR (v:Version) ON (v.framework)",
    "CREATE INDEX class_name_index IF NOT EXISTS FOR (c:Class) ON (c.name)",
    "CREATE INDEX property_name_index IF NOT EXISTS FOR (p:ApplicationProperty) ON (p.name)",
    "CREATE INDEX dependency_name_index IF NOT EXISTS FOR (d:Dependency) ON (d.name)",
    "CREATE FULLTEXT INDEX rule_statement IF NOT EXISTS FOR (r:MigrationRule) ON EACH [r.statement]",
    "CREATE FULLTEXT INDEX step_instruction IF NOT EXISTS FOR (s:MigrationStep) ON EACH [s.instruction, s.summary]",
    "CREATE INDEX step_rule_index IF NOT EXISTS FOR (s:MigrationStep) ON (s.ruleId, s.stepIndex)",
    "CREATE INDEX step_effort IF NOT EXISTS FOR (s:MigrationStep) ON (s.effort)",
    "CREATE INDEX breaking_scope_scope IF NOT EXISTS FOR (bs:BreakingScope) ON (bs.scope)",
    "CREATE INDEX context_project IF NOT EXISTS FOR (mc:MigrationContext) ON (mc.projectId)",
    "CREATE FULLTEXT INDEX migration_text IF NOT EXISTS "
    "FOR (n:MigrationRule) ON EACH [n.statement, n.reason, n.solution]",
    "CREATE FULLTEXT INDEX openrewrite_recipe_description IF NOT EXISTS "
    "FOR (r:OpenRewriteRecipe) ON EACH [r.description, r.displayName]",
]

_EXPECTED_CONSTRAINTS = {
    "version_unique",
    "migration_rule_id",
    "class_key",
    "property_key",
    "dependency_key",
    "template_syntax_key",
    "diagnostic_code_key",
    "breaking_scope_pair",
    "migration_context_key",
}

_EXPECTED_INDEXES = {
    "version_sortable",
    "version_framework",
    "class_name_index",
    "property_name_index",
    "dependency_name_index",
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
    for statement in [*_DROPS, *_INDEXES]:
        try:
            with driver.session(default_access_mode=neo4j.WRITE_ACCESS) as session:
                session.run(statement)
        except (ClientError, CypherSyntaxError, DatabaseError) as exc:
            logger.warning(
                "Index DDL failed (continuing): %s — %s",
                statement,
                exc,
            )
