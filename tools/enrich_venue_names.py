import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import connect, init_db


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_LAT = 38.047
DEFAULT_LON = 114.514


def distance_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(a))


def bbox_for(lat, lon, radius_km):
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat - delta_lat, lon - delta_lon, lat + delta_lat, lon + delta_lon


def fetch_named_features(lat, lon, radius_km):
    south, west, north, east = bbox_for(lat, lon, radius_km)
    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    query = f"""
    [out:json][timeout:60];
    (
      nwr["name"]["leisure"~"pitch|track|sports_centre|fitness_station|park"]({bbox});
      nwr["name"]["sport"]({bbox});
      nwr["name"]["amenity"~"school|university|college"]({bbox});
      nwr["name"]["landuse"~"recreation_ground|grass"]({bbox});
    );
    out center tags 2000;
    """
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={"User-Agent": "FitFlow venue name enrichment/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    features = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name:zh") or tags.get("name")
        lat_value = element.get("lat") or element.get("center", {}).get("lat")
        lon_value = element.get("lon") or element.get("center", {}).get("lon")
        if not name or lat_value is None or lon_value is None:
            continue
        features.append({
            "name": str(name).strip(),
            "lat": float(lat_value),
            "lon": float(lon_value),
            "sport": tags.get("sport", ""),
            "leisure": tags.get("leisure", ""),
            "amenity": tags.get("amenity", ""),
            "source": f"{element.get('type')}/{element.get('id')}",
        })
    return features


def name_for_venue(venue, feature):
    sport = venue.get("sport_type") or ""
    category = {
        "basketball": "篮球场",
        "soccer": "足球场",
        "running": "跑道",
        "tennis": "网球场",
        "badminton": "羽毛球场",
        "table_tennis": "乒乓球场",
        "volleyball": "排球场",
        "multi": "综合运动场",
    }.get(sport, "运动场地")
    feature_sport = feature.get("sport") or ""
    feature_leisure = feature.get("leisure") or ""
    if feature_sport == sport or feature_leisure in {"pitch", "track", "sports_centre", "fitness_station"}:
        return feature["name"][:160], "overpass_sports_name"
    return f"{feature['name']} {category}"[:160], "overpass_nearby_place"


def enrich(lat, lon, radius_km, max_match_m):
    init_db()
    south, west, north, east = bbox_for(lat, lon, radius_km)
    with connect() as conn:
        venues = conn.execute(
            """
            SELECT id, name, display_name, latitude, longitude, sport_type, leisure_type
            FROM venues
            WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
            """,
            (south, north, west, east),
        ).fetchall()
    features = fetch_named_features(lat, lon, radius_km)
    updates = []
    for venue in venues:
        best = None
        best_distance = None
        for feature in features:
            current_distance = distance_km(
                float(venue["latitude"]),
                float(venue["longitude"]),
                feature["lat"],
                feature["lon"],
            )
            if current_distance * 1000 > max_match_m:
                continue
            if best is None or current_distance < best_distance:
                best = feature
                best_distance = current_distance
        if not best:
            continue
        display_name, source = name_for_venue(venue, best)
        updates.append((
            display_name,
            best["name"],
            f"{source}:{best['source']}",
            venue["id"],
        ))
    if updates:
        with connect() as conn:
            conn.executemany(
                """
                UPDATE venues
                SET display_name = ?, resolved_address = ?, name_source = ?
                WHERE id = ?
                """,
                updates,
            )
    return len(venues), len(features), len(updates)


def main():
    parser = argparse.ArgumentParser(description="Enrich venue display names from online OSM Overpass data.")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--radius-km", type=float, default=20)
    parser.add_argument("--max-match-m", type=float, default=350)
    args = parser.parse_args()
    started = time.time()
    venue_count, feature_count, update_count = enrich(args.lat, args.lon, args.radius_km, args.max_match_m)
    print(
        f"Checked {venue_count} venues, fetched {feature_count} named online features, "
        f"updated {update_count} names in {time.time() - started:.1f}s."
    )


if __name__ == "__main__":
    main()
