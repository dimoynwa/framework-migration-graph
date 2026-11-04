"""E2E-style tests for file-state skill bundles (017)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

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
        assert len(result["installed_skills"]) == 5
        text = start_migration(
            framework="Spring Boot",
            current_version="3.3.0",
            target_version="3.4.0",
            project_id="e2e-proj",
        )
        assert "skill://framework-migration-plan/main" in text
        assert (Path(tmp) / "framework-migration-plan" / "SKILL.md").is_file()


def test_e2e_resume_migration_file_folder():
    text = resume_migration(
        migration_folder="ps-migration/spring-boot-3.3.0-to-3.4.0",
        stage="execute",
    )
    assert "skill://framework-migration-execute/main" in text
    assert "tasks.md" in text
