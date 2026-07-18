"""
Live subway arrival predictions via MTA's GTFS-realtime feeds (no API
key required). Wraps nyct-gtfs, which handles the NYCT-specific
protobuf extension the raw feed uses.

nyct-gtfs returns naive datetimes representing Eastern time. We attach
America/New_York explicitly rather than trusting the server's system
clock/timezone (Render's containers run UTC, not Eastern).
"""

import time
from datetime import datetime
from threading import Lock
from typing import Optional, TypedDict
from zoneinfo import ZoneInfo

from datetime import timedelta

from nyct_gtfs import NYCTFeed

NY_TZ = ZoneInfo("America/New_York")

# GTFS-realtime occasionally serves a stale or corrupt TripUpdate for a
# brief window (a known real-world quirk of live transit feeds) that can
# claim a train is hours away. No real NYC subway service has a gap that
# large, so anything beyond this is treated as unreliable data rather
# than a genuine prediction, and the caller falls back to the static
# estimate instead.
MAX_PLAUSIBLE_WAIT_MIN = 60

_FEED_CACHE_TTL_SECONDS = 15
_feed_cache: dict[str, tuple[float, NYCTFeed]] = {}
_feed_cache_lock = Lock()


class SubwayLegPrediction(TypedDict):
    line: str
    board_time: datetime
    alight_time: Optional[datetime]


def _get_feed(line: str) -> NYCTFeed:
    now = time.monotonic()
    with _feed_cache_lock:
        cached = _feed_cache.get(line)
        if cached and now - cached[0] < _FEED_CACHE_TTL_SECONDS:
            return cached[1]

    feed = NYCTFeed(line)
    with _feed_cache_lock:
        _feed_cache[line] = (now, feed)
    return feed


def _as_ny(dt: datetime) -> datetime:
    """nyct-gtfs arrival times are naive Eastern time -- attach the zone."""
    return dt if dt.tzinfo else dt.replace(tzinfo=NY_TZ)


def next_subway_leg(
    lines: list[str],
    board_stop_id: str,
    earliest_time: datetime,
    alight_stop_id: Optional[str] = None,
) -> Optional[SubwayLegPrediction]:
    """
    Find the soonest upcoming trip (across `lines`) that stops at
    `board_stop_id` at or after `earliest_time` (the earliest moment the
    rider could plausibly be standing on the platform). If
    `alight_stop_id` is given, only consider trips that also stop there
    afterwards, so the ride time can be read off that same trip's live
    predictions.
    """
    best: Optional[SubwayLegPrediction] = None

    for line in lines:
        try:
            feed = _get_feed(line)
        except Exception:
            continue

        trips = feed.filter_trips(headed_for_stop_id=[board_stop_id], underway=True)
        for trip in trips:
            stop_ids = [stu.stop_id for stu in trip.stop_time_updates]
            if board_stop_id not in stop_ids:
                continue
            board_idx = stop_ids.index(board_stop_id)
            board_time = _as_ny(trip.stop_time_updates[board_idx].arrival)
            if board_time < earliest_time:
                continue  # departs before the rider could get there
            if board_time > earliest_time + timedelta(minutes=MAX_PLAUSIBLE_WAIT_MIN):
                continue  # implausibly far out -- likely stale/corrupt feed data

            alight_time = None
            if alight_stop_id:
                if alight_stop_id not in stop_ids[board_idx + 1 :]:
                    continue
                alight_idx = stop_ids.index(alight_stop_id, board_idx + 1)
                alight_time = _as_ny(trip.stop_time_updates[alight_idx].arrival)

            if best is None or board_time < best["board_time"]:
                best = {"line": trip.route_id, "board_time": board_time, "alight_time": alight_time}

    return best
