import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import init_db
from app.repositories import FitnessRepository, session_scope

COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def commons_request(params):
    query = urllib.parse.urlencode({"format": "json", "origin": "*", **params})
    request = urllib.request.Request(f"{COMMONS_API}?{query}", headers={"User-Agent": "FitFlow venue image enrichment/2.0"})
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
    payload = commons_request({"action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}", "gsradius": int(radius_m), "gslimit": int(limit), "gsnamespace": 6})
    return payload.get("query", {}).get("geosearch", [])


def image_info(title):
    payload = commons_request({"action": "query", "prop": "imageinfo", "titles": title, "iiprop": "url|extmetadata", "iiurlwidth": 720})
    for page in payload.get("query", {}).get("pages", {}).values():
        infos = page.get("imageinfo") or []
        if infos:
            info = infos[0]
            metadata = info.get("extmetadata", {})
            license_short = metadata.get("LicenseShortName", {}).get("value", "")
            return {"url": info.get("thumburl") or info.get("url"), "source": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title)}", "attribution": f"Wikimedia Commons {license_short}".strip()[:255]}
    return None


def image_for_venue(venue, radius_m):
    for candidate in search_images(float(venue["latitude"]), float(venue["longitude"]), radius_m=radius_m):
        title = candidate.get("title", "")
        if title.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            info = image_info(title)
            if info and info.get("url"):
                return info
            time.sleep(0.1)
    return None


def enrich(limit, radius_m, only_missing, lat=None, lon=None, radius_km=15):
    init_db()
    with session_scope() as session:
        repo = FitnessRepository(session)
        venues = [item for item in repo.venues(limit=limit, admin_fields=True) if item.get("latitude") is not None and item.get("longitude") is not None]
        if only_missing:
            venues = [item for item in venues if not item.get("image_url")]
        updated = 0
        for venue in venues[:limit]:
            info = image_for_venue(venue, radius_m)
            if info:
                repo.save_venue({**venue, "image_url": info["url"], "image_source": info["source"], "image_attribution": info["attribution"]})
                updated += 1
                time.sleep(1.0)
    return len(venues), updated


def main():
    parser = argparse.ArgumentParser(description="Enrich venue cards with online images through ORM.")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--radius-m", type=int, default=700)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    started = time.time()
    checked, updated = enrich(args.limit, args.radius_m, only_missing=not args.all)
    print(f"Checked {checked} venues, updated {updated} images in {time.time() - started:.1f}s.")


if __name__ == "__main__":
    main()
