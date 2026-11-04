"""PaysafeMigrationOracle MCP server entry point."""

from __future__ import annotations

import os
from datetime import datetime, timezone
import logging
from pathlib import Path

from migration_oracle.mcp.config import MIGRATION_MODE

from neo4j.exceptions import ServiceUnavailable

from migration_oracle import config
from migration_oracle.graph.driver import get_driver
from migration_oracle.graph.indexes import ensure_indexes
from migration_oracle.mcp.instance import mcp
from migration_oracle.mcp.paysafe_lifespan import paysafe_cache_lifespan

logger = logging.getLogger(__name__)
_SERVER_STARTED_AT: str = datetime.now(timezone.utc).isoformat()
_GIT_SHA: str = os.environ.get("GIT_SHA", "")
_GIT_BRANCH: str = os.environ.get("GIT_BRANCH", "")
_FEATURE_TAGS: str = os.environ.get("FEATURE_TAGS", "")

# Re-exported for spec wiring reference; FastMCP uses paysafe_cache_lifespan via instance.py.
__all__ = [
    "paysafe_cache_lifespan",
    "mcp",
    "startup",
    "bundle_to_skill_uri",
]


def get_server_started_at() -> str:
    return _SERVER_STARTED_AT


_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

_STAGE_BUNDLES = {
    "research": "framework-migration-research",
    "plan": "framework-migration-plan",
    "gap-check": "framework-migration-gap-check",
    "clarify": "framework-migration-clarify",
    "preview": "framework-migration-preview",
    "execute": "framework-migration-execute",
}


def _read_skill(filename: str) -> str:
    return (_SKILLS_DIR / filename).read_text(encoding="utf-8")


def bundle_to_skill_uri(bundle: str) -> str:
    """Map a bundle directory name to its MCP skill resource URI."""
    return f"skill://{bundle}/main"


@mcp.resource("skill://framework-migration-research/main")
def skill_framework_migration_research() -> str:
    """Research stage — knowledge query and research.md checkpoint emission."""
    return _read_skill("framework-migration/research.md")


@mcp.resource("skill://framework-migration-plan/main")
def skill_framework_migration_plan() -> str:
    """Plan stage — codebase scan, knowledge queries, and file emission."""
    return _read_skill("framework-migration/plan.md")


@mcp.resource("skill://framework-migration-gap-check/main")
def skill_framework_migration_gap_check() -> str:
    """Gap-check stage — mechanical plan audit."""
    return _read_skill("framework-migration/gap-check.md")


@mcp.resource("skill://framework-migration-clarify/main")
def skill_framework_migration_clarify() -> str:
    """Clarify stage — optional human plan amendments."""
    return _read_skill("framework-migration/clarify.md")


@mcp.resource("skill://framework-migration-preview/main")
def skill_framework_migration_preview() -> str:
    """Preview stage — read-only customer-facing plan rendering."""
    return _read_skill("framework-migration/preview.md")


@mcp.resource("skill://framework-migration-execute/main")
def skill_framework_migration_execute() -> str:
    """Execute stage — apply pending steps."""
    return _read_skill("framework-migration/execute.md")


@mcp.resource("skill://framework-migration-plan/scanning")
def skill_framework_migration_plan_scanning() -> str:
    """Codebase scanning patterns for entity extraction."""
    return _read_skill("framework-migration/scanning.md")


@mcp.resource("skill://framework-migration-plan/version-map")
def skill_framework_migration_plan_version_map() -> str:
    """Framework version map and toolchain gates."""
    return _read_skill("framework-migration/version-map.md")


@mcp.resource("skill://framework-migration-execute/rollback")
def skill_framework_migration_execute_rollback() -> str:
    """Build-failure rollback procedure for the migration harness."""
    return _read_skill("framework-migration/rollback.md")


@mcp.prompt()
def start_migration(
    framework: str,
    current_version: str,
    target_version: str,
    project_id: str,
    stage: str = "plan",
) -> str:
    """Start a split migration harness session for a project.

    framework: e.g. 'Spring Boot', 'WildFly', 'Quarkus'
    current_version: the version the project is migrating FROM, e.g. '2.7'
    target_version: the version the project is migrating TO, e.g. '3.2'
    project_id: unique project identifier (used in plan.md header)
    stage: one of research, plan, gap-check, clarify, preview, execute (default: plan)
    """
    stage = (stage or "plan").strip().lower()
    bundle = _STAGE_BUNDLES.get(stage, _STAGE_BUNDLES["plan"])
    skill_uri = bundle_to_skill_uri(bundle)
    folder = f"ps-migration/{framework.lower().replace(' ', '-')}-{current_version}-to-{target_version}"
    return (
        f"Load {skill_uri}.\n\n"
        f"Run the '{stage}' stage of the file-state migration harness for project "
        f"'{project_id}' migrating {framework} from {current_version} to {target_version}.\n\n"
        f"Migration folder: {folder}/\n"
        f"Stages: research (optional) → plan → gap-check → clarify (optional) → "
        f"preview (optional) → execute.\n"
        f"Progress lives in research.md, plan.md, tasks.md, and verification.md — "
        f"not in the graph.\n\n"
        f"Active stage: {stage}"
    )


@mcp.prompt()
def resume_migration(migration_folder: str, stage: str = "execute") -> str:
    """Resume a file-state migration from an existing ps-migration/ folder.

    migration_folder: path to ps-migration/{framework}-{from}-to-{to}/ in the consumer repo.
    stage: one of research, plan, gap-check, clarify, preview, execute (default: execute).
    """
    stage = (stage or "execute").strip().lower()
    bundle = _STAGE_BUNDLES.get(stage, _STAGE_BUNDLES["execute"])
    skill_uri = bundle_to_skill_uri(bundle)
    return (
        f"Load {skill_uri}.\n\n"
        f"Resume migration at the '{stage}' stage.\n\n"
        f"Read state from: {migration_folder}/\n"
        f"  - research.md (optional knowledge checkpoint)\n"
        f"  - plan.md (strategy and rule ledger)\n"
        f"  - tasks.md (work queue and inline status)\n"
        f"  - verification.md (completion gate)\n\n"
        f"For execute: pick up from the first task with Status: pending in tasks.md."
    )


@mcp.prompt()
def migration_workflow_prompt() -> str:
    """Zero-parameter fallback for clients that do not support parameterized prompts.

    Prefer start_migration or resume_migration when the client supports parameters.
    """
    return (
        "Load skill://framework-migration-plan/main.\n\n"
        "I want to migrate this project from [framework] [current_version] "
        "to [target_version].\n"
        "Project ID: [your-project-id]\n\n"
        "Run the six-stage file-state migration harness:\n"
        "- research (optional): scan codebase, query graph, emit research.md checkpoint\n"
        "- plan: scan codebase, query graph knowledge (or consume research.md), "
        "emit ps-migration/ files\n"
        "- gap-check: mechanical audit of plan.md and tasks.md (file-only)\n"
        "- clarify (optional): resolve Relevance-Index entries in tasks.md\n"
        "- preview (optional): read-only plan grouped by risk\n"
        "- execute: work tasks sequentially, update Status in tasks.md"
    )


# Register tools via import side effects.
from migration_oracle.mcp.tools import install  # noqa: E402, F401
from migration_oracle.mcp.tools import paysafe  # noqa: E402, F401
from migration_oracle.mcp.tools import search  # noqa: E402, F401
from migration_oracle.mcp.tools import upgrade  # noqa: E402, F401

if MIGRATION_MODE == "full":
    from migration_oracle.mcp.tools import artifacts  # noqa: E402, F401
    from migration_oracle.mcp.tools import community  # noqa: E402, F401
    from migration_oracle.mcp.tools import deprecation  # noqa: E402, F401
    from migration_oracle.mcp.tools import schema  # noqa: E402, F401

from migration_oracle.mcp.stage_gating import STAGE_TOOL_ALLOWLIST, apply_stage_gating  # noqa: E402

apply_stage_gating(mcp)


def get_registered_tool_names() -> set[str]:
    """Return tool names registered for the active MCP_ACTIVE_STAGE (verification helper)."""
    stage = os.environ.get("MCP_ACTIVE_STAGE", "").strip().lower()
    if not stage:
        raise ValueError(
            "MCP_ACTIVE_STAGE must be set to one of: "
            + ", ".join(sorted(STAGE_TOOL_ALLOWLIST))
        )
    if stage not in STAGE_TOOL_ALLOWLIST:
        raise ValueError(
            f"Invalid MCP_ACTIVE_STAGE={stage!r}; valid options are: "
            + ", ".join(sorted(STAGE_TOOL_ALLOWLIST))
        )
    return set(mcp._tool_manager._tools.keys())


def _registered_tool_count() -> int:
    return len(mcp._tool_manager._tools)


logger.info(
    "Migration Oracle starting — mode=%s tools=%d",
    MIGRATION_MODE,
    _registered_tool_count(),
)


def startup() -> None:
    """Ordered startup: config (import time) → connectivity → indexes → model warm-up."""
    driver = get_driver()
    with driver.session() as session:
        session.run("RETURN 1").single()
    fast_start = os.environ.get("MCP_FAST_START", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if fast_start:
        logger.info("MCP_FAST_START set — skipping index ensure and embedding warm-up")
    else:
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
