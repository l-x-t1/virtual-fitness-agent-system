"""
Neo4j 客户端 — 连接管理与单例
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager

from neo4j import Driver, GraphDatabase
from neo4j import Session as Neo4jSession

from app.core.config import settings

logger = logging.getLogger("fitness.neo4j")

_driver: Driver | None = None
_disabled: bool = False
_last_check_time: float = 0
_check_interval: float = 60  # 连不上就 60 秒内不再重试


def _create_driver() -> Driver | None:
    if _disabled:
        return None
    try:
        return GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            max_connection_lifetime=300,
            max_connection_pool_size=10,
            connection_acquisition_timeout=2,  # 2 秒快速失败，不拖慢页面
        )
    except Exception:
        logger.warning("Failed to create Neo4j driver; graph features disabled.")
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
    global _driver, _disabled, _last_check_time
    if _driver:
        try:
            _driver.close()
        except Exception:
            pass
    _driver = None
    _disabled = False
    _last_check_time = 0


def is_available() -> bool:
    global _disabled, _last_check_time

    if _disabled:
        return False

    # 刚检查过不久，直接返回上次结果（避免每次都超时等待）
    now = time.time()
    if _last_check_time > 0 and (now - _last_check_time) < _check_interval:
        return False

    _last_check_time = now
    driver = get_driver()
    if driver is None:
        _disabled = True
        return False
    try:
        with driver.session(database=settings.neo4j_database) as session:
            session.run("RETURN 1")
        return True
    except Exception:
        _disabled = True  # 连不上就记住，60 秒内不再试
        return False


@contextmanager
def neo4j_session(readonly: bool = False) -> Generator[Neo4jSession, None, None]:
    driver = get_driver()
    if driver is None:
        raise RuntimeError("Neo4j is not available")
    session = driver.session(
        database=settings.neo4j_database,
        default_access_mode="READ" if readonly else "WRITE",
    )
    try:
        yield session
    finally:
        session.close()


def run_read(query: str, params: dict | None = None) -> list[dict]:
    """执行只读 Cypher 查询，返回 dict 列表"""
    try:
        with neo4j_session(readonly=True) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]
    except RuntimeError:
        return []


def run_write(query: str, params: dict | None = None) -> list[dict]:
    """执行写入 Cypher 查询"""
    with neo4j_session(readonly=False) as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]
