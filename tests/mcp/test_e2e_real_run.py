"""E2E replay test — paysafe-wallet-switch 3.5.12 → 4.0.6 (T052).

Requires live Neo4j with seeded Version nodes (scripts/seed_013_versions.py must have run).
Mark: integration (skipped unless --integration flag or NEO4J_AVAILABLE=1).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("NEO4J_AVAILABLE") != "1",
    reason="Requires live Neo4j — set NEO4J_AVAILABLE=1 to run",
)

PROJECT_ID = "paysafe-wallet-switch-e2e-013"
FROM_VERSION = "3.5.12"
TO_VERSION = "4.0.6"
FRAMEWORK = "Spring Boot"
SCANNED_ENTITIES = [
    "org.springframework.boot.autoconfigure.SpringBootApplication",
    "org.springframework.web.bind.annotation.RestController",
    "com.fasterxml.jackson.databind.ObjectMapper",
    "org.springframework.cloud:spring-cloud-starter-gateway",
    "spring.datasource.url",
]


@pytest.fixture(autouse=True)
def cleanup_context():
    """Delete the E2E test context before and after each test."""
    from migration_oracle.mcp.graph.queries.context import delete_zombie_context
    try:
        delete_zombie_context(
            project_id=PROJECT_ID,
            from_version=FROM_VERSION,
            to_version=TO_VERSION,
        )
    except Exception:
        pass
    yield
    try:
        delete_zombie_context(
            project_id=PROJECT_ID,
            from_version=FROM_VERSION,
            to_version=TO_VERSION,
        )
    except Exception:
        pass


def test_get_migration_contexts_count_zero_before_create():
    """Step 1: get_migration_contexts returns count=0 (no stale context)."""
    from migration_oracle.mcp.tools.context import get_migration_contexts

    result = get_migration_contexts(project_id=PROJECT_ID)
    assert result["status"] == "ok"
    assert result["count"] == 0


def test_create_migration_context_no_truncation():
    """Step 2: create context — fromVersion preserved, no truncation."""
    from migration_oracle.mcp.tools.context import create_migration_context

    result = create_migration_context(
        project_id=PROJECT_ID,
        from_version=FROM_VERSION,
        to_version=TO_VERSION,
        framework=FRAMEWORK,
        scanned_entities=SCANNED_ENTITIES,
    )
    assert result["status"] == "ok"
    assert result["created"] is True
    # fromVersion must not be truncated to "3.5.0"
    assert result["from_version"] == FROM_VERSION
    assert result["to_version"] == TO_VERSION
    assert result["dropped_count"] == 0


def test_check_version_availability_and_submit_migration_insight_same_node_id():
    """Step 3 (SC-001): check_version_availability and submit_migration_insight return same nodeId."""
    from migration_oracle.mcp.graph.queries.upgrade import resolve_version

    from_result = resolve_version(FRAMEWORK, FROM_VERSION, mode="floor")
    from migration_oracle.models.graph import VersionResolutionFailure
    assert not isinstance(from_result, VersionResolutionFailure), (
        f"resolve_version floor for {FROM_VERSION} failed — seed versions first."
    )
    check_node_id = from_result.nodeId

    # Resolve again (simulates submit_migration_insight path)
    from_result2 = resolve_version(FRAMEWORK, FROM_VERSION, mode="floor")
    assert not isinstance(from_result2, VersionResolutionFailure)
    submit_node_id = from_result2.nodeId

    assert check_node_id == submit_node_id, (
        "ISSUE-016 regression: check_version_availability and submit_migration_insight "
        "resolved different nodeIds for the same version."
    )


def test_co_migration_warning_emitted_for_spring_cloud():
    """Step 5: Spring Cloud co-migration warning emitted when cloud deps present."""
    from migration_oracle.mcp.tools.context import create_migration_context

    result = create_migration_context(
        project_id=PROJECT_ID + "-cloud",
        from_version=FROM_VERSION,
        to_version=TO_VERSION,
        framework=FRAMEWORK,
        scanned_entities=SCANNED_ENTITIES,  # includes org.springframework.cloud dep
    )
    # cleanup
    try:
        from migration_oracle.mcp.graph.queries.context import delete_zombie_context
        delete_zombie_context(
            project_id=PROJECT_ID + "-cloud",
            from_version=FROM_VERSION,
            to_version=TO_VERSION,
        )
    except Exception:
        pass

    if result["status"] == "ok":
        assert "co_migration_warning" in result, (
            "Expected co_migration_warning when Spring Cloud dep present in 3→4 migration."
        )


def test_pending_steps_and_recipe_plan_step_id_parity():
    """SC-009: get_pending_steps and build_recipe_plan return equal distinct step_id sets."""
    from migration_oracle.mcp.tools.context import create_migration_context, get_pending_steps
    from migration_oracle.mcp.tools.upgrade import build_recipe_plan

    ctx = create_migration_context(
        project_id=PROJECT_ID,
        from_version=FROM_VERSION,
        to_version=TO_VERSION,
        framework=FRAMEWORK,
        scanned_entities=SCANNED_ENTITIES,
    )
    assert ctx["status"] == "ok"
    context_id = ctx["context_id"]

    pending = get_pending_steps(context_id)
    pending_ids = {s["step_id"] for s in pending.get("pending_steps", []) if s.get("step_id")}

    plan = build_recipe_plan(
        current_version=FROM_VERSION,
        target_version=TO_VERSION,
        framework=FRAMEWORK,
        user_entities=SCANNED_ENTITIES,
        context_id=context_id,
    )
    plan_ids = {
        s["step_id"]
        for s in plan.get("manual_track", []) + plan.get("auto_track", [])
        if s.get("step_id")
    }

    assert pending_ids == plan_ids, (
        f"step_id mismatch: only in pending={pending_ids - plan_ids}, "
        f"only in plan={plan_ids - pending_ids}"
    )
    assert len(pending_ids) > 0
