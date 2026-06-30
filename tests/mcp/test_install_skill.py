"""Tests for install_migration_skill bundle installation."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest


def _reload_install_module():
    for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
        sys.modules.pop(name, None)
    import migration_oracle.mcp.tools.install as inst_mod

    return inst_mod


def test_full_mode_installs_six_bundles():
    os.environ["MIGRATION_MODE"] = "full"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        result = inst_mod.install_migration_skill(target="cursor", target_dir=tmp)
        assert result["status"] == "ok"
        assert len(result["installed_paths"]) == 9
        assert result["mode"] == "full"
        assert set(result["installed_skills"]) == {
            "framework-migration-plan",
            "framework-migration-gap-check",
            "framework-migration-clarify",
            "framework-migration-preview",
            "framework-migration-execute",
            "framework-migration-feedback",
        }
        assert Path(tmp, "framework-migration-plan", "SKILL.md").is_file()


def test_lite_mode_installs_five_files_across_bundles():
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        result = inst_mod.install_migration_skill(target="cursor", target_dir=tmp)
        assert result["status"] == "ok"
        assert len(result["installed_paths"]) == 5
        assert result["mode"] == "lite"
        assert set(result["installed_skills"]) == {"migration-lite", "openrewrite-runner"}
        expected = [
            "migration-lite/SKILL.md",
            "migration-lite/references/version-map.md",
            "openrewrite-runner/SKILL.md",
            "openrewrite-runner/references/recipe-catalog.md",
            "openrewrite-runner/references/examples.md",
        ]
        for rel in expected:
            assert Path(tmp, rel).is_file(), rel


def test_return_payload_includes_mode_and_installed_skills():
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        result = inst_mod.install_migration_skill(target="cursor", target_dir=tmp)
        assert "mode" in result
        assert "installed_skills" in result
        assert "installed_paths" in result
        assert "status" in result
        assert "target" in result
        assert "message" in result


def test_missing_source_file_raises_file_not_found_with_no_partial_install():
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    orig = inst_mod.SKILL_BUNDLES["migration-lite"][0]
    inst_mod.SKILL_BUNDLES["migration-lite"][0] = (
        "does_not_exist.md",
        "migration-lite/SKILL.md",
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(FileNotFoundError, match="does_not_exist"):
                inst_mod.install_migration_skill(target="cursor", target_dir=tmp)
            assert not Path(tmp, "migration-lite").exists()
    finally:
        inst_mod.SKILL_BUNDLES["migration-lite"][0] = orig


def test_non_writable_target_raises_permission_error():
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IXUSR)
        try:
            with pytest.raises(PermissionError) as exc_info:
                inst_mod.install_migration_skill(target="cursor", target_dir=tmp)
            assert tmp in str(exc_info.value)
        finally:
            os.chmod(tmp, stat.S_IRWXU)
