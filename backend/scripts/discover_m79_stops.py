"""
One-off discovery: find the exact M79 SBS stop_ids + directions near
1st Ave & 79th St and near Lexington Ave & 79th St, so the live route
wiring boards/alights at the correct corner and direction.

    py -3 backend/scripts/discover_m79_stops.py
"""

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.environ["MTA_BUS_TIME_API_KEY"]

POINTS = [
    ("1st Ave & E 79th St", 40.7717, -73.9520),
    ("Lexington Ave & E 79th St", 40.7736, -73.9587),
]


def search(label: str, lat: float, lon: float):
    print(f"\n{label} ({lat}, {lon}):")
    resp = requests.get(
        "https://bustime.mta.info/api/where/stops-for-location.json",
        params={"key": API_KEY, "lat": lat, "lon": lon, "radius": 250, "version": 2},
        timeout=10,
    )
    resp.raise_for_status()
    stops = resp.json()["data"]["list"]
    m79_stops = [s for s in stops if any("M79" in r for r in s.get("routeIds", []))]
    for s in m79_stops:
        print(
            f"  id={s['id']}  code={s.get('code')}  name={s['name']}  "
            f"direction={s.get('direction')}  lat={s['lat']}  lon={s['lon']}"
        )


if __name__ == "__main__":
    for i, (label, lat, lon) in enumerate(POINTS):
        if i > 0:
            print("\n(waiting 30s for rate limit...)")
            time.sleep(30)
        search(label, lat, lon)
