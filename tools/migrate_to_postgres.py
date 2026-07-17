from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import init_db
from app.repositories import FitnessRepository, session_scope

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SEED_DIR = BASE_DIR / "tools" / "data_seed" / "shijiazhuang"
DEFAULT_SQLITE = DEFAULT_SEED_DIR / "shijiazhuang_fitness_reference.db"
DEFAULT_SQL_FILE = BASE_DIR / "virtual_fitness_agent_system.sql"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def import_exercises(repo: FitnessRepository, rows: list[dict]) -> int:
    count = 0
    for row in rows:
        name = row.get("name")
        if not name:
            continue
        repo.save_exercise({
            "name": name,
            "category": row.get("category") or row.get("preference_type") or "综合训练",
            "difficulty": 1,
            "target": row.get("target_body_part") or row.get("goal_tags") or "综合体能",
            "equipment": row.get("location_type") or "徒手",
            "standard_json": json.dumps({"source": "seed", "intensity": row.get("intensity"), "duration_min": row.get("duration_min")}, ensure_ascii=False),
        })
        count += 1
    return count


def import_venues(repo: FitnessRepository, rows: list[dict]) -> int:
    count = 0
    for row in rows:
        name = row.get("name") or row.get("keyword") or row.get("poi_id")
        if not name:
            continue
        repo.save_venue({
            "name": name[:100],
            "source_id": (row.get("poi_id") or name)[:80],
            "display_name": name[:160],
            "resolved_address": row.get("address"),
            "name_source": row.get("source") or "migration",
            "location": row.get("address") or row.get("district") or "石家庄",
            "latitude": float(row.get("latitude") or 38.047),
            "longitude": float(row.get("longitude") or 114.514),
            "sport_type": row.get("suitable_sports") or row.get("type") or "综合运动",
            "leisure_type": row.get("venue_group"),
            "kind": "outdoor",
            "equipment": row.get("suitable_sports") or "公共运动设施",
            "capacity": 50,
            "crowd_index": 30,
            "air_quality": 50,
            "open_hours": "06:00-22:00",
            "rating": float(row.get("rating") or 4.6),
            "facility_count": 1,
            "density_score": 30,
        })
        count += 1
    return count


def sqlite_tables(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        table_rows = getattr(conn, "execute")("select name from sqlite_master where type = 'table'").fetchall()
        data = {}
        for item in table_rows:
            table = item["name"]
            data[table] = [dict(row) for row in getattr(conn, "execute")(f"select * from {table}").fetchall()]
        return data
    finally:
        conn.close()


def migrate(seed_dir: Path, sqlite_path: Path, sql_file: Path) -> dict:
    init_db()
    stats = {"sql_seed_seen": sql_file.exists(), "exercise_rows": 0, "venue_rows": 0, "sqlite_tables": 0}
    with session_scope() as session:
        repo = FitnessRepository(session)
        stats["exercise_rows"] += import_exercises(repo, read_csv(seed_dir / "exercise_library_seed.csv"))
        stats["venue_rows"] += import_venues(repo, read_csv(seed_dir / "shijiazhuang_venues.csv"))
        sqlite_data = sqlite_tables(sqlite_path)
        stats["sqlite_tables"] = len(sqlite_data)
        stats["exercise_rows"] += import_exercises(repo, sqlite_data.get("exercise_library_seed", []))
        stats["venue_rows"] += import_venues(repo, sqlite_data.get("shijiazhuang_venues", []))
    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate historical seed data into PostgreSQL through SQLAlchemy ORM.")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    parser.add_argument("--sql-file", type=Path, default=DEFAULT_SQL_FILE)
    args = parser.parse_args()
    stats = migrate(args.seed_dir, args.sqlite, args.sql_file)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
