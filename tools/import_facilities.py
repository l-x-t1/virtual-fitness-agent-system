import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import init_db
from app.repositories import FitnessRepository, session_scope

DEFAULT_CSV = Path("tools/data_seed/shijiazhuang/shijiazhuang_venues.csv")
DEFAULT_AQI = 62


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def stable_bucket(text: str, mod: int) -> int:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % mod


def venue_payload(row: dict) -> dict:
    name = row.get("name") or row.get("keyword") or row.get("poi_id") or "石家庄运动场馆"
    source_id = row.get("poi_id") or row.get("source") or name
    lat = float(row.get("latitude") or row.get("lat") or 38.047)
    lon = float(row.get("longitude") or row.get("lon") or 114.514)
    crowd_index = 20 + stable_bucket(source_id, 45)
    return {
        "name": str(name)[:100],
        "source_id": str(source_id)[:80],
        "display_name": str(name)[:160],
        "resolved_address": row.get("address") or row.get("district"),
        "name_source": row.get("source") or "seed",
        "location": row.get("address") or row.get("district") or f"石家庄 ({lat:.5f}, {lon:.5f})",
        "latitude": lat,
        "longitude": lon,
        "leisure_type": row.get("venue_group") or row.get("type"),
        "sport_type": row.get("suitable_sports") or "综合运动",
        "kind": "outdoor",
        "equipment": row.get("suitable_sports") or "公共运动设施、热身区",
        "capacity": int(float(row.get("capacity") or 50)),
        "crowd_index": crowd_index,
        "air_quality": DEFAULT_AQI,
        "open_hours": row.get("open_hours") or "06:00-22:00",
        "rating": float(row.get("rating") or 4.6),
        "facility_count": 1,
        "density_score": float(row.get("density_score") or crowd_index),
        "geometry_json": row.get("geometry_json") or None,
    }


def import_facilities(csv_path: Path) -> int:
    init_db()
    rows = load_csv(csv_path)
    if not rows:
        return 0
    with session_scope() as session:
        repo = FitnessRepository(session)
        for row in rows:
            repo.save_venue(venue_payload(row))
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Import venue seed data through SQLAlchemy ORM.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    count = import_facilities(args.csv)
    print(f"Imported or updated {count} facilities.")


if __name__ == "__main__":
    main()
