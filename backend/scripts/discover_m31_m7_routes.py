"""
One-off: fetch the full stop sequence for M31 and M7 to verify their
real routing before treating "M31 -> F" or "M79 -> M7" as legitimate
route options.

    py -3 backend/scripts/discover_m31_m7_routes.py
"""

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.environ["MTA_BUS_TIME_API_KEY"]

ROUTES = [
    ("MTA NYCT_M31", "M31"),
    ("MTA NYCT_M7", "M7"),
]


def print_route_stops(route_id: str, label: str):
    print(f"\n=== {label} ({route_id}) ===")
    resp = requests.get(
        f"https://bustime.mta.info/api/where/stops-for-route/{route_id}.json",
        params={"key": API_KEY, "version": 2},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        return

    data = resp.json()["data"]
    stops_by_id = {s["id"]: s for s in data["references"]["stops"]}

    for grouping in data["entry"]["stopGroupings"]:
        for group in grouping.get("stopGroups", []):
            name = group.get("name", {}).get("name")
            stop_ids = group.get("stopIds", [])
            print(f"\n  Direction: {name} ({len(stop_ids)} stops)")
            for sid in stop_ids:
                stop = stops_by_id.get(sid)
                if stop:
                    print(f"    id={stop['id']}  name={stop['name']}")


if __name__ == "__main__":
    for i, (route_id, label) in enumerate(ROUTES):
        if i > 0:
            print("\n(waiting 30s for rate limit...)")
            time.sleep(30)
        try:
            print_route_stops(route_id, label)
        except Exception as exc:
            print(f"  failed: {exc}")
