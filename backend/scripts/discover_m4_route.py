"""
One-off: fetch M4's full stop sequence to verify its real routing near
5th/Madison Ave & 79th St and confirm how close it gets to 1221 Ave of
the Americas before treating "M79 -> M4" as a legitimate route option.

    py -3 backend/scripts/discover_m4_route.py
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.environ["MTA_BUS_TIME_API_KEY"]

resp = requests.get(
    "https://bustime.mta.info/api/where/stops-for-route/MTA%20NYCT_M4.json",
    params={"key": API_KEY, "version": 2},
    timeout=10,
)
resp.raise_for_status()
data = resp.json()["data"]
stops_by_id = {s["id"]: s for s in data["references"]["stops"]}

for grouping in data["entry"]["stopGroupings"]:
    for group in grouping.get("stopGroups", []):
        name = group.get("name", {}).get("name")
        stop_ids = group.get("stopIds", [])
        print(f"\nDirection: {name} ({len(stop_ids)} stops)")
        for sid in stop_ids:
            stop = stops_by_id.get(sid)
            if stop and (
                "79" in stop["name"]
                or " AV/W 4" in stop["name"]
                or " AV/W 5" in stop["name"]
            ):
                print(f"  id={stop['id']}  name={stop['name']}")
