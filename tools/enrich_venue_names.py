import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import init_db
from app.repositories import FitnessRepository, session_scope

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
    );
    out center tags 2000;
    """
    request = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
        headers={"User-Agent": "FitFlow venue name enrichment/2.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    features = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name:zh") or tags.get("name")
        lat_value = element.get("lat") or element.get("center", {}).get("lat")
        lon_value = element.get("lon") or element.get("center", {}).get("lon")
        if name and lat_value is not None and lon_value is not None:
            features.append({"name": str(name).strip(), "lat": float(lat_value), "lon": float(lon_value), "source": f"{element.get('type')}/{element.get('id')}"})
    return features


def enrich(lat, lon, radius_km, max_match_m):
    init_db()
    features = fetch_named_features(lat, lon, radius_km)
    with session_scope() as session:
        repo = FitnessRepository(session)
        venues = repo.venues(admin_fields=True)
        updated = 0
        for venue in venues:
            if venue.get("latitude") is None or venue.get("longitude") is None:
                continue
            best = None
            best_distance = None
            for feature in features:
                current_distance = distance_km(float(venue["latitude"]), float(venue["longitude"]), feature["lat"], feature["lon"])
                if current_distance * 1000 <= max_match_m and (best is None or current_distance < best_distance):
                    best = feature
                    best_distance = current_distance
            if best:
                repo.save_venue({**venue, "display_name": best["name"][:160], "resolved_address": best["name"], "name_source": f"overpass:{best['source']}"})
                updated += 1
    return len(venues), len(features), updated


def main():
    parser = argparse.ArgumentParser(description="Enrich venue display names through ORM.")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--radius-km", type=float, default=20)
    parser.add_argument("--max-match-m", type=float, default=350)
    args = parser.parse_args()
    started = time.time()
    venue_count, feature_count, update_count = enrich(args.lat, args.lon, args.radius_km, args.max_match_m)
    print(f"Checked {venue_count} venues, fetched {feature_count} features, updated {update_count} names in {time.time() - started:.1f}s.")


if __name__ == "__main__":
    main()
