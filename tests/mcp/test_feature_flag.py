"""Tests for MIGRATION_MODE tool registration."""

from __future__ import annotations

import os
import sys

import pytest

TOOL_MODULES = [
    "migration_oracle.mcp.tools.upgrade",
    "migration_oracle.mcp.tools.search",
    "migration_oracle.mcp.tools.paysafe",
    "migration_oracle.mcp.tools.install",
    "migration_oracle.mcp.tools.context",
    "migration_oracle.mcp.tools.deprecation",
    "migration_oracle.mcp.tools.community",
    "migration_oracle.mcp.tools.artifacts",
    "migration_oracle.mcp.tools.schema",
]

MCP_MODULES = TOOL_MODULES + [
    "migration_oracle.mcp.instance",
    "migration_oracle.mcp.server",
    "migration_oracle.mcp.config",
]


def _evict_mcp_modules() -> None:
    for name in list(sys.modules):
        if name == "migration_oracle.mcp.config" or name.startswith("migration_oracle.mcp."):
            sys.modules.pop(name, None)


def _fresh_server(mode: str, stage: str | None = None):
    """Force every relevant module to be re-imported under the given mode."""
    os.environ["MIGRATION_MODE"] = mode
    if stage is None:
        os.environ.pop("MCP_ACTIVE_STAGE", None)
    else:
        os.environ["MCP_ACTIVE_STAGE"] = stage
    _evict_mcp_modules()
    import migration_oracle.mcp.server as srv

    return srv.mcp


async def _tool_names(mcp) -> set[str]:
    tools = await mcp.list_tools()
    return {t.name for t in tools}


@pytest.mark.asyncio
async def test_lite_registers_4_tools():
    mcp = _fresh_server("lite")
    names = await _tool_names(mcp)
    assert names == {
        "analyze_upgrade_path",
        "search_migration_knowledge",
        "resolve_paysafe_dependency_by_service_name",
        "install_migration_skill",
    }


@pytest.mark.asyncio
async def test_full_registers_26_tools():
    mcp = _fresh_server("full")
    tools = await mcp.list_tools()
    assert len(tools) == 26


@pytest.mark.asyncio
async def test_mixed_module_full_only_tools_absent_in_lite():
    mcp = _fresh_server("lite")
    names = await _tool_names(mcp)
    assert "build_recipe_plan" not in names
    assert "check_version_availability" not in names
    assert "search_openrewrite_recipes" not in names


def test_invalid_mode_raises_before_server_builds():
    os.environ["MIGRATION_MODE"] = "enterprise"
    _evict_mcp_modules()
    try:
        with pytest.raises(ValueError, match="MIGRATION_MODE"):
            import migration_oracle.mcp.config  # noqa: F401
    finally:
        os.environ["MIGRATION_MODE"] = "lite"


def test_default_mode_is_lite_when_unset():
    backup = os.environ.pop("MIGRATION_MODE", None)
    _evict_mcp_modules()
    try:
        import migration_oracle.mcp.config as cfg

        assert cfg.MIGRATION_MODE == "lite"
    finally:
        if backup is not None:
            os.environ["MIGRATION_MODE"] = backup
        _evict_mcp_modules()


@pytest.mark.asyncio
async def test_full_only_tool_call_raises_protocol_error_in_lite():
    mcp = _fresh_server("lite")
    with pytest.raises(Exception) as exc_info:
        await mcp.call_tool("create_migration_context", {})
    assert type(exc_info.value).__name__ not in {"AttributeError", "KeyError"}
