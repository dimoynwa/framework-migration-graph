"""Paysafe dependency resolution MCP tool handler."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from migration_oracle.mcp.instance import mcp
from migration_oracle.paysafe.resolver import resolve


@mcp.tool()
def resolve_paysafe_dependency_by_service_name(
    service_name: Annotated[
        str,
        Field(description="FindIt service name for the com.paysafe dependency, for example 'payments-core'."),
    ],
    target_version: Annotated[
        str | None,
        Field(description="Optional target framework version used to filter compatible tags when metadata is available."),
    ] = None,
    framework: Annotated[
        str | None,
        Field(description="Optional framework identifier for compatibility filtering, for example 'spring-boot'."),
    ] = None,
    allow_latest_overall: Annotated[
        bool,
        Field(description="Allow selecting the latest tag even when per-tag framework compatibility metadata is unavailable."),
    ] = False,
    max_tags: Annotated[
        int,
        Field(description="Maximum number of repository tags to inspect within the resolver wall-clock budget."),
    ] = 15,
    pinned_version: Annotated[
        str | None,
        Field(description="Optional exact dependency version to prefer when present in repository metadata."),
    ] = None,
    pinned_tag: Annotated[
        str | None,
        Field(description="Optional exact Git tag to inspect instead of selecting from recent tags."),
    ] = None,
) -> dict:
    """Resolve a com.paysafe.* dependency via FindIt and GitLab. Returns repo, tags, and migration guidance.

    Requires FINDIT_AUTH_TOKEN and GITLAB_API_KEY environment variables. Returns a RESOLUTION_FAILED dict with subStatus='auth_error' if FINDIT_AUTH_TOKEN is absent.
    Pass target_version to filter returned tags to those compatible with that framework version.
    Scans at most max_tags (default 15) within a 45s wall-clock budget. For BOM-only repos without
    per-tag framework metadata, omit target_version or set allow_latest_overall=True.
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
