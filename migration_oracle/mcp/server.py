"""PaysafeMigrationOracle MCP server entry point."""

from __future__ import annotations

import logging
from pathlib import Path

from neo4j.exceptions import ServiceUnavailable

from migration_oracle import config
from migration_oracle.graph.driver import get_driver
from migration_oracle.graph.indexes import ensure_indexes
from migration_oracle.mcp.instance import mcp

logger = logging.getLogger(__name__)
_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _read_skill(filename: str) -> str:
    return (_SKILLS_DIR / filename).read_text(encoding="utf-8")


@mcp.resource("skill://framework-migration/main")
def skill_framework_migration_main() -> str:
    """Four-loop migration harness skill."""
    return _read_skill("framework_migration_main.md")


@mcp.resource("skill://framework-migration/scanning")
def skill_framework_migration_scanning() -> str:
    """Codebase scanning patterns for entity extraction."""
    return _read_skill("framework_migration_scanning.md")


@mcp.resource("skill://framework-migration/plan-format")
def skill_framework_migration_plan_format() -> str:
    """Migration plan output format reference."""
    return _read_skill("framework_migration_plan_format.md")


@mcp.resource("skill://framework-migration/version-map")
def skill_framework_migration_version_map() -> str:
    """Framework version map and toolchain gates."""
    return _read_skill("framework_migration_version_map.md")


@mcp.resource("skill://framework-migration/rollback")
def skill_framework_migration_rollback() -> str:
    """Build-failure rollback procedure for the migration harness."""
    return _read_skill("framework_migration_rollback.md")


@mcp.prompt()
def start_migration(
    framework: str,
    current_version: str,
    target_version: str,
    project_id: str,
) -> str:
    """Start a four-loop migration harness for a project.

    framework: e.g. 'Spring Boot', 'WildFly', 'Quarkus'
    current_version: the version the project is migrating FROM, e.g. '2.7'
    target_version: the version the project is migrating TO, e.g. '3.2'
    project_id: unique project identifier used to create or resume a MigrationContext
    """
    return (
        f"Load skill://framework-migration/main.\n\n"
        f"Migrate project '{project_id}' from {framework} {current_version} "
        f"to {framework} {target_version}.\n\n"
        f"Run the four-loop migration harness:\n"
        f"- Loop I: scan the codebase, call create_migration_context\n"
        f"- Loop II: query the graph in scope-gated tiers "
        f"(api-surface → runtime → config/build → test)\n"
        f"- Loop III: execute each pending step (auto or manual; ask me to confirm manual steps)\n"
        f"- Loop IV: submit new insights via submit_migration_insight, "
        f"then call close_migration_context"
    )


@mcp.prompt()
def resume_migration(context_id: str) -> str:
    """Resume a four-loop migration harness from an existing MigrationContext.

    context_id: the UUID returned by create_migration_context or
                get_pending_steps from a previous session.
    """
    return (
        f"Load skill://framework-migration/main.\n\n"
        f"Resume migration context '{context_id}'.\n\n"
        f"Call get_pending_steps(context_id='{context_id}') to see what remains.\n"
        f"Continue from Loop III: execute each pending step, then run Loop IV "
        f"(submit insights, close context)."
    )


@mcp.prompt()
def migration_workflow_prompt() -> str:
    """Zero-parameter fallback for clients that do not support parameterized prompts.

    Prefer start_migration or resume_migration when the client supports parameters.
    """
    return (
        "Load skill://framework-migration/main.\n\n"
        "I want to migrate this project from [framework] [current_version] "
        "to [target_version].\n"
        "Project ID: [your-project-id]\n\n"
        "Run the four-loop migration harness:\n"
        "- Loop I: scan the codebase, create or resume a migration context\n"
        "- Loop II: query the graph in scope-gated tiers "
        "(api-surface → runtime → config/build → test)\n"
        "- Loop III: execute each pending step (auto or manual)\n"
        "- Loop IV: submit any new insights, close the context"
    )


# Register tools via import side effects.
from migration_oracle.mcp.tools import (  # noqa: E402, F401
    artifacts,
    community,
    context,
    deprecation,
    install,
    paysafe,
    schema,
    search,
    upgrade,
)


def startup() -> None:
    """Ordered startup: config (import time) → connectivity → indexes → model warm-up."""
    driver = get_driver()
    with driver.session() as session:
        session.run("RETURN 1").single()
    ensure_indexes(driver)
    try:
        from migration_oracle.mcp.tools.search import get_embedding_model
        get_embedding_model()
        logger.info("Embedding model warm-up complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding model warm-up skipped: %s", exc)
    logger.info(
        "PaysafeMigrationOracle ready — transport=%s",
        config.MCP_TRANSPORT,
    )


if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    transport = config.MCP_TRANSPORT
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError(f"Unsupported MCP_TRANSPORT: {transport}")
    startup()
    mcp.settings.host = config.MCP_HOST
    mcp.settings.port = config.MCP_PORT
    if transport == "streamable-http":
        mcp.settings.stateless_http = config.MCP_STATELESS_HTTP
    try:
        mcp.run(transport=transport)
    except ServiceUnavailable:
        raise
