"""Tests for resolve_version: unit + ISSUE-016 regression gate (T011, T012)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from migration_oracle.mcp.graph.queries.upgrade import resolve_version
from migration_oracle.models.graph import VersionResolutionFailure, VersionResolutionResult


def _make_row(version: str, sortable: int, node_id: str = "element-1") -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "node_id": node_id,
        "resolved_version": version,
        "sortable": sortable,
    }[k]
    row.get = lambda k, default=None: {
        "node_id": node_id,
        "resolved_version": version,
        "sortable": sortable,
    }.get(k, default)
    return row


def _make_session(row=None, rows=None):
    sess = MagicMock()
    result = MagicMock()
    if row is not None:
        result.single.return_value = row
    else:
        result.single.return_value = None
    if rows is not None:
        result.__iter__ = lambda self: iter(rows)
    sess.run.return_value = result
    return sess


class FakeReadSession:
    def __init__(self, side_effects):
        self._calls = iter(side_effects)

    def __enter__(self):
        return next(self._calls)

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Unit tests (T011)
# ---------------------------------------------------------------------------

@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_floor_resolves_patch_to_same_node(mock_rs):
    """floor resolves 3.5.12 → same node as 3.5.0 (floor semantics)."""
    row = _make_row("3.5.0", 3005000, "node-35")
    candidates_result = MagicMock()
    candidates_result.__iter__ = lambda s: iter([])
    candidates_result.single.return_value = row

    sessions = [_make_session(row=row), _make_session(rows=[])]
    call_count = [0]

    def fake_rs():
        class CM:
            def __enter__(self_inner):
                sess = _make_session(row=row)
                return sess
            def __exit__(self_inner, *args):
                pass
        return CM()

    mock_rs.side_effect = fake_rs

    result = resolve_version("Spring Boot", "3.5.12", mode="floor")
    assert isinstance(result, VersionResolutionResult)
    assert result.nodeId == "node-35"
    assert result.direction == "floor"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_ceil_resolves_with_rounded_true(mock_rs):
    """ceil resolves 4.0.9 → 4.0.6 with rounded=True."""
    row = _make_row("4.0.6", 4000006, "node-406")

    def fake_rs():
        class CM:
            def __enter__(self_inner):
                return _make_session(row=row)
            def __exit__(self_inner, *args):
                pass
        return CM()

    mock_rs.side_effect = fake_rs

    result = resolve_version("Spring Boot", "4.0.9", mode="ceil")
    assert isinstance(result, VersionResolutionResult)
    assert result.resolvedVersion == "4.0.6"
    assert result.rounded is True
    assert result.aheadOfCatalogue is False


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_ceil_ahead_of_catalogue(mock_rs):
    """ceil for 6.0.0 returns highest node + aheadOfCatalogue=True."""
    no_ceil = MagicMock()
    no_ceil.single.return_value = None
    fallback_row = _make_row("4.1.0", 4001000, "node-410")
    fallback = MagicMock()
    fallback.single.return_value = fallback_row

    call_idx = [0]

    def fake_rs():
        class CM:
            def __enter__(self_inner):
                idx = call_idx[0]
                call_idx[0] += 1
                if idx == 0:
                    return _make_session(row=None)
                return _make_session(row=fallback_row)
            def __exit__(self_inner, *args):
                pass
        return CM()

    mock_rs.side_effect = fake_rs

    result = resolve_version("Spring Boot", "6.0.0", mode="ceil")
    assert isinstance(result, VersionResolutionResult)
    assert result.aheadOfCatalogue is True
    assert result.rounded is True


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_exact_match_returns_correct_node(mock_rs):
    """exact match returns the node when version matches exactly."""
    row = _make_row("3.5.0", 3005000, "node-exact")

    def fake_rs():
        class CM:
            def __enter__(self_inner):
                return _make_session(row=row)
            def __exit__(self_inner, *args):
                pass
        return CM()

    mock_rs.side_effect = fake_rs

    result = resolve_version("Spring Boot", "3.5.0", mode="exact")
    assert isinstance(result, VersionResolutionResult)
    assert result.nodeId == "node-exact"
    assert result.rounded is False


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_patch_preserved_never_truncated(mock_rs):
    """Patch 3.5.12 is preserved — never truncated to 3.5.0."""
    row = _make_row("3.5.0", 3005000, "node-floor")

    def fake_rs():
        class CM:
            def __enter__(self_inner):
                return _make_session(row=row)
            def __exit__(self_inner, *args):
                pass
        return CM()

    mock_rs.side_effect = fake_rs

    result = resolve_version("Spring Boot", "3.5.12", mode="floor")
    assert isinstance(result, VersionResolutionResult)
    # The requestedVersion must be the full patch string, not truncated
    assert result.requestedVersion == "3.5.12"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_unknown_framework_returns_no_candidate(mock_rs):
    """Unknown framework returns VersionResolutionFailure(status=NO_CANDIDATE)."""
    candidates_row = MagicMock()
    candidates_row.__getitem__ = lambda s, k: "" if k == "version" else None

    no_row = MagicMock()
    no_row.single.return_value = None
    candidates_list_result = MagicMock()
    candidates_list_result.__iter__ = lambda s: iter([])

    call_idx = [0]

    def fake_rs():
        class CM:
            def __enter__(self_inner):
                idx = call_idx[0]
                call_idx[0] += 1
                if idx == 0:
                    return _make_session(row=None)
                sess = MagicMock()
                result = MagicMock()
                result.__iter__ = lambda s: iter([])
                sess.run.return_value = result
                return sess
            def __exit__(self_inner, *args):
                pass
        return CM()

    mock_rs.side_effect = fake_rs

    result = resolve_version("UnknownFramework", "1.0.0", mode="floor")
    assert isinstance(result, VersionResolutionFailure)
    assert result.status == "NO_CANDIDATE"
    assert result.framework == "UnknownFramework"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_near_miss_returns_candidates_considered(mock_rs):
    """Near-miss version returns VersionResolutionFailure with candidatesConsidered."""
    candidate_row = MagicMock()
    candidate_row.__getitem__ = lambda s, k: "3.5.0" if k == "version" else None

    call_idx = [0]

    def fake_rs():
        class CM:
            def __enter__(self_inner):
                idx = call_idx[0]
                call_idx[0] += 1
                if idx == 0:
                    return _make_session(row=None)
                sess = MagicMock()
                result = MagicMock()
                result.__iter__ = lambda s: iter([candidate_row])
                sess.run.return_value = result
                return sess
            def __exit__(self_inner, *args):
                pass
        return CM()

    mock_rs.side_effect = fake_rs

    result = resolve_version("Spring Boot", "99.99.0", mode="floor")
    assert isinstance(result, VersionResolutionFailure)
    assert result.candidatesConsidered is not None
    assert len(result.candidatesConsidered) > 0


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
@patch("migration_oracle.mcp.graph.queries.upgrade.write_session")
def test_allow_stub_create_false_does_not_create_stub(mock_ws, mock_rs):
    """allow_stub_create=False does not create stub nodes."""
    call_idx = [0]

    def fake_rs():
        class CM:
            def __enter__(self_inner):
                idx = call_idx[0]
                call_idx[0] += 1
                if idx == 0:
                    return _make_session(row=None)
                return _make_session(row=None)
            def __exit__(self_inner, *args):
                pass
        return CM()

    mock_rs.side_effect = fake_rs

    result = resolve_version("Spring Boot", "99.0.0", mode="ceil", allow_stub_create=False)
    # Should not call write_session
    mock_ws.assert_not_called()
    assert isinstance(result, (VersionResolutionResult, VersionResolutionFailure))
