"""Resume skip guard tests for update_queried_entity."""

import json
from unittest.mock import MagicMock, call, patch


def test_update_queried_entity_persists_entry():
    """update_queried_entity stores entity in queriedEntities and returns cached_count."""
    from migration_oracle.mcp.tools.context import update_queried_entity

    fake_get = {"qe": "{}"}
    with patch("migration_oracle.mcp.graph.queries.context.read_session") as mock_rs, \
         patch("migration_oracle.mcp.graph.queries.context.write_session") as mock_ws:

        read_session = MagicMock()
        read_result = MagicMock()
        read_result.single.return_value = fake_get
        read_session.run.return_value = read_result
        read_session.__enter__ = lambda s: s
        read_session.__exit__ = MagicMock(return_value=False)
        mock_rs.return_value = read_session

        write_session = MagicMock()
        write_result = MagicMock()
        write_result.single.return_value = None
        write_session.run.return_value = write_result
        write_session.__enter__ = lambda s: s
        write_session.__exit__ = MagicMock(return_value=False)
        mock_ws.return_value = write_session

        result = update_queried_entity(
            context_id="ctx-1",
            entity_name="org.example.Foo",
            result_summary="deprecated in 3.0.0",
        )

    assert result["status"] == "ok"
    assert result["entity_name"] == "org.example.Foo"
    assert result["cached_count"] == 1


def test_skip_guard_entity_present_after_update():
    """After update_queried_entity, the entity key is present in the written JSON."""
    from migration_oracle.mcp.graph.queries.context import update_queried_entity as query_fn

    fake_get = {"qe": "{}"}
    written_json = {}

    def capture_write(cypher, **kwargs):
        written_json.update({"updated_json": kwargs.get("updated_json", "")})
        result = MagicMock()
        result.single.return_value = None
        return result

    with patch("migration_oracle.mcp.graph.queries.context.read_session") as mock_rs, \
         patch("migration_oracle.mcp.graph.queries.context.write_session") as mock_ws:

        read_session = MagicMock()
        read_result = MagicMock()
        read_result.single.return_value = fake_get
        read_session.run.return_value = read_result
        read_session.__enter__ = lambda s: s
        read_session.__exit__ = MagicMock(return_value=False)
        mock_rs.return_value = read_session

        write_session = MagicMock()
        write_session.run.side_effect = capture_write
        write_session.__enter__ = lambda s: s
        write_session.__exit__ = MagicMock(return_value=False)
        mock_ws.return_value = write_session

        query_fn(
            context_id="ctx-1",
            entity_name="org.example.Bar",
            result_summary="removed in 2.7.0",
        )

    stored = json.loads(written_json["updated_json"])
    assert "org.example.Bar" in stored
    assert stored["org.example.Bar"] == "removed in 2.7.0"
