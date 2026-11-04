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


def _make_git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir()
    return root.resolve()


def test_full_mode_installs_six_bundles():
    os.environ["MIGRATION_MODE"] = "full"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        result = inst_mod.install_migration_skill(target="cursor", target_dir=tmp)
        assert result["status"] == "ok"
        assert len(result["installed_paths"]) == 10
        assert result["mode"] == "full"
        assert result["installed_skills"] == [
            "framework-migration-research",
            "framework-migration-plan",
            "framework-migration-gap-check",
            "framework-migration-clarify",
            "framework-migration-preview",
            "framework-migration-execute",
        ]
        assert Path(tmp, "framework-migration-research", "SKILL.md").is_file()
        assert Path(tmp, "framework-migration-plan", "SKILL.md").is_file()
        assert Path(
            tmp, "framework-migration-plan", "references", "framework_scanner.py"
        ).is_file()


def test_invalid_target_raises_value_error_before_write():
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError, match="target must be one of"):
            inst_mod.install_migration_skill(target="curser", target_dir=tmp)
        assert list(Path(tmp).iterdir()) == []


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


def test_default_installs_under_project_cursor_skills(monkeypatch):
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_git_repo(Path(tmp))
        monkeypatch.chdir(repo)
        result = inst_mod.install_migration_skill(target="cursor")
        install_root = repo / ".cursor" / "skills"
        assert result["status"] == "ok"
        assert result["scope"] == "project"
        assert result["project_root"] == str(repo)
        assert (install_root / "migration-lite" / "SKILL.md").is_file()
        assert all(Path(p).is_relative_to(repo) for p in result["installed_paths"])


def test_claude_code_installs_under_project_claude_skills(monkeypatch):
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_git_repo(Path(tmp))
        monkeypatch.chdir(repo)
        result = inst_mod.install_migration_skill(target="claude-code")
        install_root = repo / ".claude" / "skills"
        assert result["status"] == "ok"
        assert result["scope"] == "project"
        assert (install_root / "migration-lite" / "SKILL.md").is_file()


def test_scope_global_uses_home_skills_dir(monkeypatch):
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        fake_home = Path(tmp) / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        repo = _make_git_repo(Path(tmp) / "repo")
        monkeypatch.chdir(repo)
        result = inst_mod.install_migration_skill(target="cursor", scope="global")
        install_root = fake_home / ".cursor" / "skills"
        assert result["status"] == "ok"
        assert result["scope"] == "global"
        assert (install_root / "migration-lite" / "SKILL.md").is_file()


def test_project_dir_override_when_cwd_differs(monkeypatch):
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_git_repo(Path(tmp) / "consumer-repo")
        other_cwd = Path(tmp) / "other-cwd"
        other_cwd.mkdir()
        monkeypatch.chdir(other_cwd)
        result = inst_mod.install_migration_skill(
            target="cursor",
            project_dir=str(repo),
        )
        install_root = repo / ".cursor" / "skills"
        assert result["status"] == "ok"
        assert result["project_root"] == str(repo)
        assert (install_root / "migration-lite" / "SKILL.md").is_file()


def test_coexists_with_unrelated_project_skills(monkeypatch):
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_git_repo(Path(tmp))
        existing = repo / ".cursor" / "skills" / "speckit-plan" / "SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("# existing skill\n", encoding="utf-8")
        monkeypatch.chdir(repo)
        result = inst_mod.install_migration_skill(target="cursor")
        assert result["status"] == "ok"
        assert existing.read_text(encoding="utf-8") == "# existing skill\n"
        assert (repo / ".cursor" / "skills" / "migration-lite" / "SKILL.md").is_file()


def test_git_root_walk_from_subdirectory(monkeypatch):
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_git_repo(Path(tmp))
        subdir = repo / "services" / "api"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        result = inst_mod.install_migration_skill(target="cursor")
        install_root = repo / ".cursor" / "skills"
        assert result["project_root"] == str(repo)
        assert (install_root / "migration-lite" / "SKILL.md").is_file()


def test_invalid_scope_raises_value_error():
    os.environ["MIGRATION_MODE"] = "lite"
    inst_mod = _reload_install_module()

    with pytest.raises(ValueError, match="scope must be one of"):
        inst_mod.install_migration_skill(scope="workspace")
