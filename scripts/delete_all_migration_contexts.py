"""Delete MigrationContext nodes from the graph (and their relationships).

Removes all runtime migration session state: UPGRADES_FROM/TO edges to Version nodes,
STEP_OUTCOME edges to MigrationStep nodes, and context properties. Does not delete
Version, MigrationRule, MigrationStep, or any other graph content.

Usage:
  # List contexts (no changes)
  python scripts/delete_all_migration_contexts.py

  # Delete every MigrationContext
  python scripts/delete_all_migration_contexts.py --yes

  # Delete contexts for one project only
  python scripts/delete_all_migration_contexts.py --project-id paysafe-wallet-switch --yes

Requires NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD (same as the MCP server).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from migration_oracle.graph.driver import close_driver, read_session, write_session

_LIST_CONTEXTS = """
MATCH (ctx:MigrationContext)
WHERE $project_id IS NULL OR ctx.projectId = $project_id
RETURN elementId(ctx) AS id,
       ctx.projectId AS projectId,
       ctx.fromVersion AS fromVersion,
       ctx.toVersion AS toVersion,
       ctx.framework AS framework,
       ctx.status AS status,
       toString(ctx.createdAt) AS createdAt
ORDER BY ctx.projectId, ctx.createdAt DESC
"""

_COUNT_CONTEXTS = """
MATCH (ctx:MigrationContext)
WHERE $project_id IS NULL OR ctx.projectId = $project_id
RETURN count(ctx) AS count
"""

_DELETE_CONTEXTS = """
MATCH (ctx:MigrationContext)
WHERE $project_id IS NULL OR ctx.projectId = $project_id
DETACH DELETE ctx
"""


def list_contexts(project_id: str | None) -> list[dict]:
    with read_session() as session:
        return [
            dict(row)
            for row in session.run(_LIST_CONTEXTS, project_id=project_id)
        ]


def count_contexts(project_id: str | None) -> int:
    with read_session() as session:
        record = session.run(_COUNT_CONTEXTS, project_id=project_id).single()
    return int(record["count"]) if record else 0


def delete_contexts(project_id: str | None) -> None:
    with write_session() as session:
        session.run(_DELETE_CONTEXTS, project_id=project_id)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete MigrationContext nodes from Neo4j (runtime session state only)."
    )
    parser.add_argument(
        "--project-id",
        help="Only delete contexts for this projectId (default: all projects).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Perform deletion without prompting (required to delete).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    project_id = args.project_id.strip() if args.project_id else None

    try:
        contexts = list_contexts(project_id)
    except Exception as exc:
        print(f"Failed to query graph: {exc}", file=sys.stderr)
        return 1

    if not contexts:
        scope = f"projectId={project_id!r}" if project_id else "all projects"
        print(f"No MigrationContext nodes found ({scope}).")
        return 0

    print(f"Found {len(contexts)} MigrationContext node(s):")
    for row in contexts:
        print(
            f"  {row['id']}  {row['projectId']}  "
            f"{row['fromVersion']} → {row['toVersion']}  "
            f"status={row['status']}  framework={row.get('framework')}"
        )

    if not args.yes:
        print("\nNo changes made. Re-run with --yes to delete these contexts.")
        return 0

    try:
        delete_contexts(project_id)
        remaining = count_contexts(project_id)
    except Exception as exc:
        print(f"Delete failed: {exc}", file=sys.stderr)
        return 1

    if remaining != 0:
        print(
            f"Warning: expected 0 contexts after delete, found {remaining}.",
            file=sys.stderr,
        )
        return 1

    scope = f"for projectId={project_id!r}" if project_id else "in the graph"
    print(f"Deleted {len(contexts)} MigrationContext node(s) {scope}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        close_driver()
