"""E2E-style tests for 015a skill bundle split (no live DB required)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from migration_oracle.mcp.server import resume_migration, start_migration


def _reload_install_full():
    os.environ["MIGRATION_MODE"] = "full"
    for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
        sys.modules.pop(name, None)
    from migration_oracle.mcp.tools.install import install_migration_skill
    return install_migration_skill


def test_e2e_install_then_start_migration_loads_plan():
    install_migration_skill = _reload_install_full()

    with tempfile.TemporaryDirectory() as tmp:
        result = install_migration_skill(target="cursor", target_dir=tmp)
        assert len(result["installed_skills"]) == 6
        text = start_migration(
            framework="Spring Boot",
            current_version="3.3.0",
            target_version="3.4.0",
            project_id="e2e-proj",
        )
        assert "skill://framework-migration-plan/main" in text
        assert (Path(tmp) / "framework-migration-plan" / "SKILL.md").is_file()


@patch("migration_oracle.mcp.server._resolve_context_for_resume")
def test_e2e_resume_branches(mock_resolve):
    branches = [
        (
            {"status": "in-progress", "outcome_counts": {"completed": 0, "failed": 0, "skipped": 0, "deferred": 0, "excluded": 0}, "has_gap_check_flags": False},
            "framework-migration-gap-check",
            4,
        ),
        (
            {"status": "in-progress", "outcome_counts": {"completed": 0, "failed": 0, "skipped": 0, "deferred": 0, "excluded": 0}, "has_gap_check_flags": True},
            "framework-migration-clarify",
            4,
        ),
        (
            {"status": "in-progress", "outcome_counts": {"completed": 1, "failed": 1, "skipped": 0, "deferred": 0, "excluded": 0}, "has_gap_check_flags": True},
            "framework-migration-execute",
            2,
        ),
        (
            {"status": "in-progress", "outcome_counts": {"completed": 2, "failed": 0, "skipped": 1, "deferred": 0, "excluded": 0}, "has_gap_check_flags": True},
            "framework-migration-feedback",
            0,
        ),
    ]
    for ctx, expected_bundle, pending in branches:
        mock_resolve.return_value = (ctx, pending, None)
        text = resume_migration(context_id="ctx-e2e")
        assert f"skill://{expected_bundle}/main" in text, f"Expected {expected_bundle} for {ctx}"
