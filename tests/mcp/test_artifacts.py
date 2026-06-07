"""Tests for artifact MCP tools."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

from migration_oracle.mcp.tools.artifacts import get_artifact_content, list_pipeline_runs


def test_list_pipeline_runs():
    rows = [
        {
            "framework": "Spring Boot",
            "version": "4.0.0",
            "raw_md_path": "/data/run.md",
            "filtered_md_path": None,
            "entities_json_path": None,
        }
    ]
    with patch(
        "migration_oracle.mcp.tools.artifacts.artifact_queries.list_pipeline_runs",
        return_value=rows,
    ):
        result = list_pipeline_runs()
    assert result["total"] == 1
    assert result["runs"][0]["raw_md_path"] == "/data/run.md"


def test_get_artifact_content_raw_md(tmp_path):
    artifact = tmp_path / "run.md"
    artifact.write_text("# release notes", encoding="utf-8")
    with patch(
        "migration_oracle.mcp.tools.artifacts.artifact_queries.get_version_artifact_path",
        return_value={"rawMdPath": str(artifact)},
    ):
        result = get_artifact_content(
            framework="Spring Boot",
            from_version="3.5.6",
            to_version="4.0.0",
            artifact_type="raw_md",
        )
    assert result["status"] == "ok"
    assert result["content"] == "# release notes"
    assert result["path_resolved"] == str(artifact)


def test_get_artifact_content_invalid_type():
    with patch(
        "migration_oracle.mcp.tools.artifacts.artifact_queries.get_version_artifact_path"
    ) as mock_paths:
        result = get_artifact_content(
            framework="Spring Boot",
            from_version="3.5.6",
            to_version="4.0.0",
            artifact_type="invalid",
        )
    assert result["status"] == "error"
    mock_paths.assert_not_called()


def test_get_artifact_content_missing_version():
    with patch(
        "migration_oracle.mcp.tools.artifacts.artifact_queries.get_version_artifact_path",
        return_value=None,
    ):
        result = get_artifact_content(
            framework="Spring Boot",
            from_version="3.5.6",
            to_version="9.9.9",
            artifact_type="raw_md",
        )
    assert result["status"] == "not_found"


def test_get_artifact_content_no_direct_path_param():
    sig = inspect.signature(get_artifact_content)
    assert "path" not in sig.parameters
