"""Error-path test for update_queried_entity: context not found."""

from unittest.mock import MagicMock, patch


def test_update_queried_entity_context_not_found():
    """Nonexistent context_id returns documented error shape."""
    from migration_oracle.mcp.tools.context import update_queried_entity

    with patch("migration_oracle.mcp.graph.queries.context.read_session") as mock_rs:
        session = MagicMock()
        result = MagicMock()
        result.single.return_value = None  # context not found
        session.run.return_value = result
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        mock_rs.return_value = session

        response = update_queried_entity(
            context_id="nonexistent-ctx",
            entity_name="org.example.Foo",
            result_summary="something",
        )

    assert response["status"] == "error"
    assert response["error_code"] == "context_not_found"
