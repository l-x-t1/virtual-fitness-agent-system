"""SQLite → PostgreSQL 全量数据迁移脚本。

将当前 SQLite 数据库（默认 fitness.db）的全部业务表，通过 SQLAlchemy ORM
复制到目标数据库（默认 PostgreSQL，见 .env 的 DATABASE_URL）。

用法:
  # 1. 先初始化目标库表结构（目标库必须可达）
  python -m tools.migrate_sqlite_to_postgres --init

  # 2. 全量迁移（按依赖顺序复制所有表，含 BodyPart / exercise_body_parts）
  python -m tools.migrate_sqlite_to_postgres

  # 3. 干跑（不写目标库，只统计源库表和数据量，验证脚本可运行）
  python -m tools.migrate_sqlite_to_postgres --dry-run

  # 4. 指定源库 / 目标库连接串
  python -m tools.migrate_sqlite_to_postgres \
      --source sqlite:///fitness.db \
      --target postgresql+psycopg://postgres:postgres@localhost:5432/virtual_fitness_agent_system

真实切换步骤（.env 改为 PostgreSQL 后）:
  1. 在 PostgreSQL 建库: CREATE DATABASE virtual_fitness_agent_system;
  2. python -m tools.migrate_sqlite_to_postgres --init
  3. python -m tools.migrate_sqlite_to_postgres
  4. 将 .env 的 DATABASE_URL 改为 postgresql+psycopg://... 后重启服务
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.db.base import Base
from app.db.models import BodyPart, Exercise, FitnessEquipment, TrainingSession, User, Venue

# 迁移顺序：先父表后子表，保证外键引用完整
MODEL_ORDER: list[tuple[object, str]] = [
    (User, "users"),
    (Venue, "venues"),
    (Exercise, "exercises"),
    (FitnessEquipment, "fitness_equipment"),
    (TrainingSession, "sessions"),
    (BodyPart, "body_parts"),
    (Base.metadata.tables["exercise_body_parts"], "exercise_body_parts"),
]


def _table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _copy_table(src: Engine, dst: Engine, model_or_table, table_name: str) -> int:
    if table_name not in _table_names(src):
        return 0

    from sqlalchemy import select

    if hasattr(model_or_table, "insert"):
        # 关联表（Table 对象）：无 datetime，直接原生 INSERT
        with src.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(text(f"SELECT * FROM \"{table_name}\""))]
        if not rows:
            return 0
        with dst.begin() as conn:
            for row in rows:
                conn.execute(model_or_table.insert().values(**row))
        return len(rows)

    # ORM 模型：通过 ORM 读取，datetime 列自动还原为 datetime 对象
    from sqlalchemy.orm import Session

    with Session(src) as session:
        objects = list(session.scalars(select(model_or_table)).all())
    if not objects:
        return 0
    cols = [c.key for c in model_or_table.__table__.columns]
    with dst.begin() as conn:
        for obj in objects:
            payload = {k: getattr(obj, k) for k in cols if getattr(obj, k) is not None}
            conn.execute(model_or_table.__table__.insert().values(**payload))
    return len(objects)


def migrate_full(source_url: str, target_url: str, dry_run: bool = False) -> dict:
    src = create_engine(source_url)
    dst = create_engine(target_url)

    if not dry_run:
        Base.metadata.create_all(dst)

    stats: dict[str, int] = {}
    for model, table_name in MODEL_ORDER:
        if dry_run:
            stats[table_name] = len(_table_names(src).intersection({table_name}))
        else:
            stats[table_name] = _copy_table(src, dst, model, table_name)
    return stats


def main():
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 全量数据迁移")
    parser.add_argument("--source", default="sqlite:///fitness.db", help="源库连接串，默认当前 fitness.db")
    parser.add_argument("--target", default=None, help="目标库连接串，默认取 settings.database_url")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写目标库")
    parser.add_argument("--init", action="store_true", help="只在目标库建表，不拷贝数据")
    args = parser.parse_args()

    from app.core.config import settings

    target = args.target or settings.database_url
    print(f"源库:   {args.source}")
    print(f"目标库: {target}")

    if args.init:
        dst = create_engine(target)
        Base.metadata.create_all(dst)
        print("目标库表结构创建完成。")
        return

    stats = migrate_full(args.source, target, dry_run=args.dry_run)
    print(json_dumps(stats))


def json_dumps(data: dict) -> str:
    import json
    return json.dumps(data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
