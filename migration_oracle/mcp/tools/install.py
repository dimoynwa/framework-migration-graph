"""Migration skill installation MCP tool handler."""

from __future__ import annotations

from pathlib import Path

from migration_oracle.mcp.instance import mcp

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Maps source filename → relative output path within the skill directory.
# main → SKILL.md (entry point); all others go under references/.
_FILE_MAP: dict[str, str] = {
    "framework_migration_main.md": "SKILL.md",
    "framework_migration_scanning.md": "references/scanning.md",
    "framework_migration_plan_format.md": "references/plan-format.md",
    "framework_migration_version_map.md": "references/version-map.md",
    "framework_migration_rollback.md": "references/rollback.md",
}

_CURSOR_DIR = "~/.cursor/skills/framework-migration"
_CLAUDE_DIR = "~/.claude/skills/framework-migration"


@mcp.tool()
def install_migration_skill(
    target: str = "auto",
    target_dir: str | None = None,
) -> dict:
    """Return the bundled migration skill files as text so the agent can write them locally.

    The MCP server runs in a Docker container and cannot write to your host filesystem.
    This tool returns the skill file contents so your AI agent (Cursor, Claude Code) can
    write them to the correct location using its own filesystem access.

    target: 'auto', 'cursor', or 'claude-code' — used to suggest the install directory.
            'auto' defaults to 'cursor'.
    target_dir: override the suggested install directory (e.g. '/Users/you/.cursor/skills/framework-migration').

    Returns:
      suggested_dir  — recommended absolute path to install into (expand ~ yourself)
      files          — dict of { relative_path: file_content } to write
      instructions   — plain-English steps for the agent to follow
    """
    resolved = "cursor" if target in ("auto", "cursor") else "claude-code"
    if target_dir:
        suggested = target_dir
    else:
        suggested = _CURSOR_DIR if resolved == "cursor" else _CLAUDE_DIR

    files: dict[str, str] = {}
    missing: list[str] = []
    for src_name, rel_path in _FILE_MAP.items():
        src = _SKILLS_DIR / src_name
        if src.exists():
            files[rel_path] = src.read_text(encoding="utf-8")
        else:
            missing.append(src_name)

    if not files:
        return {
            "status": "error",
            "message": "No skill files found in server bundle.",
            "missing": missing,
        }

    instructions = (
        f"Write each entry in `files` to `{{suggested_dir}}/{{relative_path}}`, "
        f"creating parent directories as needed. "
        f"For example: write `files['SKILL.md']` to `{suggested}/SKILL.md` and "
        f"`files['references/scanning.md']` to `{suggested}/references/scanning.md`."
    )

    result: dict = {
        "status": "ok",
        "target": resolved,
        "suggested_dir": suggested,
        "files": files,
        "instructions": instructions,
    }
    if missing:
        result["missing"] = missing
    return result
