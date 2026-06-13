"""Tests for spec 011 US7: list_pipeline_runs populates from_version correctly."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_run_row(
    framework: str = "Spring Boot",
    version: str = "4.0.0",
    raw_md_path: str = "/data/spring-boot-3.5.0-to-4.0.0-changes.md",
    filtered_md_path: str | None = None,
    entities_json_path: str | None = None,
    from_version: str | None = None,
) -> dict:
    return {
        "framework": framework,
        "version": version,
        "raw_md_path": raw_md_path,
        "filtered_md_path": filtered_md_path,
        "entities_json_path": entities_json_path,
        "from_version": from_version,
    }


@patch("migration_oracle.mcp.tools.artifacts.artifact_queries.list_pipeline_runs")
def test_stored_from_version_used(mock_list):
    """from_version from the Version node is used when present."""
    mock_list.return_value = [_make_run_row(from_version="3.5.0")]

    from migration_oracle.mcp.tools.artifacts import list_pipeline_runs

    result = list_pipeline_runs()

    assert result["status"] == "ok"
    assert result["runs"][0]["from_version"] == "3.5.0"


@patch("migration_oracle.mcp.tools.artifacts.artifact_queries.list_pipeline_runs")
def test_filename_fallback(mock_list):
    """from_version falls back to filename parse when node has no stored value."""
    mock_list.return_value = [
        _make_run_row(
            raw_md_path="/data/spring-boot-3.5.0-to-4.0.0-changes.md",
            from_version=None,
        )
    ]

    from migration_oracle.mcp.tools.artifacts import list_pipeline_runs

    result = list_pipeline_runs()

    assert result["runs"][0]["from_version"] == "3.5.0"


@patch("migration_oracle.mcp.tools.artifacts.artifact_queries.list_pipeline_runs")
def test_graceful_empty_when_no_source(mock_list):
    """from_version defaults to '' when neither node value nor filename pattern is available."""
    mock_list.return_value = [
        _make_run_row(raw_md_path="/data/unknown-file.md", from_version=None)
    ]

    from migration_oracle.mcp.tools.artifacts import list_pipeline_runs

    result = list_pipeline_runs()

    assert result["runs"][0]["from_version"] == ""


@patch("migration_oracle.mcp.tools.artifacts.artifact_queries.list_pipeline_runs")
def test_filtered_md_suffix_handled(mock_list):
    """Filename parse handles the _filtered.md suffix variant correctly."""
    mock_list.return_value = [
        _make_run_row(
            raw_md_path="/data/spring-boot-3.3.0-to-3.5.0-changes_filtered.md",
            from_version=None,
        )
    ]

    from migration_oracle.mcp.tools.artifacts import list_pipeline_runs

    result = list_pipeline_runs()

    assert result["runs"][0]["from_version"] == "3.3.0"
