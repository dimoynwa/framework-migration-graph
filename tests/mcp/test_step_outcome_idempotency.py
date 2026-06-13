"""Idempotency test: STEP_OUTCOME uses MERGE so double-record leaves one relationship."""

from migration_oracle.mcp.graph.queries.context import _RECORD_STEP_OUTCOME


def test_step_outcome_uses_merge_not_create():
    """STEP_OUTCOME must be written with MERGE (not CREATE) to guarantee idempotency."""
    assert "MERGE (ctx)-[so:STEP_OUTCOME]->(step)" in _RECORD_STEP_OUTCOME
    assert "CREATE" not in _RECORD_STEP_OUTCOME or "ON CREATE" in _RECORD_STEP_OUTCOME


def test_step_outcome_sets_properties_after_merge():
    """SET clause on STEP_OUTCOME runs unconditionally after MERGE (upsert semantics)."""
    merge_pos = _RECORD_STEP_OUTCOME.index("MERGE (ctx)-[so:STEP_OUTCOME]->(step)")
    set_pos = _RECORD_STEP_OUTCOME.index("SET so.status")
    assert set_pos > merge_pos, "SET must come after MERGE for upsert to work"
