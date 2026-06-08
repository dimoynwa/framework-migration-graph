"""Tests for the Run Browser page."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

PAGE = "migration_oracle/streamlit_app/pages/02_run_browser.py"


def test_page_loads_without_exception():
    with patch("migration_oracle.mcp.tools.artifacts.list_pipeline_runs", return_value={"runs": []}):
        at = AppTest.from_file(PAGE)
        at.run()
    assert not at.exception


def test_empty_state_shows_info():
    with patch("migration_oracle.mcp.tools.artifacts.list_pipeline_runs", return_value={"runs": []}):
        at = AppTest.from_file(PAGE)
        at.run()
    assert len(at.info) > 0
    assert "No pipeline runs found" in at.info[0].value
    assert len(at.selectbox) == 0


def test_run_appears_in_selectbox():
    run = {"framework": "spring-boot", "from_version": "", "to_version": "3.2"}
    with patch("migration_oracle.mcp.tools.artifacts.list_pipeline_runs", return_value={"runs": [run]}):
        with patch("migration_oracle.mcp.tools.artifacts.get_artifact_content", return_value={"status": "ok", "content": "# MD"}):
            at = AppTest.from_file(PAGE)
            at.run()
    assert len(at.selectbox) > 0
    assert "spring-boot → 3.2" in at.selectbox[0].options[0]


def test_missing_artifact_shows_error():
    run = {"framework": "spring-boot", "from_version": "", "to_version": "3.2"}
    with patch("migration_oracle.mcp.tools.artifacts.list_pipeline_runs", return_value={"runs": [run]}):
        with patch("migration_oracle.mcp.tools.artifacts.get_artifact_content", return_value={"status": "not_found", "content": ""}):
            at = AppTest.from_file(PAGE)
            at.run()
    assert len(at.error) > 0
