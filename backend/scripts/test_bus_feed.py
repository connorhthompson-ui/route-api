"""
Isolated test: find the real M79 SBS stop near 1st Ave & 79th St, then
fetch live arrival predictions for it via MTA Bus Time's SIRI API.

Not imported by the app -- run directly to sanity-check the feed:

    py -3 backend/scripts/test_bus_feed.py

Two phases, both printing raw results:
  1. Discovery: search for stops near 1st Ave & E 79th St, find the ones
     serving M79 SBS, and read off their real stop code + route id
     (rather than guessing the MTA's id formats).
  2. Live query: SIRI StopMonitoring for that stop code, printing
     predicted arrival times.

BusTime enforces ~1 request per 30s per key, shared across endpoints --
hitting phase 1 then phase 2 back-to-back trips it (the connection gets
reset rather than a clean 429), so this script waits between them.
"""

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.environ["MTA_BUS_TIME_API_KEY"]

# Approx coords for 1st Ave & E 79th St, Manhattan
SEARCH_LAT = 40.7717
SEARCH_LON = -73.9520


def _get_with_retries(url: str, params: dict, retries: int = 3) -> dict:
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            last_error = "connection reset (likely rate-limited)"
            print(f"  attempt {attempt + 1} failed ({last_error}), retrying...")
            time.sleep(5)
    raise RuntimeError(f"request to {url} failed after {retries} attempts: {last_error}")


def discover_stop():
    print("Phase 1: searching for stops near 1st Ave & E 79th St...")
    data = _get_with_retries(
        "https://bustime.mta.info/api/where/stops-for-location.json",
        {
            "key": API_KEY,
            "lat": SEARCH_LAT,
            "lon": SEARCH_LON,
            "radius": 300,
            "version": 2,
        },
    )
    stops = data["data"]["list"]

    m79_stops = [s for s in stops if any("M79" in r for r in s.get("routeIds", []))]

    print(f"  found {len(stops)} stops nearby, {len(m79_stops)} serving M79")
    for s in m79_stops:
        print(f"  stop_id={s['id']}  code={s.get('code')}  name={s['name']}  routes={s['routeIds']}")

    return m79_stops


def print_arrivals(stop_id: str, route_id: str):
    print(f"\nPhase 2: live arrivals for stop_id={stop_id}, route={route_id}")
    data = _get_with_retries(
        "https://bustime.mta.info/api/siri/stop-monitoring.json",
        {
            "key": API_KEY,
            "MonitoringRef": stop_id,
            "LineRef": route_id,
        },
    )

    visits = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0]["MonitoredStopVisit"]
    print(f"  {len(visits)} upcoming visit(s)")
    for visit in visits:
        call = visit["MonitoredVehicleJourney"]["MonitoredCall"]
        print(
            f"  {visit['MonitoredVehicleJourney']['PublishedLineName']}: "
            f"expected {call['ExpectedArrivalTime']} "
            f"({call['Extensions']['Distances']['PresentableDistance']})"
        )


if __name__ == "__main__":
    m79_stops = discover_stop()
    if m79_stops:
        target = m79_stops[0]
        route_id = next(r for r in target["routeIds"] if "M79" in r)
        print("\n(waiting 30s so phase 2 doesn't trip the per-key rate limit...)")
        time.sleep(30)
        print_arrivals(target["id"], route_id)
    else:
        print("No M79 stops found near the search point -- adjust SEARCH_LAT/LON.")
