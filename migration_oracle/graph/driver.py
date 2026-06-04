"""Neo4j/Memgraph driver singleton and session helpers."""

from contextlib import contextmanager
from typing import Generator

import neo4j
from neo4j import GraphDatabase

from migration_oracle import config

_driver: neo4j.Driver | None = None


class DriverNotInitialisedError(RuntimeError):
    """Raised when session helpers are used after close_driver()."""


def get_driver() -> neo4j.Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD),
            encrypted=config.SSL_VERIFY,
        )
    return _driver


def _require_driver() -> neo4j.Driver:
    if _driver is None:
        raise DriverNotInitialisedError("Neo4j driver is not initialised")
    return _driver


@contextmanager
def read_session() -> Generator[neo4j.Session, None, None]:
    driver = get_driver()
    session = driver.session(default_access_mode=neo4j.READ_ACCESS)
    try:
        yield session
    finally:
        session.close()


@contextmanager
def write_session() -> Generator[neo4j.Session, None, None]:
    driver = get_driver()
    session = driver.session(default_access_mode=neo4j.WRITE_ACCESS)
    try:
        yield session
    finally:
        session.close()


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
