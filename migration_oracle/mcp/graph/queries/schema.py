"""Read-only Cypher execution and schema constants."""

from __future__ import annotations

import re

from migration_oracle.graph.driver import read_session

MUTATION_KEYWORDS = ["CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP"]

GRAPH_SCHEMA_MD = """# Migration Knowledge Graph Schema

## Node labels
- **Version**: `framework`, `version`, `sortableVersion`
- **MigrationRule**: `statement`, `ruleType`, `actionStep`, `sourceUrl`, `entityClassification`
- **MigrationStep**: `stepType`, `summary`, `instruction`, `effort`, `automatable`, `verificationHint`
- **BreakingScope**: `scope`, `severity`
- **MigrationContext**: `projectId`, `fromVersion`, `toVersion`, `status`, `completedSteps`, `skippedSteps`, `failedSteps`
- **Class**, **ApplicationProperty**, **Dependency**, **OpenRewriteRecipe**

## Key relationships
- Version -[:INCLUDES_RULE]-> MigrationRule
- MigrationRule -[:REQUIRES_STEP]-> MigrationStep
- MigrationRule -[:HAS_SCOPE]-> BreakingScope
- MigrationStep -[:AUTOMATED_BY]-> OpenRewriteRecipe
- MigrationContext -[:UPGRADES_FROM|UPGRADES_TO]-> Version
- Entity -[:DEPRECATED_IN|REMOVED_IN|REPLACED_BY]-> ...

## Indexes
- Full-text: `migration_text`, `openrewrite_recipe_description`
- Vector: `migration_knowledge_vector_mr`, `openrewrite_recipe_vector`
"""


def check_mutation(query: str) -> str | None:
    upper = query.upper()
    for keyword in MUTATION_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            return keyword
    if upper.strip().startswith("CALL DB"):
        return "CALL db"
    return None


def execute_read_cypher(query: str, params: dict | None = None) -> list[dict]:
    with read_session() as session:
        return [dict(row) for row in session.run(query, params or {})]
