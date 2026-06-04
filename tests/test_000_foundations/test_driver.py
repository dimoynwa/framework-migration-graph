"""Tests for Neo4j driver singleton and session helpers."""

from unittest.mock import MagicMock, patch

import pytest

from migration_oracle.graph import driver as driver_mod


@pytest.fixture(autouse=True)
def _reset_driver() -> None:
    driver_mod.close_driver()
    yield
    driver_mod.close_driver()


def _make_mock_driver() -> tuple[MagicMock, MagicMock]:
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value = mock_session
    return mock_driver, mock_session


@pytest.fixture
def mock_graph_database() -> MagicMock:
    first_driver, first_session = _make_mock_driver()
    second_driver, second_session = _make_mock_driver()
    with patch.object(
        driver_mod.GraphDatabase,
        "driver",
        side_effect=[first_driver, second_driver],
    ) as ctor:
        yield ctor, first_driver, first_session, second_driver, second_session


def test_singleton(mock_graph_database: tuple) -> None:
    ctor, mock_driver, _, _, _ = mock_graph_database
    d1 = driver_mod.get_driver()
    d2 = driver_mod.get_driver()
    assert d1 is d2
    ctor.assert_called_once()


def test_close_driver_resets_singleton(mock_graph_database: tuple) -> None:
    ctor, mock_driver, _, second_driver, _ = mock_graph_database
    first = driver_mod.get_driver()
    driver_mod.close_driver()
    mock_driver.close.assert_called_once()
    second = driver_mod.get_driver()
    assert second is second_driver
    assert second is not first
    assert ctor.call_count == 2


def test_read_session_context_manager(mock_graph_database: tuple) -> None:
    _, mock_driver, mock_session, _, _ = mock_graph_database
    driver_mod.get_driver()
    with driver_mod.read_session() as session:
        assert session is mock_session
    mock_session.close.assert_called_once()


def test_write_session_context_manager(mock_graph_database: tuple) -> None:
    _, mock_driver, mock_session, _, _ = mock_graph_database
    driver_mod.get_driver()
    with driver_mod.write_session() as session:
        assert session is mock_session
    mock_session.close.assert_called_once()


def test_read_session_lazy_inits_after_close(mock_graph_database: tuple) -> None:
    ctor, _, first_session, _, second_session = mock_graph_database
    driver_mod.get_driver()
    driver_mod.close_driver()
    with driver_mod.read_session() as session:
        assert session is second_session
    assert ctor.call_count == 2
