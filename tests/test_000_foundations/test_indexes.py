"""Tests for graph index DDL."""

from unittest.mock import MagicMock

import neo4j
import pytest
from neo4j.exceptions import ClientError

from migration_oracle.graph.indexes import _INDEXES, ensure_indexes


def _make_mock_driver(run_side_effect=None) -> MagicMock:
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    if run_side_effect is not None:
        mock_session.run.side_effect = run_side_effect

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session
    return mock_driver, mock_session


def test_all_statements_run() -> None:
    mock_driver, mock_session = _make_mock_driver()
    ensure_indexes(mock_driver)
    assert mock_session.run.call_count == len(_INDEXES)


def test_partial_failure_continues() -> None:
    fulltext_stmt = _INDEXES[9]

    def run_side_effect(statement: str, **kwargs):
        if statement == fulltext_stmt:
            raise ClientError("Full-text indexes not supported")

    mock_driver, mock_session = _make_mock_driver(run_side_effect=run_side_effect)
    ensure_indexes(mock_driver)
    assert mock_session.run.call_count == len(_INDEXES)


def test_idempotent_second_call() -> None:
    mock_driver, mock_session = _make_mock_driver()
    ensure_indexes(mock_driver)
    ensure_indexes(mock_driver)
    assert mock_session.run.call_count == len(_INDEXES) * 2
