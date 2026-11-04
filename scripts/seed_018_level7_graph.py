"""Minimal Neo4j seed for specs/018 Level 7 functional verification."""

from __future__ import annotations

from migration_oracle.graph.driver import write_session

_SEED = """
// Versions for Spring Boot 3.4.0 -> 3.5.0 (and 3.6.0 for mismatch tests)
MERGE (v340:Version {framework: "Spring Boot", version: "3.4.0"})
SET v340.sortableVersion = 3004000, v340.status = "active"
MERGE (v350:Version {framework: "Spring Boot", version: "3.5.0"})
SET v350.sortableVersion = 3005000, v350.status = "active"
MERGE (v360:Version {framework: "Spring Boot", version: "3.6.0"})
SET v360.sortableVersion = 3006000, v360.status = "active"

MERGE (rule:MigrationRule {ruleId: "MR-L7-001"})
SET rule.statement = "Replace deprecated RestControllerAdvice pattern",
    rule.ruleType = "breaking",
    rule.title = "RestControllerAdvice migration",
    rule.entityClassification = "actionable"

MERGE (scope:BreakingScope {scope: "api-surface", severity: "high"})
MERGE (rule)-[:HAS_SCOPE]->(scope)

MERGE (cls:Class {name: "org.springframework.web.bind.annotation.RestController"})
MERGE (rule)-[:AFFECTS_CLASS]->(cls)

MERGE (step:MigrationStep {stepId: "MS-L7-001"})
SET step.stepType = "replace",
    step.instruction = "Rename @RestControllerAdvice to @ControllerAdvice with explicit basePackages.",
    step.effort = "mechanical",
    step.automatable = true,
    step.summary = "Update RestControllerAdvice annotation"
MERGE (rule)-[:REQUIRES_STEP]->(step)

MERGE (v350)-[:INCLUDES_RULE]->(rule)

MERGE (rule2:MigrationRule {ruleId: "MR-L7-002"})
SET rule2.statement = "javax.servlet API affects codebase without prescribed fix",
    rule2.ruleType = "deprecation",
    rule2.title = "Servlet API incomplete",
    rule2.entityClassification = "incomplete"

MERGE (scope2:BreakingScope {scope: "runtime", severity: "medium"})
MERGE (rule2)-[:HAS_SCOPE]->(scope2)
MERGE (cls2:Class {name: "javax.servlet.http.HttpServlet"})
MERGE (rule2)-[:AFFECTS_CLASS]->(cls2)
MERGE (v350)-[:INCLUDES_RULE]->(rule2)

RETURN count(rule) + count(rule2) AS rules_seeded
"""


def main() -> None:
    with write_session() as session:
        record = session.run(_SEED).single()
    print(f"Seeded Level-7 graph (rules={record['rules_seeded']})")


if __name__ == "__main__":
    main()
