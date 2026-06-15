"""Paysafe dependency resolution MCP tool handler."""

from __future__ import annotations

from migration_oracle.mcp.instance import mcp
from migration_oracle.paysafe.resolver import resolve


@mcp.tool()
def resolve_paysafe_dependency_by_service_name(
    service_name: str,
    target_version: str | None = None,
    framework: str | None = None,
    allow_latest_overall: bool = False,
    max_tags: int = 100,
    pinned_version: str | None = None,
    pinned_tag: str | None = None,
) -> dict:
    """Resolve a com.paysafe.* dependency via FindIt and GitLab. Returns repo, tags, and migration guidance.

    Requires FINDIT_AUTH_TOKEN and GITLAB_API_KEY environment variables. Returns a RESOLUTION_FAILED dict with subStatus='auth_error' if FINDIT_AUTH_TOKEN is absent.
    Pass target_version to filter returned tags to those compatible with that framework version.
    The tool delegates entirely to the Paysafe resolver — check resolver logs for root-cause errors.
    """
    return resolve(
        service_name=service_name,
        target_version=target_version,
        framework=framework,
        allow_latest_overall=allow_latest_overall,
        max_tags=max_tags,
        pinned_version=pinned_version,
        pinned_tag=pinned_tag,
    )
