"""Tests for the Rule Explorer page."""

from unittest.mock import AsyncMock, patch

import pytest
from streamlit.testing.v1 import AppTest

PAGE = "migration_oracle/streamlit_app/pages/03_rule_explorer.py"


def test_page_loads_without_exception():
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception


def test_no_results_shows_info():
    async def mock_search(**kwargs):
        return {"hits": []}

    with patch("migration_oracle.mcp.tools.search.search_migration_knowledge", side_effect=mock_search):
        at = AppTest.from_file(PAGE)
        at.run()
        at.text_input[0].set_value("removed API")
        at.button[0].click()
        at.run()
    assert any("No rules found for this query" in i.value for i in at.info)


def test_happy_path_renders_results():
    hit = {
        "statement": "Some long rule statement that is over 80 characters total to test truncation",
        "rule_type": "breaking-change",
        "source_url": "",
        "action_step": "Do something",
    }

    async def mock_search(**kwargs):
        return {"hits": [hit]}

    with patch("migration_oracle.mcp.tools.search.search_migration_knowledge", side_effect=mock_search):
        at = AppTest.from_file(PAGE)
        at.run()
        at.text_input[0].set_value("removed API")
        at.button[0].click()
        at.run()
    # Results are rendered as st.markdown with custom HTML, not st.expander
    assert not at.exception
    assert any("results-header" in m.value for m in at.markdown)


def test_all_framework_passes_none():
    called_with = {}

    async def mock_search(query, framework, max_results=20):
        called_with["framework"] = framework
        return {"hits": []}

    with patch("migration_oracle.mcp.tools.search.search_migration_knowledge", side_effect=mock_search):
        at = AppTest.from_file(PAGE)
        at.run()
        at.text_input[0].set_value("test query")
        # selectbox default is "All" (index 0)
        at.button[0].click()
        at.run()
    assert "framework" in called_with
    assert called_with["framework"] is None
