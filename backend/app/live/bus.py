"""
Live bus arrival + ride-time predictions via MTA Bus Time's SIRI
StopMonitoring API. Requires MTA_BUS_TIME_API_KEY. The key is
rate-limited to ~1 request per 30s, GLOBALLY -- shared across all stops
and routes, not per-stop. With several different bus legs in the route
catalog, a single /best-route request can ask about multiple distinct
(stop, route) pairs within milliseconds of each other, which would blow
the limit if each made its own request. So there are two layers:
  1. A per-(stop, route) cache (25s) for repeat lookups of the same leg.
  2. A global cooldown gate: if a live call was made anywhere in the last
     ~28s, new *different* lookups skip the network call entirely and
     fall back immediately, rather than firing a request we know will
     get rate-limited.

Ride time (not just wait time) comes from the same request: requesting
StopMonitoringDetailLevel=calls returns OnwardCalls -- the same vehicle's
predicted arrival at every subsequent stop on its route. If the leg's
alighting stop appears there, that gives a genuine live ride time instead
of a static guess, using the exact same API call and rate-limit budget
already spent on the wait time.
"""

import os
import time
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional, TypedDict

import requests

# Same rationale as subway.py: live feeds occasionally serve a stale or
# corrupt prediction claiming a vehicle is hours away. No real bus route
# has a gap that large, so anything beyond this is treated as unreliable
# and the caller falls back to the static estimate instead.
MAX_PLAUSIBLE_WAIT_MIN = 60

_CACHE_TTL_SECONDS = 25
_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_cache_lock = Lock()

_GLOBAL_COOLDOWN_SECONDS = 28
_last_request_monotonic: Optional[float] = None
_global_lock = Lock()


class BusLegPrediction(TypedDict):
    board_time: datetime
    ride_min: Optional[float]  # None if the alighting stop wasn't in OnwardCalls


def _stop_monitoring(stop_id: str, route_id: str) -> Optional[dict]:
    global _last_request_monotonic

    key = (stop_id, route_id)
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

    with _global_lock:
        if (
            _last_request_monotonic is not None
            and now - _last_request_monotonic < _GLOBAL_COOLDOWN_SECONDS
        ):
            return None  # would get rate-limited -- skip straight to fallback
        _last_request_monotonic = now

    api_key = os.environ["MTA_BUS_TIME_API_KEY"]
    resp = requests.get(
        "https://bustime.mta.info/api/siri/stop-monitoring.json",
        params={
            "key": api_key,
            "MonitoringRef": stop_id,
            "LineRef": route_id,
            "StopMonitoringDetailLevel": "calls",
            "MaximumNumberOfCallsOnwards": "30",
        },
        timeout=8,
    )
    resp.raise_for_status()
    data = resp.json()

    with _cache_lock:
        _cache[key] = (now, data)
    return data


def _onward_ride_min(visit: dict, board_time: datetime, alight_stop_id: str) -> Optional[float]:
    onward_calls = visit["MonitoredVehicleJourney"].get("OnwardCalls", {}).get("OnwardCall", [])
    for call in onward_calls:
        if call.get("StopPointRef") != alight_stop_id:
            continue
        raw = call.get("ExpectedArrivalTime") or call.get("AimedArrivalTime")
        if not raw:
            return None
        try:
            alight_time = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return (alight_time - board_time).total_seconds() / 60
    return None


def next_bus_leg(
    stop_id: str,
    route_id: str,
    earliest_time: datetime,
    alight_stop_id: Optional[str] = None,
) -> Optional[BusLegPrediction]:
    """
    Find the soonest upcoming bus at `stop_id` on `route_id` that arrives
    at or after `earliest_time` (the earliest moment the rider could
    plausibly be standing at the stop). If `alight_stop_id` is given,
    also try to read a live ride time to that stop off the same vehicle's
    OnwardCalls.
    """
    if not os.environ.get("MTA_BUS_TIME_API_KEY"):
        return None

    try:
        data = _stop_monitoring(stop_id, route_id)
        if data is None:
            return None
        visits = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0][
            "MonitoredStopVisit"
        ]
    except Exception:
        return None

    candidates = []
    for visit in visits:
        try:
            call = visit["MonitoredVehicleJourney"]["MonitoredCall"]
            expected = datetime.fromisoformat(call["ExpectedArrivalTime"])
        except (KeyError, ValueError):
            continue
        if earliest_time <= expected <= earliest_time + timedelta(minutes=MAX_PLAUSIBLE_WAIT_MIN):
            candidates.append((expected, visit))

    if not candidates:
        return None

    board_time, best_visit = min(candidates, key=lambda pair: pair[0])

    ride_min = None
    if alight_stop_id:
        try:
            ride_min = _onward_ride_min(best_visit, board_time, alight_stop_id)
        except Exception:
            ride_min = None

    return {"board_time": board_time, "ride_min": ride_min}
