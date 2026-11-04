"""Migration skill installation MCP tool handler."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from pydantic import Field

from migration_oracle.mcp.config import MIGRATION_MODE
from migration_oracle.mcp.instance import mcp

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Maps bundle name → list of (source filename under _SKILLS_DIR, relative output path).
SKILL_BUNDLES: dict[str, list[tuple[str, str]]] = {
    "framework-migration-research": [
        ("framework-migration/research.md", "framework-migration-research/SKILL.md"),
    ],
    "framework-migration-plan": [
        ("framework-migration/plan.md", "framework-migration-plan/SKILL.md"),
        ("framework-migration/scanning.md", "framework-migration-plan/references/scanning.md"),
        ("framework-migration/version-map.md", "framework-migration-plan/references/version-map.md"),
        (
            "framework-migration/framework_scanner.py",
            "framework-migration-plan/references/framework_scanner.py",
        ),
    ],
    "framework-migration-gap-check": [
        ("framework-migration/gap-check.md", "framework-migration-gap-check/SKILL.md"),
    ],
    "framework-migration-clarify": [
        ("framework-migration/clarify.md", "framework-migration-clarify/SKILL.md"),
    ],
    "framework-migration-preview": [
        ("framework-migration/preview.md", "framework-migration-preview/SKILL.md"),
    ],
    "framework-migration-execute": [
        ("framework-migration/execute.md", "framework-migration-execute/SKILL.md"),
        ("framework-migration/rollback.md", "framework-migration-execute/references/rollback.md"),
    ],
    "migration-lite": [
        ("migration-lite/main.md", "migration-lite/SKILL.md"),
        ("framework-migration/version-map.md", "migration-lite/references/version-map.md"),
    ],
    "openrewrite-runner": [
        ("openrewrite/main.md", "openrewrite-runner/SKILL.md"),
        ("openrewrite/recipe-catalog.md", "openrewrite-runner/references/recipe-catalog.md"),
        ("openrewrite/examples.md", "openrewrite-runner/references/examples.md"),
    ],
}

MODE_BUNDLES: dict[str, list[str]] = {
    "full": [
        "framework-migration-research",
        "framework-migration-plan",
        "framework-migration-gap-check",
        "framework-migration-clarify",
        "framework-migration-preview",
        "framework-migration-execute",
    ],
    "lite": ["migration-lite", "openrewrite-runner"],
}

_CURSOR_GLOBAL_DIR = "~/.cursor/skills"
_CLAUDE_GLOBAL_DIR = "~/.claude/skills"
_CURSOR_PROJECT_SUBDIR = ".cursor/skills"
_CLAUDE_PROJECT_SUBDIR = ".claude/skills"
_VALID_TARGETS = frozenset({"auto", "cursor", "claude-code"})
_VALID_SCOPES = frozenset({"project", "global"})


def _find_project_root(start: Path) -> Path:
    current = start.expanduser().resolve()
    if not current.is_dir():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").is_dir():
            return candidate
    return current


def _resolve_install(
    *,
    target: str,
    target_dir: str | None,
    project_dir: str | None,
    scope: str,
) -> tuple[Path, Path, str]:
    if target not in _VALID_TARGETS:
        raise ValueError(
            f"target must be one of {sorted(_VALID_TARGETS)!r}, got {target!r}"
        )
    if scope not in _VALID_SCOPES:
        raise ValueError(f"scope must be one of {sorted(_VALID_SCOPES)!r}, got {scope!r}")

    project_root = _find_project_root(Path(project_dir or Path.cwd()))

    if target_dir:
        return Path(target_dir).expanduser().resolve(), project_root, scope

    resolved = "cursor" if target in ("auto", "cursor") else "claude-code"
    if scope == "global":
        base = _CURSOR_GLOBAL_DIR if resolved == "cursor" else _CLAUDE_GLOBAL_DIR
        return Path(base).expanduser().resolve(), project_root, scope

    subdir = _CURSOR_PROJECT_SUBDIR if resolved == "cursor" else _CLAUDE_PROJECT_SUBDIR
    return (project_root / subdir).resolve(), project_root, scope


def _collect_install_plan(bundle_names: list[str]) -> list[tuple[Path, Path]]:
    plan: list[tuple[Path, Path]] = []
    for bundle in bundle_names:
        for src_name, rel_dest in SKILL_BUNDLES[bundle]:
            src = _SKILLS_DIR / src_name
            if not src.is_file():
                raise FileNotFoundError(str(src))
            plan.append((src, Path(rel_dest)))
    return plan


def _install_to_target(plan: list[tuple[Path, Path]], target_root: Path) -> list[str]:
    installed_paths: list[str] = []
    staging = Path(tempfile.mkdtemp(prefix="migration-skill-install-"))
    try:
        for src, rel_dest in plan:
            dest = staging / rel_dest
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            installed_paths.append(str((target_root / rel_dest).resolve()))

        try:
            target_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PermissionError(
                f"Cannot write to target directory {target_root}: {exc}"
            ) from exc

        for src, rel_dest in plan:
            staged = staging / rel_dest
            final = target_root / rel_dest
            try:
                final.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged, final)
            except OSError as exc:
                raise PermissionError(
                    f"Cannot write to target directory {target_root}: {exc}"
                ) from exc
    except Exception:
        for rel_dest in {rel for _, rel in plan}:
            partial = target_root / rel_dest
            if partial.exists():
                partial.unlink(missing_ok=True)
            parent = partial.parent
            if parent.exists() and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return installed_paths


@mcp.tool()
def install_migration_skill(
    target: Annotated[
        str,
        Field(description="'auto', 'cursor', or 'claude-code'. 'auto' resolves to cursor."),
    ] = "auto",
    target_dir: Annotated[
        str | None,
        Field(description="Optional explicit skills parent directory; overrides target and scope path resolution."),
    ] = None,
    project_dir: Annotated[
        str | None,
        Field(description="Optional starting directory for project-root detection; defaults to the process CWD."),
    ] = None,
    scope: Annotated[
        str,
        Field(description="'project' installs under the project skills directory; 'global' installs under the user skills directory."),
    ] = "project",
) -> dict:
    """Install migration skill bundles for the active server mode to a local skills directory.

    target: 'auto', 'cursor', or 'claude-code' — used to suggest the install directory.
            'auto' defaults to 'cursor'.
    target_dir: override the install root directory (skills parent for all bundles).
    project_dir: starting directory for project-root detection; defaults to the process CWD.
    scope: 'project' (default) installs under {project_root}/.cursor/skills or
           {project_root}/.claude/skills; 'global' installs under ~/.cursor/skills or
           ~/.claude/skills. Ignored when target_dir is set.

    Returns:
      status, target, installed_paths, message, mode, installed_skills, project_root, scope
    """
    target_root, project_root, effective_scope = _resolve_install(
        target=target,
        target_dir=target_dir,
        project_dir=project_dir,
        scope=scope,
    )
    resolved = "cursor" if target in ("auto", "cursor") else "claude-code"
    bundle_names = MODE_BUNDLES[MIGRATION_MODE]

    plan = _collect_install_plan(bundle_names)
    installed_paths = _install_to_target(plan, target_root)

    return {
        "status": "ok",
        "target": resolved,
        "installed_paths": installed_paths,
        "message": (
            f"Installed {len(installed_paths)} skill file(s) for mode={MIGRATION_MODE!r} "
            f"into {target_root} (scope={effective_scope!r})"
        ),
        "mode": MIGRATION_MODE,
        "installed_skills": bundle_names,
        "project_root": str(project_root),
        "scope": effective_scope,
    }
