"""Tests for the Community Insights page."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

PAGE = "migration_oracle/streamlit_app/pages/05_community.py"


def test_page_loads_without_exception():
    with patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": []}):
        at = AppTest.from_file(PAGE)
        at.run()
    assert not at.exception


def test_empty_state_shows_info():
    with patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": []}):
        at = AppTest.from_file(PAGE)
        at.run()
    assert any("No community insights found" in i.value for i in at.info)


def test_insight_card_renders():
    insight = {
        "insight_id": "ins-1",
        "statement": "Use the new API",
        "solution": "Replace old call",
        "votes": 3,
        "verified": True,
        "source_url": "",
    }
    with patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": [insight]}):
        at = AppTest.from_file(PAGE)
        at.run()
    assert not at.exception


def test_vote_up_calls_vote_insight_with_delta():
    insight = {
        "insight_id": "ins-1",
        "statement": "Use the new API",
        "solution": "Replace old call",
        "votes": 3,
        "verified": False,
        "source_url": "",
    }
    vote_response = {"status": "ok", "new_vote_count": 4}
    called_with = {}

    def mock_vote(**kwargs):
        called_with.update(kwargs)
        return vote_response

    with patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": [insight]}):
        with patch("migration_oracle.mcp.tools.community.vote_insight", side_effect=mock_vote):
            at = AppTest.from_file(PAGE)
            at.run()
            at.button[0].click()
            at.run()
    assert called_with.get("insight_id") == "ins-1"
    assert called_with.get("delta") == 1


def test_submit_insight_success():
    submit_response = {"status": "ok"}
    with patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": [{"insight_id": "x", "statement": "s", "solution": "sol", "votes": 0, "verified": False, "source_url": ""}]}):
        with patch("migration_oracle.mcp.tools.community.submit_migration_insight", return_value=submit_response):
            at = AppTest.from_file(PAGE)
            at.run()
            at.text_area[0].set_value("My statement")
            at.text_area[1].set_value("My solution")
            at.text_input[0].set_value("3.2")
            at.text_input[1].set_value("MyClass")
            at.text_input[2].set_value("http://example.com")
            at.get("form")[0].submit()
            at.run()
    assert any("Insight submitted" in s.value for s in at.success)


def test_submit_insight_duplicate():
    submit_response = {"status": "duplicate"}
    with patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": [{"insight_id": "x", "statement": "s", "solution": "sol", "votes": 0, "verified": False, "source_url": ""}]}):
        with patch("migration_oracle.mcp.tools.community.submit_migration_insight", return_value=submit_response):
            at = AppTest.from_file(PAGE)
            at.run()
            at.text_area[0].set_value("My statement")
            at.text_area[1].set_value("My solution")
            at.text_input[0].set_value("3.2")
            at.text_input[1].set_value("MyClass")
            at.text_input[2].set_value("http://example.com")
            at.get("form")[0].submit()
            at.run()
    assert any("Duplicate detected" in e.value for e in at.error)
