"""Neo4j client utilities for the fitness knowledge graph module.

The module keeps Neo4j optional at import time. If the Python driver is not
installed or the database is offline, graph features report unavailable while
the main FastAPI application can still start.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from typing import Any

from app.core.config import settings

try:
    from neo4j import Driver, GraphDatabase
    from neo4j import Session as Neo4jSession
    from neo4j import Transaction
except ImportError:  # pragma: no cover - exercised when optional dependency is absent.
    Driver = Any  # type: ignore[misc, assignment]
    GraphDatabase = None  # type: ignore[assignment]
    Neo4jSession = Any  # type: ignore[misc, assignment]
    Transaction = Any  # type: ignore[misc, assignment]

logger = logging.getLogger("fitness.neo4j")

_driver: Driver | None = None
_disabled: bool = False
_last_check_time: float = 0
_last_available: bool = False
_check_interval: float = 60


class Neo4jUnavailableError(RuntimeError):
    """Raised when Neo4j features are requested but the driver is unavailable."""


def _normalize_records(records: Iterable[Any]) -> list[dict[str, Any]]:
    return [record.data() if hasattr(record, "data") else dict(record) for record in records]


class Neo4jClient:
    """Small Neo4j access wrapper used by graph and GraphRAG modules."""

    def __init__(
        self,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
        connection_timeout: float = 2.0,
    ):
        self.uri = uri or settings.neo4j_uri
        self.username = username or settings.neo4j_username
        self.password = password or settings.neo4j_password
        self.database = database or settings.neo4j_database
        self.connection_timeout = connection_timeout
        self._driver: Driver | None = None

    def connect(self) -> Driver:
        """Create or return the underlying Neo4j driver."""
        if GraphDatabase is None:
            raise Neo4jUnavailableError("Python package 'neo4j' is not installed.")
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                max_connection_lifetime=300,
                max_connection_pool_size=10,
                connection_acquisition_timeout=self.connection_timeout,
            )
        return self._driver

    @property
    def driver(self) -> Driver:
        return self.connect()

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def verify_connectivity(self) -> bool:
        try:
            self.connect().verify_connectivity()
            return True
        except Exception as exc:
            logger.info("Neo4j connectivity check failed: %s", exc)
            return False

    @contextmanager
    def session(self, readonly: bool = False) -> Generator[Neo4jSession, None, None]:
        access_mode = "READ" if readonly else "WRITE"
        session = self.driver.session(database=self.database, default_access_mode=access_mode)
        try:
            yield session
        finally:
            session.close()

    def execute_cypher(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        readonly: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute a parameterized Cypher statement and return JSON-like rows."""
        with self.session(readonly=readonly) as session:
            result = session.run(query, params or {})
            return _normalize_records(result)

    def query_nodes(
        self,
        label: str,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query nodes by a controlled label and parameterized property filters."""
        _validate_identifier(label, "label")
        filters = filters or {}
        for key in filters:
            _validate_identifier(key, "property")
        where = " AND ".join(f"n.{key} = ${key}" for key in filters)
        query = f"MATCH (n:`{label}`)"
        if where:
            query += f" WHERE {where}"
        query += " RETURN properties(n) AS node LIMIT $limit"
        return self.execute_cypher(query, {**filters, "limit": int(limit)}, readonly=True)

    def query_relationships(
        self,
        relationship_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query graph relationships, optionally constrained by relationship type."""
        if relationship_type:
            _validate_identifier(relationship_type, "relationship_type")
            pattern = f"-[r:`{relationship_type}`]->"
        else:
            pattern = "-[r]->"
        query = (
            f"MATCH (source){pattern}(target) "
            "RETURN labels(source) AS source_labels, properties(source) AS source, "
            "type(r) AS relationship, properties(r) AS properties, "
            "labels(target) AS target_labels, properties(target) AS target "
            "LIMIT $limit"
        )
        return self.execute_cypher(query, {"limit": int(limit)}, readonly=True)

    def execute_transaction(
        self,
        work: Callable[[Transaction], Any],
        readonly: bool = False,
    ) -> Any:
        """Run caller-provided unit of work inside a Neo4j transaction."""
        with self.session(readonly=readonly) as session:
            runner = session.execute_read if readonly else session.execute_write
            return runner(work)


def _validate_identifier(value: str, field_name: str) -> None:
    if not value or not value.replace("_", "").isalnum():
        raise ValueError(f"Invalid Neo4j {field_name}: {value!r}")


def _create_driver() -> Driver | None:
    if _disabled:
        return None
    try:
        return Neo4jClient().connect()
    except Exception as exc:
        logger.warning("Failed to create Neo4j driver; graph features disabled: %s", exc)
        return None


def get_driver() -> Driver | None:
    global _driver, _disabled
    if _disabled:
        return None
    if _driver is not None:
        return _driver
    _driver = _create_driver()
    if _driver is None:
        _disabled = True
    return _driver


def reset_driver() -> None:
    global _driver, _disabled, _last_check_time, _last_available
    if _driver:
        try:
            _driver.close()
        except Exception:
            pass
    _driver = None
    _disabled = False
    _last_check_time = 0
    _last_available = False


def is_available() -> bool:
    global _disabled, _last_check_time, _last_available

    if _disabled:
        return False

    now = time.time()
    if _last_check_time > 0 and (now - _last_check_time) < _check_interval:
        return _last_available

    _last_check_time = now
    driver = get_driver()
    if driver is None:
        _disabled = True
        _last_available = False
        return False
    try:
        with driver.session(database=settings.neo4j_database) as session:
            session.run("RETURN 1").consume()
        _last_available = True
        return True
    except Exception as exc:
        logger.info("Neo4j is unavailable: %s", exc)
        _disabled = True
        _last_available = False
        return False


@contextmanager
def neo4j_session(readonly: bool = False) -> Generator[Neo4jSession, None, None]:
    driver = get_driver()
    if driver is None:
        raise Neo4jUnavailableError("Neo4j is not available")
    session = driver.session(
        database=settings.neo4j_database,
        default_access_mode="READ" if readonly else "WRITE",
    )
    try:
        yield session
    finally:
        session.close()


def run_read(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute a read-only Cypher query and return dictionaries."""
    try:
        with neo4j_session(readonly=True) as session:
            result = session.run(query, params or {})
            return _normalize_records(result)
    except Neo4jUnavailableError:
        return []


def run_write(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute a write Cypher query and return dictionaries."""
    with neo4j_session(readonly=False) as session:
        result = session.run(query, params or {})
        return _normalize_records(result)
