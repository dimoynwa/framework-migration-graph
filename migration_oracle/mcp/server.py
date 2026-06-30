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
    "determine_resume_bundle",
    "bundle_to_skill_uri",
]


def get_server_started_at() -> str:
    return _SERVER_STARTED_AT


_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

_STAGE_BUNDLES = {
    "plan": "framework-migration-plan",
    "gap-check": "framework-migration-gap-check",
    "clarify": "framework-migration-clarify",
    "preview": "framework-migration-preview",
    "execute": "framework-migration-execute",
    "feedback": "framework-migration-feedback",
}

_CLOSED_STATUSES = frozenset({"complete", "partial", "abandoned"})


def _read_skill(filename: str) -> str:
    return (_SKILLS_DIR / filename).read_text(encoding="utf-8")


def bundle_to_skill_uri(bundle: str) -> str:
    """Map a bundle directory name to its MCP skill resource URI."""
    return f"skill://{bundle}/main"


def determine_resume_bundle(ctx: dict, *, pending_count: int) -> str | None:
    """Return the bundle name to load for resume_migration, or None if closed."""
    status = (ctx.get("status") or "").strip().lower()
    if status in _CLOSED_STATUSES:
        return None

    counts = ctx.get("outcome_counts") or {}
    total_outcomes = sum(
        counts.get(k, 0)
        for k in ("completed", "failed", "skipped", "deferred", "excluded")
    )

    if (
        ctx.get("has_gap_check_flags")
        and counts.get("excluded", 0) == 0
        and counts.get("completed", 0) == 0
        and counts.get("failed", 0) == 0
    ):
        return _STAGE_BUNDLES["clarify"]

    if total_outcomes == 0:
        return _STAGE_BUNDLES["gap-check"]

    if counts.get("failed", 0) > 0 or counts.get("deferred", 0) > 0:
        return _STAGE_BUNDLES["execute"]

    accounted = (
        counts.get("completed", 0)
        + counts.get("excluded", 0)
        + counts.get("failed", 0)
        + counts.get("skipped", 0)
    )
    total_steps = pending_count + total_outcomes
    if total_steps > 0 and accounted == total_steps:
        return _STAGE_BUNDLES["feedback"]

    return _STAGE_BUNDLES["execute"]


def _resolve_context_for_resume(context_id: str) -> tuple[dict | None, int, str | None]:
    """Load context row and pending step count for resume stage determination."""
    from migration_oracle.mcp.graph.queries import context as context_queries

    row = context_queries.get_context_by_id(context_id=context_id)
    if row is None:
        return None, 0, f"Context '{context_id}' not found"
    pending = context_queries.get_pending_steps(context_id=context_id)
    ctx = {
        "id": row.get("id") or context_id,
        "status": row.get("status") or "",
        "outcome_counts": {
            "completed": row.get("completed_count") or 0,
            "failed": row.get("failed_count") or 0,
            "skipped": row.get("skipped_count") or 0,
            "deferred": row.get("deferred_count") or 0,
            "excluded": row.get("excluded_count") or 0,
        },
        "has_gap_check_flags": bool(row.get("has_gap_check_flags")),
    }
    return ctx, len(pending), None


@mcp.resource("skill://framework-migration-plan/main")
def skill_framework_migration_plan() -> str:
    """Plan stage — context creation and scope-gated queries."""
    return _read_skill("framework_migration_plan.md")


@mcp.resource("skill://framework-migration-gap-check/main")
def skill_framework_migration_gap_check() -> str:
    """Gap-check stage — mechanical plan audit."""
    return _read_skill("framework_migration_gap_check.md")


@mcp.resource("skill://framework-migration-clarify/main")
def skill_framework_migration_clarify() -> str:
    """Clarify stage — optional human plan amendments."""
    return _read_skill("framework_migration_clarify.md")


@mcp.resource("skill://framework-migration-preview/main")
def skill_framework_migration_preview() -> str:
    """Preview stage — read-only customer-facing plan rendering."""
    return _read_skill("framework_migration_preview.md")


@mcp.resource("skill://framework-migration-execute/main")
def skill_framework_migration_execute() -> str:
    """Execute stage — apply pending steps."""
    return _read_skill("framework_migration_execute.md")


@mcp.resource("skill://framework-migration-feedback/main")
def skill_framework_migration_feedback() -> str:
    """Feedback stage — insights and close."""
    return _read_skill("framework_migration_feedback.md")


@mcp.resource("skill://framework-migration-plan/scanning")
def skill_framework_migration_plan_scanning() -> str:
    """Codebase scanning patterns for entity extraction."""
    return _read_skill("framework_migration_scanning.md")


@mcp.resource("skill://framework-migration-plan/version-map")
def skill_framework_migration_plan_version_map() -> str:
    """Framework version map and toolchain gates."""
    return _read_skill("framework_migration_version_map.md")


@mcp.resource("skill://framework-migration-execute/rollback")
def skill_framework_migration_execute_rollback() -> str:
    """Build-failure rollback procedure for the migration harness."""
    return _read_skill("framework_migration_rollback.md")


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
    project_id: unique project identifier used to create or resume a MigrationContext
    stage: one of plan, gap-check, clarify, preview, execute, feedback (default: plan)
    """
    stage = (stage or "plan").strip().lower()
    bundle = _STAGE_BUNDLES.get(stage, _STAGE_BUNDLES["plan"])
    skill_uri = bundle_to_skill_uri(bundle)
    return (
        f"Load {skill_uri}.\n\n"
        f"Run the '{stage}' stage of the split migration harness for project "
        f"'{project_id}' migrating {framework} from {current_version} to {target_version}.\n\n"
        f"Stages: plan → gap-check → clarify (optional) → preview → execute → feedback.\n"
        f"Each stage resumes purely from MigrationContext graph state — never from prior "
        f"session conversation memory.\n\n"
        f"Active stage: {stage}"
    )


@mcp.prompt()
def resume_migration(context_id: str, stage: str = "execute") -> str:
    """Resume a split migration harness from an existing MigrationContext.

    context_id: the elementId returned by create_migration_context or get_pending_steps.
    stage: ignored — bundle is determined from context state (kept for API compatibility).
    """
    _ = stage
    ctx, pending_count, err = _resolve_context_for_resume(context_id)
    if err:
        return (
            f"Cannot resume context '{context_id}': {err}.\n"
            "Call get_migration_contexts to locate a valid context_id."
        )
    bundle = determine_resume_bundle(ctx, pending_count=pending_count)
    if bundle is None:
        return (
            f"Migration context '{context_id}' is already closed (status={ctx.get('status')!r}).\n"
            "No stage to resume. Start a new migration with start_migration if needed."
        )
    skill_uri = bundle_to_skill_uri(bundle)
    stage_name = next((k for k, v in _STAGE_BUNDLES.items() if v == bundle), bundle)
    return (
        f"Load {skill_uri}.\n\n"
        f"Resume migration context '{context_id}' at the '{stage_name}' stage.\n\n"
        f"Call get_pending_steps(context_id='{context_id}') when the stage needs the "
        f"pending queue.\n"
        f"All state must be read from the graph — do not rely on prior session memory."
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
        "Run the six-stage split migration harness:\n"
        "- plan: scan codebase, create MigrationContext, scope-gated graph queries\n"
        "- gap-check: mechanical plan audit, write gap-check flags\n"
        "- clarify (optional): add manual steps, exclude steps, force-include rules\n"
        "- preview: read-only plan grouped by risk with gap-check caveats\n"
        "- execute: apply pending steps, update_step_status\n"
        "- feedback: submit insights, close_migration_context"
    )


# Register tools via import side effects.
from migration_oracle.mcp.tools import install  # noqa: E402, F401
from migration_oracle.mcp.tools import paysafe  # noqa: E402, F401
from migration_oracle.mcp.tools import search  # noqa: E402, F401
from migration_oracle.mcp.tools import upgrade  # noqa: E402, F401

if MIGRATION_MODE == "full":
    from migration_oracle.mcp.tools import artifacts  # noqa: E402, F401
    from migration_oracle.mcp.tools import community  # noqa: E402, F401
    from migration_oracle.mcp.tools import context  # noqa: E402, F401
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
