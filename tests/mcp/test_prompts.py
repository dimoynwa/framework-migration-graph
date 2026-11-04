"""Tests for file-state migration prompts (017/020)."""

from __future__ import annotations

from migration_oracle.mcp.server import (
    bundle_to_skill_uri,
    migration_workflow_prompt,
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
    assert "ps-migration/" in text
    assert "Migration" + "Context" not in text
    assert "research (optional)" in text


def test_start_migration_research_stage():
    text = start_migration(
        framework="Spring Boot",
        current_version="3.3.0",
        target_version="3.4.0",
        project_id="proj-1",
        stage="research",
    )
    assert "skill://framework-migration-research/main" in text
    assert "Active stage: research" in text


def test_start_migration_execute_stage():
    text = start_migration(
        framework="Spring Boot",
        current_version="2.7.18",
        target_version="3.2.0",
        project_id="proj-1",
        stage="execute",
    )
    assert "skill://framework-migration-execute/main" in text


def test_bundle_to_skill_uri():
    assert bundle_to_skill_uri("framework-migration-gap-check") == (
        "skill://framework-migration-gap-check/main"
    )
    assert bundle_to_skill_uri("framework-migration-research") == (
        "skill://framework-migration-research/main"
    )


def test_resume_migration_renders_execute_bundle():
    text = resume_migration(
        migration_folder="ps-migration/spring-boot-2.7.18-to-3.2.0",
        stage="execute",
    )
    assert "skill://framework-migration-execute/main" in text
    assert "tasks.md" in text
    assert "get_pending_steps" not in text


def test_resume_migration_gap_check_stage():
    text = resume_migration(
        migration_folder="ps-migration/spring-boot-2.7.18-to-3.2.0",
        stage="gap-check",
    )
    assert "skill://framework-migration-gap-check/main" in text


def test_resume_migration_research_stage():
    text = resume_migration(
        migration_folder="ps-migration/spring-boot-2.7.18-to-3.2.0",
        stage="research",
    )
    assert "skill://framework-migration-research/main" in text
    assert "research.md" in text


def test_migration_workflow_prompt_describes_six_stages():
    text = migration_workflow_prompt()
    assert "six-stage" in text
    assert "research (optional)" in text
    assert "skill://framework-migration-plan/main" in text
