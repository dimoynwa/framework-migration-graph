"""Tests for the Context Dashboard page."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

PAGE = "migration_oracle/streamlit_app/pages/04_context_dashboard.py"


def test_page_loads_without_context():
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    assert len(at.text_input) > 0


def test_create_context_sets_session_state():
    response = {
        "context_id": "ctx-123",
        "project_id": "proj-abc",
        "from_version": "2.7.x",
        "to_version": "3.2",
        "migration_status": "in-progress",
        "completed_steps": [],
        "skipped_steps": [],
    }
    pending_response = {"pending_steps": []}

    with patch("migration_oracle.mcp.tools.context.create_migration_context", return_value=response):
        with patch("migration_oracle.mcp.tools.context.get_pending_steps", return_value=pending_response):
            at = AppTest.from_file(PAGE)
            at.run()
            at.text_input[0].set_value("proj-abc")
            at.text_input[1].set_value("2.7.x")
            at.text_input[2].set_value("3.2")
            at.button[0].click()
            at.run()
    assert at.session_state["context_id"] == "ctx-123"
    assert at.session_state["context_completed_count"] == 0
    assert at.session_state["context_skipped_count"] == 0


def test_no_pending_steps_shows_info():
    pending_response = {"pending_steps": []}
    at = AppTest.from_file(PAGE)
    at.session_state["context_id"] = "ctx-123"
    at.session_state["context_status"] = "in-progress"
    at.session_state["context_completed_count"] = 0
    at.session_state["context_skipped_count"] = 0
    with patch("migration_oracle.mcp.tools.context.get_pending_steps", return_value=pending_response):
        at.run()
    assert any("No pending steps remaining" in i.value for i in at.info)


def test_mark_complete_updates_session_state():
    step = {
        "step_id": "step-1",
        "summary": "Migrate config",
        "effort": "mechanical",
        "automatable": True,
        "scope": "config",
        "severity": "low",
    }
    pending_response = {"pending_steps": [step]}
    update_response = {"completed_count": 1, "skipped_count": 0}
    empty_pending = {"pending_steps": []}

    at = AppTest.from_file(PAGE)
    at.session_state["context_id"] = "ctx-123"
    at.session_state["context_status"] = "in-progress"
    at.session_state["context_completed_count"] = 0
    at.session_state["context_skipped_count"] = 0

    # call sequence: (1) first at.run after clear_on_nav rerun, (2) initial execution
    # on button click run, (3) rerun after button sets completing_key — must still see
    # the step so the completing_key branch fires, (4) final rerun after update shows empty
    with patch("migration_oracle.mcp.tools.context.get_pending_steps", side_effect=[pending_response, pending_response, pending_response, empty_pending]):
        with patch("migration_oracle.mcp.tools.context.update_step_status", return_value=update_response):
            at.run()
            at.button[0].click()
            at.run()
    assert at.session_state["context_completed_count"] == 1
