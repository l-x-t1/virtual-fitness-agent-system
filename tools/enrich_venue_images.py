import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import connect, init_db


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
DEFAULT_LAT = 38.047
DEFAULT_LON = 114.514


def bbox_for(lat, lon, radius_km):
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat - delta_lat, lon - delta_lon, lat + delta_lat, lon + delta_lon


def commons_request(params):
    query = urllib.parse.urlencode({
        "format": "json",
        "origin": "*",
        **params,
    })
    request = urllib.request.Request(
        f"{COMMONS_API}?{query}",
        headers={"User-Agent": "FitFlow venue image enrichment/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            time.sleep(8)
            return {}
        raise
    except URLError:
        time.sleep(2)
        return {}


def search_images(lat, lon, radius_m=600, limit=10):
    payload = commons_request({
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lon}",
        "gsradius": int(radius_m),
        "gslimit": int(limit),
        "gsnamespace": 6,
    })
    return payload.get("query", {}).get("geosearch", [])


def image_info(title):
    payload = commons_request({
        "action": "query",
        "prop": "imageinfo",
        "titles": title,
        "iiprop": "url|extmetadata",
        "iiurlwidth": 720,
    })
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        metadata = info.get("extmetadata", {})
        license_short = metadata.get("LicenseShortName", {}).get("value", "")
        artist = metadata.get("Artist", {}).get("value", "")
        attribution = "Wikimedia Commons"
        if license_short:
            attribution = f"Wikimedia Commons · {license_short}"
        if artist and len(artist) < 80:
            clean_artist = artist.replace("<span>", "").replace("</span>", "")
            attribution = f"{attribution} · {clean_artist}"
        return {
            "url": info.get("thumburl") or info.get("url"),
            "source": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title)}",
            "attribution": attribution[:255],
        }
    return None


def image_for_venue(venue, radius_m):
    candidates = search_images(float(venue["latitude"]), float(venue["longitude"]), radius_m=radius_m)
    for candidate in candidates:
        title = candidate.get("title", "")
        lower = title.lower()
        if not lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        if not title_matches_venue(title, venue):
            continue
        info = image_info(title)
        if info and info.get("url"):
            return info
        time.sleep(0.1)
    return None


def title_matches_venue(title, venue):
    name = str(venue.get("display_name") or venue.get("name") or "")
    if name.startswith("未命名"):
        return False
    compact_title = title.lower().replace("file:", "").replace("_", "")
    tokens = [
        token
        for token in name.replace("足球场", "").replace("篮球场", "").replace("运动场地", "").split()
        if len(token) >= 2
    ]
    chinese_chunks = [name[:4], name[:6]]
    return any(token and token.lower() in compact_title for token in tokens + chinese_chunks)


def enrich(limit, radius_m, only_missing, lat=None, lon=None, radius_km=15):
    init_db()
    sql = """
        SELECT id, display_name, name, latitude, longitude, image_url
        FROM venues
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """
    params = []
    if lat is not None and lon is not None:
        south, west, north, east = bbox_for(lat, lon, radius_km)
        sql += " AND latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?"
        params.extend([south, north, west, east])
    if only_missing:
        sql += " AND (image_url IS NULL OR image_url = '')"
    sql += " ORDER BY crowd_index, density_score DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        venues = conn.execute(sql, tuple(params)).fetchall()

    updated = 0
    for venue in venues:
        info = image_for_venue(venue, radius_m)
        if not info:
            continue
        with connect() as conn:
            conn.execute(
                """
                UPDATE venues
                SET image_url = ?, image_source = ?, image_attribution = ?
                WHERE id = ?
                """,
                (info["url"], info["source"], info["attribution"], venue["id"]),
            )
        updated += 1
        time.sleep(1.0)
    return len(venues), updated


def main():
    parser = argparse.ArgumentParser(description="Enrich venue cards with online images from Wikimedia Commons.")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--radius-m", type=int, default=700)
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--radius-km", type=float, default=15)
    parser.add_argument("--all", action="store_true", help="Recheck venues that already have images.")
    args = parser.parse_args()
    started = time.time()
    checked, updated = enrich(
        args.limit,
        args.radius_m,
        only_missing=not args.all,
        lat=args.lat,
        lon=args.lon,
        radius_km=args.radius_km,
    )
    print(f"Checked {checked} venues, updated {updated} images in {time.time() - started:.1f}s.")


if __name__ == "__main__":
    main()
