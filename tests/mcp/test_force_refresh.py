"""Force-refresh semantics test: agent-loop concept, not a tool parameter."""

import json
from unittest.mock import MagicMock, patch


def test_force_refresh_is_not_a_tool_parameter():
    """update_queried_entity has no force_refresh parameter — it is an agent-loop concept."""
    import inspect
    from migration_oracle.mcp.tools.context import update_queried_entity

    sig = inspect.signature(update_queried_entity)
    assert "force_refresh" not in sig.parameters


def test_force_refresh_semantics_via_agent_loop():
    """Simulating the agent-loop: when force_refresh is set, update_queried_entity IS called
    (bypassing the skip guard locally) and overwrites the cached entry."""
    from migration_oracle.mcp.graph.queries.context import update_queried_entity as query_fn

    initial_cache = json.dumps({"org.example.Foo": "old result"})
    written_json: dict = {}

    def capture_write(cypher, **kwargs):
        written_json.update({"updated_json": kwargs.get("updated_json", "")})
        result = MagicMock()
        result.single.return_value = None
        return result

    with patch("migration_oracle.mcp.graph.queries.context.read_session") as mock_rs, \
         patch("migration_oracle.mcp.graph.queries.context.write_session") as mock_ws:

        read_session = MagicMock()
        read_result = MagicMock()
        read_result.single.return_value = {"qe": initial_cache}
        read_session.run.return_value = read_result
        read_session.__enter__ = lambda s: s
        read_session.__exit__ = MagicMock(return_value=False)
        mock_rs.return_value = read_session

        write_session = MagicMock()
        write_session.run.side_effect = capture_write
        write_session.__enter__ = lambda s: s
        write_session.__exit__ = MagicMock(return_value=False)
        mock_ws.return_value = write_session

        # Agent loop: force_refresh is a local flag — the loop simply calls update_queried_entity
        # again (bypassing the skip guard check) to overwrite the cache.
        force_refresh = True  # local agent-loop flag, never passed to any tool
        if force_refresh:
            result = query_fn(
                context_id="ctx-1",
                entity_name="org.example.Foo",
                result_summary="fresh result",
            )

    stored = json.loads(written_json["updated_json"])
    assert stored["org.example.Foo"] == "fresh result"
    assert result is not None
    assert result["cached_count"] == 1
