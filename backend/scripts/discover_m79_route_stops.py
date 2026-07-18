"""
One-off: fetch M79 SBS's stops grouped by direction (0/1) with headsigns,
so we know unambiguously which stop_id is the westbound-towards-Lex
boarding point vs the eastbound-towards-1st-Ave one.

    py -3 backend/scripts/discover_m79_route_stops.py
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.environ["MTA_BUS_TIME_API_KEY"]

resp = requests.get(
    "https://bustime.mta.info/api/where/stops-for-route/MTA%20NYCT_M79+.json",
    params={"key": API_KEY, "version": 2},
    timeout=10,
)
resp.raise_for_status()
data = resp.json()["data"]

for grouping in data["entry"]["stopGroupings"]:
    for group in grouping.get("stopGroups", []):
        name = group.get("name", {}).get("name")
        stop_ids = group.get("stopIds", [])
        print(f"\nDirection group: {name}  ({len(stop_ids)} stops)")
        for sid in stop_ids:
            stop = next((s for s in data["references"]["stops"] if s["id"] == sid), None)
            if stop and "79" in stop["name"]:
                print(f"  id={stop['id']}  code={stop.get('code')}  name={stop['name']}")
