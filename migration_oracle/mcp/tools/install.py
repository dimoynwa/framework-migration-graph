"""Migration skill installation MCP tool handler."""

from __future__ import annotations

import shutil
from pathlib import Path

from migration_oracle.mcp.instance import mcp

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _detect_target() -> str:
    cwd = Path.cwd()
    home = Path.home()
    if (cwd / ".cursor").exists() or (home / ".cursor").exists():
        return "cursor"
    if (cwd / ".claude").exists() or (home / ".claude").exists():
        return "claude-code"
    return "cursor"


def _target_dir(target: str) -> Path:
    home = Path.home()
    if target == "cursor":
        return home / ".cursor" / "skills" / "framework-migration-mcp"
    return home / ".claude" / "skills" / "framework-migration-mcp"


@mcp.tool()
def install_migration_skill(
    target: str = "auto",
    target_dir: str | None = None,
) -> dict:
    """Copy bundled skill Markdown files to the Cursor or Claude Code skills directory.

    target: 'auto' (detect from environment), 'cursor', or 'claude-code'.
    'auto' checks for .cursor or .claude directories in CWD and HOME; defaults to 'cursor' if neither found.
    Returns: installed_paths list, target (resolved). Use once after first connecting to the server.
    """
    resolved = _detect_target() if target == "auto" else target
    dest = Path(target_dir) if target_dir else _target_dir(resolved)
    dest.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for skill_file in sorted(_SKILLS_DIR.glob("*.md")):
        out = dest / skill_file.name
        shutil.copy2(skill_file, out)
        installed.append(str(out))
    if not installed:
        return {
            "status": "error",
            "target": resolved,
            "installed_paths": [],
            "message": "No skill files found to install",
        }
    return {
        "status": "ok",
        "target": resolved,
        "installed_paths": installed,
        "message": f"Installed {len(installed)} skill files to {dest}",
    }
