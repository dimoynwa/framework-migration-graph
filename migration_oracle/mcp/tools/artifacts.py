"""Pipeline artifact MCP tool handlers."""

from __future__ import annotations

import re
from pathlib import Path

from migration_oracle.mcp.graph.queries import artifacts as artifact_queries
from migration_oracle.mcp.instance import mcp

_FROM_VERSION_RE = re.compile(
    r"[\\/]?[\w.-]+-to-(\d+\.\d+\.\d+)-changes(?:_filtered)?\.md$",
    re.IGNORECASE,
)
_SPLIT_RE = re.compile(r"-to-(\d+\.\d+\.\d+)-changes", re.IGNORECASE)


def _parse_from_version(raw_md_path: str | None) -> str:
    if not raw_md_path:
        return ""
    m = re.search(r"(\d+\.\d+\.\d+)-to-\d+\.\d+\.\d+-changes(?:_filtered)?\.md", raw_md_path)
    if m:
        return m.group(1)
    return ""

ARTIFACT_TYPE_MAP = {
    "raw_md": "rawMdPath",
    "filtered_md": "filteredMdPath",
    "entities_json": "entitiesJsonPath",
}


@mcp.tool()
def list_pipeline_runs() -> dict:
    """List all Version nodes that have pipeline artifact paths stored in the graph.

    A pipeline run is a processed (framework, version) pair that has at least one artifact
    path (raw_md, filtered_md, or entities_json). Returns: runs list with framework, to_version,
    and path fields. Use to discover available artifact keys before calling get_artifact_content.
    """
    runs = artifact_queries.list_pipeline_runs()
    records = [
        {
            "framework": row.get("framework") or "",
            "from_version": row.get("from_version") or _parse_from_version(row.get("raw_md_path")),
            "to_version": row.get("version") or "",
            "raw_md_path": row.get("raw_md_path") or "",
            "filtered_md_path": row.get("filtered_md_path"),
            "entities_json_path": row.get("entities_json_path"),
        }
        for row in runs
    ]
    return {"status": "ok", "runs": records, "total": len(records)}


@mcp.tool()
def get_artifact_content(
    framework: str,
    from_version: str,
    to_version: str,
    artifact_type: str,
) -> dict:
    """Read a pipeline artifact by type. The file path is resolved from the graph — no direct path accepted.

    artifact_type: 'raw_md' | 'filtered_md' | 'entities_json'.
    The path is read from the Version node in the graph; callers cannot supply an arbitrary filesystem path.
    Returns: content (full text), path_resolved, status ('ok' | 'not_found' | 'error').
    """
    if artifact_type not in ARTIFACT_TYPE_MAP:
        return {
            "status": "error",
            "framework": framework,
            "from_version": from_version,
            "to_version": to_version,
            "artifact_type": artifact_type,
            "content": "",
            "path_resolved": "",
            "message": f"Invalid artifact_type: {artifact_type}",
        }
    paths = artifact_queries.get_version_artifact_path(
        framework=framework, to_version=to_version
    )
    if paths is None:
        return {
            "status": "not_found",
            "framework": framework,
            "from_version": from_version,
            "to_version": to_version,
            "artifact_type": artifact_type,
            "content": "",
            "path_resolved": "",
            "message": "Version node not found",
        }
    prop = ARTIFACT_TYPE_MAP[artifact_type]
    path = paths.get(prop)
    if not path:
        return {
            "status": "not_found",
            "framework": framework,
            "from_version": from_version,
            "to_version": to_version,
            "artifact_type": artifact_type,
            "content": "",
            "path_resolved": "",
            "message": f"No path for artifact_type {artifact_type}",
        }
    content = Path(path).read_text(encoding="utf-8")
    return {
        "status": "ok",
        "framework": framework,
        "from_version": from_version,
        "to_version": to_version,
        "artifact_type": artifact_type,
        "content": content,
        "path_resolved": path,
        "message": "",
    }
