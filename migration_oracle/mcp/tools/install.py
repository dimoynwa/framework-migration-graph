"""Migration skill installation MCP tool handler."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from migration_oracle.mcp.config import MIGRATION_MODE
from migration_oracle.mcp.instance import mcp

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Maps bundle name → list of (source filename under _SKILLS_DIR, relative output path).
SKILL_BUNDLES: dict[str, list[tuple[str, str]]] = {
    "framework-migration": [
        ("framework_migration_main.md", "SKILL.md"),
        ("framework_migration_scanning.md", "references/scanning.md"),
        ("framework_migration_plan_format.md", "references/plan-format.md"),
        ("framework_migration_version_map.md", "references/version-map.md"),
        ("framework_migration_rollback.md", "references/rollback.md"),
    ],
    "migration-lite": [
        ("migration_lite_main.md", "migration-lite/SKILL.md"),
        ("framework_migration_version_map.md", "migration-lite/references/version-map.md"),
    ],
    "openrewrite-runner": [
        ("openrewrite_main.md", "openrewrite-runner/SKILL.md"),
        ("openrewrite_recipe_catalog.md", "openrewrite-runner/references/recipe-catalog.md"),
        ("openrewrite_examples.md", "openrewrite-runner/references/examples.md"),
    ],
}

MODE_BUNDLES: dict[str, list[str]] = {
    "full": ["framework-migration"],
    "lite": ["migration-lite", "openrewrite-runner"],
}

_CURSOR_DIR = "~/.cursor/skills"
_CLAUDE_DIR = "~/.claude/skills"
_CURSOR_FRAMEWORK_DIR = "~/.cursor/skills/framework-migration"
_CLAUDE_FRAMEWORK_DIR = "~/.claude/skills/framework-migration"


def _resolve_target_dir(*, target: str, target_dir: str | None) -> Path:
    resolved = "cursor" if target in ("auto", "cursor") else "claude-code"
    if target_dir:
        return Path(target_dir).expanduser().resolve()
    if MIGRATION_MODE == "full":
        base = _CURSOR_FRAMEWORK_DIR if resolved == "cursor" else _CLAUDE_FRAMEWORK_DIR
    else:
        base = _CURSOR_DIR if resolved == "cursor" else _CLAUDE_DIR
    return Path(base).expanduser().resolve()


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
    target: str = "auto",
    target_dir: str | None = None,
) -> dict:
    """Install migration skill bundles for the active server mode to a local skills directory.

    target: 'auto', 'cursor', or 'claude-code' — used to suggest the install directory.
            'auto' defaults to 'cursor'.
    target_dir: override the install root directory (parent for lite bundles, bundle root for full).

    Returns:
      status, target, installed_paths, message, mode, installed_skills
    """
    resolved = "cursor" if target in ("auto", "cursor") else "claude-code"
    bundle_names = MODE_BUNDLES[MIGRATION_MODE]
    target_root = _resolve_target_dir(target=target, target_dir=target_dir)

    plan = _collect_install_plan(bundle_names)
    installed_paths = _install_to_target(plan, target_root)

    return {
        "status": "ok",
        "target": resolved,
        "installed_paths": installed_paths,
        "message": (
            f"Installed {len(installed_paths)} skill file(s) for mode={MIGRATION_MODE!r} "
            f"into {target_root}"
        ),
        "mode": MIGRATION_MODE,
        "installed_skills": bundle_names,
    }
