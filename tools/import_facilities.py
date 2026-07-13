import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import connect, init_db


DEFAULT_CSV = Path(r"D:\xwechat_files\wxid_lyqfqbr97x9k22_9907\msg\file\2026-05\facilities.csv")
DEFAULT_GEOJSON = Path(r"D:\xwechat_files\wxid_lyqfqbr97x9k22_9907\msg\file\2026-05\export.geojson")
DEFAULT_AQI = 62

LEISURE_LABELS = {
    "pitch": "运动场地",
    "track": "跑道",
    "sports_centre": "体育中心",
    "fitness_station": "健身点",
}

SPORT_LABELS = {
    "athletics": "田径",
    "badminton": "羽毛球",
    "basketball": "篮球",
    "climbing": "攀岩",
    "multi": "综合运动",
    "running": "跑步",
    "soccer": "足球",
    "table_tennis": "乒乓球",
    "tennis": "网球",
    "volleyball": "排球",
}

EQUIPMENT_BY_SPORT = {
    "athletics": "跑道、田径训练区、热身区",
    "badminton": "羽毛球场、照明设施、休息区",
    "basketball": "篮球场、篮架、夜间照明",
    "climbing": "攀岩墙、安全垫、力量训练区",
    "multi": "综合球场、体能训练区、公共健身器材",
    "running": "跑道、步道、拉伸区",
    "soccer": "足球场、热身区、看台或休息区",
    "table_tennis": "乒乓球台、休息区",
    "tennis": "网球场、围网、夜间照明",
    "volleyball": "排球场、球网、休息区",
}


def load_geojson(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        feature.get("properties", {}).get("@id"): feature
        for feature in data.get("features", [])
        if feature.get("properties", {}).get("@id")
    }


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def centroid_from_geometry(geometry):
    points = []

    def collect(value):
        if isinstance(value, list) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            points.append((float(value[1]), float(value[0])))
            return
        if isinstance(value, list):
            for item in value:
                collect(item)

    collect((geometry or {}).get("coordinates", []))
    if not points:
        return None, None
    return sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)


def grid_key(lat, lon, size=0.02):
    return round(float(lat) / size), round(float(lon) / size)


def stable_bucket(text, mod):
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % mod


def label_for(leisure, sport):
    leisure_label = LEISURE_LABELS.get(leisure, leisure or "运动点")
    sport_label = SPORT_LABELS.get(sport, sport or "")
    return f"{sport_label}{leisure_label}" if sport_label and sport_label not in leisure_label else leisure_label


def build_name(source_id, properties, leisure, sport):
    explicit = properties.get("name:zh") or properties.get("name") or properties.get("name:en")
    suffix = source_id.split("/")[-1]
    if explicit:
        name = str(explicit).strip()
        return f"{name[:82]} {suffix}"[:100]
    return f"{label_for(leisure, sport)} {suffix}"[:100]


def build_display_name(source_id, properties, leisure, sport):
    explicit = properties.get("name:zh") or properties.get("name") or properties.get("name:en")
    if explicit:
        return str(explicit).strip()[:160], "osm_name"
    return f"未命名{label_for(leisure, sport)}"[:160], "type_fallback"


def build_location(lat, lon, properties):
    name = properties.get("name:zh") or properties.get("name")
    if name:
        return f"{name}附近 ({lat:.5f}, {lon:.5f})"
    return f"石家庄周边运动位置 ({lat:.5f}, {lon:.5f})"


def build_record(row, feature, cell_count, max_cell_count):
    properties = (feature or {}).get("properties", {})
    source_id = row.get("id") or properties.get("@id")
    leisure = row.get("leisure") or properties.get("leisure") or ""
    sport = row.get("sport") or properties.get("sport") or ""
    lat = float(row["lat"])
    lon = float(row["lon"])
    density_score = round(cell_count / max_cell_count * 100, 1) if max_cell_count else 0
    crowd_base = 16 + min(44, cell_count * 4)
    sport_bonus = 8 if sport in {"basketball", "soccer"} else 5 if sport in {"badminton", "tennis", "running"} else 2
    crowd_index = max(8, min(96, crowd_base + sport_bonus + stable_bucket(source_id, 17)))
    rating = round(4.15 + (100 - min(100, crowd_index)) / 250 + stable_bucket(source_id + "rating", 8) / 100, 1)
    capacity = 220 if leisure == "sports_centre" else 90 if leisure == "track" else 48 if sport in {"soccer", "basketball"} else 32
    geometry = (feature or {}).get("geometry")
    geometry_json = json.dumps(geometry, ensure_ascii=False, separators=(",", ":")) if geometry else None
    display_name, name_source = build_display_name(source_id, properties, leisure, sport)
    return (
        build_name(source_id, properties, leisure, sport),
        source_id,
        display_name,
        None,
        name_source,
        build_location(lat, lon, properties),
        lat,
        lon,
        leisure,
        sport,
        "indoor" if leisure == "sports_centre" else "outdoor",
        EQUIPMENT_BY_SPORT.get(sport, "公共运动场地、基础健身设施、热身区"),
        capacity,
        crowd_index,
        DEFAULT_AQI,
        "06:00-22:00" if leisure != "sports_centre" else "08:00-22:00",
        rating,
        cell_count,
        density_score,
        geometry_json,
    )


def merge_rows(csv_rows, geo_features):
    rows_by_id = {row["id"]: row for row in csv_rows if row.get("id") and row.get("lat") and row.get("lon")}
    for source_id, feature in geo_features.items():
        if source_id in rows_by_id:
            continue
        lat, lon = centroid_from_geometry(feature.get("geometry"))
        if lat is None or lon is None:
            continue
        properties = feature.get("properties", {})
        rows_by_id[source_id] = {
            "id": source_id,
            "leisure": properties.get("leisure", ""),
            "sport": properties.get("sport", ""),
            "lat": str(lat),
            "lon": str(lon),
        }
    return list(rows_by_id.values())


def import_facilities(csv_path, geojson_path):
    csv_rows = load_csv(csv_path)
    geo_features = load_geojson(geojson_path)
    rows = merge_rows(csv_rows, geo_features)
    cell_counts = Counter(grid_key(row["lat"], row["lon"]) for row in rows)
    max_cell_count = max(cell_counts.values()) if cell_counts else 1
    records = [
        build_record(row, geo_features.get(row["id"]), cell_counts[grid_key(row["lat"], row["lon"])], max_cell_count)
        for row in rows
    ]
    init_db()
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO venues(
                name, source_id, display_name, resolved_address, name_source,
                location, latitude, longitude, leisure_type, sport_type, kind,
                equipment, capacity, crowd_index, air_quality, open_hours, rating,
                facility_count, density_score, geometry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                display_name = COALESCE(NULLIF(venues.display_name, ''), VALUES(display_name)),
                resolved_address = COALESCE(venues.resolved_address, VALUES(resolved_address)),
                name_source = COALESCE(venues.name_source, VALUES(name_source)),
                location = VALUES(location),
                latitude = VALUES(latitude),
                longitude = VALUES(longitude),
                leisure_type = VALUES(leisure_type),
                sport_type = VALUES(sport_type),
                kind = VALUES(kind),
                equipment = VALUES(equipment),
                capacity = VALUES(capacity),
                crowd_index = VALUES(crowd_index),
                air_quality = VALUES(air_quality),
                open_hours = VALUES(open_hours),
                rating = VALUES(rating),
                facility_count = VALUES(facility_count),
                density_score = VALUES(density_score),
                geometry_json = VALUES(geometry_json)
            """,
            records,
        )
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Import OSM fitness facilities into the FitFlow venues table.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    args = parser.parse_args()
    count = import_facilities(args.csv, args.geojson)
    print(f"Imported or updated {count} facilities.")


if __name__ == "__main__":
    main()
