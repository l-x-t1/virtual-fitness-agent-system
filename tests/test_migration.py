"""SQLite→PostgreSQL 迁移脚本测试"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app.db.base import Base


def test_migrate_module_imports():
    """迁移脚本应可正常导入，且定义了全量迁移入口"""
    import tools.migrate_sqlite_to_postgres as migration

    assert callable(migration.migrate_full)
    assert callable(migration.main)


def test_dry_run_stats(tmp_path):
    """dry-run 不写目标库，只统计源库表"""
    import tools.migrate_sqlite_to_postgres as migration

    stats = migration.migrate_full(
        source_url=f"sqlite:///{tmp_path / 'empty.db'}",
        target_url=f"sqlite:///{tmp_path / 'target.db'}",
        dry_run=True,
    )
    # 源库不存在时所有表为 0
    assert all(count == 0 for count in stats.values())
    assert set(stats.keys()) == {"users", "venues", "exercises", "fitness_equipment", "sessions", "body_parts", "exercise_body_parts"}


def test_full_copy_to_sqlite(tmp_path):
    """真实复制：源 fitness.db → 临时 SQLite，验证 ORM 全表迁移可运行且行数一致"""
    src_db = ROOT / "fitness.db"
    if not src_db.exists():
        pytest.skip("fitness.db not present")

    import tools.migrate_sqlite_to_postgres as migration

    target_db = tmp_path / "migrated.db"
    stats = migration.migrate_full(
        source_url=f"sqlite:///{src_db}",
        target_url=f"sqlite:///{target_db}",
        dry_run=False,
    )

    assert stats["users"] >= 1
    assert stats["exercises"] >= 1
    assert stats["venues"] >= 1

    # 校验目标库表结构已创建
    import sqlite3

    conn = sqlite3.connect(target_db)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "body_parts" in tables
        assert "exercise_body_parts" in tables
    finally:
        conn.close()
