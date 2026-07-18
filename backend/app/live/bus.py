"""
Live bus arrival predictions via MTA Bus Time's SIRI StopMonitoring API.
Requires MTA_BUS_TIME_API_KEY. The key is rate-limited to ~1 request per
30s, GLOBALLY -- shared across all stops and routes, not per-stop. With
several different bus legs in the route catalog, a single /best-route
request can ask about multiple distinct (stop, route) pairs within
milliseconds of each other, which would blow the limit if each made its
own request. So there are two layers:
  1. A per-(stop, route) cache (25s) for repeat lookups of the same leg.
  2. A global cooldown gate: if a live call was made anywhere in the last
     ~28s, new *different* lookups skip the network call entirely and
     fall back immediately, rather than firing a request we know will
     get rate-limited.
"""

import os
import time
from datetime import datetime
from threading import Lock
from typing import Optional, TypedDict

import requests

_CACHE_TTL_SECONDS = 25
_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_cache_lock = Lock()

_GLOBAL_COOLDOWN_SECONDS = 28
_last_request_monotonic: Optional[float] = None
_global_lock = Lock()


class BusLegPrediction(TypedDict):
    board_time: datetime


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
        params={"key": api_key, "MonitoringRef": stop_id, "LineRef": route_id},
        timeout=8,
    )
    resp.raise_for_status()
    data = resp.json()

    with _cache_lock:
        _cache[key] = (now, data)
    return data


def next_bus_leg(
    stop_id: str, route_id: str, earliest_time: datetime
) -> Optional[BusLegPrediction]:
    """
    Find the soonest upcoming bus at `stop_id` on `route_id` that arrives
    at or after `earliest_time` (the earliest moment the rider could
    plausibly be standing at the stop).
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
        if expected >= earliest_time:
            candidates.append(expected)

    if not candidates:
        return None

    return {"board_time": min(candidates)}
