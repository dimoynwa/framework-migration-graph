"""Tests for stage-aware migration prompts (015a)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from migration_oracle.mcp.server import (
    bundle_to_skill_uri,
    determine_resume_bundle,
    resume_migration,
    start_migration,
)


def test_start_migration_loads_plan_bundle():
    text = start_migration(
        framework="Spring Boot",
        current_version="3.3.0",
        target_version="3.4.0",
        project_id="proj-1",
        stage="plan",
    )
    assert "skill://framework-migration-plan/main" in text
    assert "skill://framework-migration/main" not in text


def test_bundle_to_skill_uri():
    assert bundle_to_skill_uri("framework-migration-gap-check") == (
        "skill://framework-migration-gap-check/main"
    )


def test_determine_resume_zero_outcomes_suggests_gap_check():
    ctx = {
        "status": "in-progress",
        "outcome_counts": {"completed": 0, "failed": 0, "skipped": 0, "deferred": 0, "excluded": 0},
        "has_gap_check_flags": False,
    }
    assert determine_resume_bundle(ctx, pending_count=5) == "framework-migration-gap-check"


def test_determine_resume_gap_flags_suggests_clarify():
    ctx = {
        "status": "in-progress",
        "outcome_counts": {"completed": 0, "failed": 0, "skipped": 0, "deferred": 0, "excluded": 0},
        "has_gap_check_flags": True,
    }
    assert determine_resume_bundle(ctx, pending_count=3) == "framework-migration-clarify"


def test_determine_resume_failed_suggests_execute():
    ctx = {
        "status": "in-progress",
        "outcome_counts": {"completed": 2, "failed": 1, "skipped": 0, "deferred": 0, "excluded": 0},
        "has_gap_check_flags": True,
    }
    assert determine_resume_bundle(ctx, pending_count=1) == "framework-migration-execute"


def test_determine_resume_all_accounted_suggests_feedback():
    ctx = {
        "status": "in-progress",
        "outcome_counts": {"completed": 3, "failed": 0, "skipped": 1, "deferred": 0, "excluded": 0},
        "has_gap_check_flags": True,
    }
    assert determine_resume_bundle(ctx, pending_count=0) == "framework-migration-feedback"


@patch("migration_oracle.mcp.server._resolve_context_for_resume")
def test_resume_migration_renders_gap_check_bundle(mock_resolve):
    mock_resolve.return_value = (
        {
            "status": "in-progress",
            "outcome_counts": {"completed": 0, "failed": 0, "skipped": 0, "deferred": 0, "excluded": 0},
            "has_gap_check_flags": False,
        },
        4,
        None,
    )
    text = resume_migration(context_id="ctx-1")
    assert "skill://framework-migration-gap-check/main" in text


@patch("migration_oracle.mcp.server._resolve_context_for_resume")
def test_resume_migration_renders_clarify_bundle(mock_resolve):
    mock_resolve.return_value = (
        {
            "status": "in-progress",
            "outcome_counts": {"completed": 0, "failed": 0, "skipped": 0, "deferred": 0, "excluded": 0},
            "has_gap_check_flags": True,
        },
        4,
        None,
    )
    text = resume_migration(context_id="ctx-1")
    assert "skill://framework-migration-clarify/main" in text


@patch("migration_oracle.mcp.server._resolve_context_for_resume")
def test_resume_migration_renders_execute_on_failed(mock_resolve):
    mock_resolve.return_value = (
        {
            "status": "in-progress",
            "outcome_counts": {"completed": 1, "failed": 1, "skipped": 0, "deferred": 0, "excluded": 0},
            "has_gap_check_flags": True,
        },
        2,
        None,
    )
    text = resume_migration(context_id="ctx-1")
    assert "skill://framework-migration-execute/main" in text


@patch("migration_oracle.mcp.server._resolve_context_for_resume")
def test_resume_migration_renders_feedback_when_all_accounted(mock_resolve):
    mock_resolve.return_value = (
        {
            "status": "in-progress",
            "outcome_counts": {"completed": 2, "failed": 0, "skipped": 1, "deferred": 0, "excluded": 0},
            "has_gap_check_flags": True,
        },
        0,
        None,
    )
    text = resume_migration(context_id="ctx-1")
    assert "skill://framework-migration-feedback/main" in text
