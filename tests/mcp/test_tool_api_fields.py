"""Field-contract and error-path tests for resolve_deprecation, search_openrewrite_recipes, submit_migration_insight."""

from unittest.mock import MagicMock, patch


# --- resolve_deprecation ---

def test_resolve_deprecation_uses_entity_name_alias():
    """Cypher alias must be entity_name, not original_entity."""
    from migration_oracle.mcp.graph.queries.deprecation import _RESOLVE_DEPRECATION

    assert "e.name AS entity_name" in _RESOLVE_DEPRECATION
    assert "e.name AS original_entity" not in _RESOLVE_DEPRECATION


def test_resolve_deprecation_tool_returns_entity_name():
    """resolve_deprecation tool returns non-null entity_name field."""
    from migration_oracle.mcp.tools.deprecation import resolve_deprecation

    fake_record = {
        "entity_type": "Class",
        "entity_name": "org.springframework.Foo",
        "replaced_by": None,
        "deprecated_in": "3.0.0",
        "removed_in": None,
        "rules": [],
    }
    with patch("migration_oracle.mcp.tools.deprecation.deprecation_queries.resolve_deprecation") as mock:
        mock.return_value = fake_record
        result = resolve_deprecation(entity_name="org.springframework.Foo")

    assert result["status"] == "ok"
    assert result["entity_name"] == "org.springframework.Foo"


# --- search_openrewrite_recipes ---

def test_search_recipes_uses_composite_property():
    """Cypher filter must use r.composite, not r.isComposite."""
    from migration_oracle.mcp.graph.queries.search import hydrate_openrewrite_recipes

    # Verify the function generates the correct filter
    # We call it with only_composite=True to trigger the filter
    with patch("migration_oracle.mcp.graph.queries.search.read_session") as mock_rs:
        session = MagicMock()
        session.run.return_value = []
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        mock_rs.return_value = session

        hydrate_openrewrite_recipes(element_ids=["fake-id"], only_composite=True)

        cypher_call = session.run.call_args[0][0]
        assert "r.composite" in cypher_call
        assert "isComposite" not in cypher_call


def test_search_recipes_require_no_params_uses_has_param():
    """require_no_params filter must use HAS_PARAM relationship, not requiredParams array."""
    from migration_oracle.mcp.graph.queries.search import hydrate_openrewrite_recipes

    with patch("migration_oracle.mcp.graph.queries.search.read_session") as mock_rs:
        session = MagicMock()
        session.run.return_value = []
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        mock_rs.return_value = session

        hydrate_openrewrite_recipes(element_ids=["fake-id"], require_no_params=True)

        cypher_call = session.run.call_args[0][0]
        assert "HAS_PARAM" in cypher_call
        assert "requiredParams" not in cypher_call


# --- submit_migration_insight ---

def test_submit_insight_duplicate_returns_none_insight_id():
    """On duplicate, insight_id must be None; duplicate_of must be the existing insight's ID."""
    from migration_oracle.mcp.tools.community import submit_migration_insight

    with patch("migration_oracle.mcp.tools.community.community_queries.submit_insight") as mock_si, \
         patch("migration_oracle.mcp.tools.community.get_embedding_model") as mock_em:

        mock_em.return_value.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2])
        mock_si.return_value = ("existing-id-123", True)

        result = submit_migration_insight(
            statement="some insight",
            spring_boot_version="3.2.0",
        )

    assert result["status"] == "duplicate"
    assert result["insight_id"] is None
    assert result["duplicate_of"] == "existing-id-123"


def test_submit_insight_ok_returns_new_id_and_none_duplicate_of():
    """On success, insight_id is the new ID and duplicate_of is None."""
    from migration_oracle.mcp.tools.community import submit_migration_insight

    with patch("migration_oracle.mcp.tools.community.community_queries.submit_insight") as mock_si, \
         patch("migration_oracle.mcp.tools.community.get_embedding_model") as mock_em:

        mock_em.return_value.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2])
        mock_si.return_value = ("new-id-456", False)

        result = submit_migration_insight(
            statement="unique insight",
            spring_boot_version="3.2.0",
        )

    assert result["status"] == "ok"
    assert result["insight_id"] == "new-id-456"
    assert result["duplicate_of"] is None


def test_submit_insight_error_returns_none_fields():
    """On error, both insight_id and duplicate_of are None."""
    from migration_oracle.mcp.tools.community import submit_migration_insight

    with patch("migration_oracle.mcp.tools.community.community_queries.submit_insight") as mock_si, \
         patch("migration_oracle.mcp.tools.community.get_embedding_model") as mock_em:

        mock_em.return_value.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2])
        mock_si.side_effect = ValueError("Version not found: Spring Boot 99.0.0")

        result = submit_migration_insight(
            statement="any insight",
            spring_boot_version="99.0.0",
        )

    assert result["status"] == "error"
    assert result["insight_id"] is None
    assert result["duplicate_of"] is None
