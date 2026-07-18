from datetime import datetime, timedelta
from typing import Callable, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.live.bus import next_bus_leg
from app.live.subway import next_subway_leg
from app.models import Leg, RouteOption

router = APIRouter()

NY_TZ = ZoneInfo("America/New_York")

# Time to get out the door and actually be walking -- routes are planned
# as if departure happens this many minutes from now, not immediately.
PREP_TIME_MIN = 3

# A walking leg that crosses both avenues and streets can cut corners
# instead of walking the full rectangle. The closer dx (avenue-blocks) and
# dy (street-blocks) are to each other, the more "diagonal" the walk is,
# and the bigger the time saving versus the naive block-by-block estimate.
# A leg with dx=0 and dy=0 always gets discount=1.0, i.e. the base time
# passes through unchanged -- used for real, measured walk times that
# shouldn't be run through the estimate formula at all.
MAX_SAVINGS = 0.25


class RouteUnavailable(Exception):
    """Raised by a required leg builder when that service isn't currently running."""


# A leg builder takes the current "clock" (when the rider would arrive at
# the start of this leg) and returns the resolved Leg plus the clock
# advanced to when the rider arrives at the end of this leg. It may raise
# RouteUnavailable if the leg is marked required and no live service exists.
LegBuilder = Callable[[datetime], tuple[Leg, datetime]]


def _diagonal_discount(dx: int, dy: int) -> float:
    ratio = 0.0 if dx == 0 or dy == 0 else min(dx, dy) / max(dx, dy)
    return 1.0 - (ratio * MAX_SAVINGS)


def _walk_leg(description: str, base_duration_min: int, dx: int, dy: int) -> LegBuilder:
    discount = _diagonal_discount(dx, dy)
    duration_min = round(base_duration_min * discount)

    def build(clock: datetime) -> tuple[Leg, datetime]:
        leg = Leg(
            mode="walk",
            description=description,
            base_duration_min=base_duration_min,
            duration_min=duration_min,
        )
        return leg, clock + timedelta(minutes=duration_min)

    return build


def _subway_leg(
    description: str,
    lines: list[str],
    board_stop_id: str,
    alight_stop_id: str,
    fallback_line: str,
    fallback_min: int,
    required: bool = False,
) -> LegBuilder:
    def build(clock: datetime) -> tuple[Leg, datetime]:
        try:
            prediction = next_subway_leg(lines, board_stop_id, clock, alight_stop_id)
        except Exception:
            prediction = None

        if prediction and prediction["alight_time"] is not None:
            new_clock = prediction["alight_time"]
            duration_min = max(round((new_clock - clock).total_seconds() / 60), 1)
            line = prediction["line"]
        elif required:
            raise RouteUnavailable()
        else:
            new_clock = clock + timedelta(minutes=fallback_min)
            duration_min = fallback_min
            line = fallback_line

        leg = Leg(
            mode="subway",
            line=line,
            description=description.format(line=line),
            duration_min=duration_min,
        )
        return leg, new_clock

    return build


def _bus_leg(
    description: str,
    stop_id: str,
    route_id: str,
    static_ride_min: int,
    fallback_line: str,
    fallback_min: int,
) -> LegBuilder:
    def build(clock: datetime) -> tuple[Leg, datetime]:
        try:
            prediction = next_bus_leg(stop_id, route_id, clock)
        except Exception:
            prediction = None

        if prediction:
            new_clock = prediction["board_time"] + timedelta(minutes=static_ride_min)
            duration_min = max(round((new_clock - clock).total_seconds() / 60), 1)
        else:
            new_clock = clock + timedelta(minutes=fallback_min)
            duration_min = fallback_min

        leg = Leg(mode="bus", line=fallback_line, description=description, duration_min=duration_min)
        return leg, new_clock

    return build


def _route(
    id_: str, label: str, leg_builders: list[LegBuilder], walk_distance_ft: Optional[int] = None
) -> Optional[RouteOption]:
    now = datetime.now(NY_TZ)
    clock = now + timedelta(minutes=PREP_TIME_MIN)

    legs: list[Leg] = []
    try:
        for build in leg_builders:
            leg, clock = build(clock)
            legs.append(leg)
    except RouteUnavailable:
        return None

    total_duration_min = round((clock - now).total_seconds() / 60)
    return RouteOption(
        id=id_,
        label=label,
        total_duration_min=total_duration_min,
        legs=legs,
        walk_distance_ft=walk_distance_ft,
    )


# --- Real GTFS stop_ids (from MTA's official Stations.csv), not guessed ---
# 6 @ 77 St -> 627 (627S downtown, 627N uptown)
# 6 @ 51 St -> 630 (630S downtown, 630N uptown)
# Q @ 72 St (2nd Ave) -> Q03 (Q03S downtown, Q03N uptown)
# Q @ 86 St (2nd Ave) -> Q04 (Q04S downtown, Q04N uptown)
# Lexington Av/63 St (M, Q) -> B08 (B08S downtown, B08N uptown)
# 47-50 Sts-Rockefeller Ctr (B D F M) -> D15 (D15S downtown, D15N uptown)
# 57 St-7 Av (N Q R W) -> R14 (R14S downtown, R14N uptown)
# 49 St (N R W, NOT Q) -> R15 (R15S downtown, R15N uptown)
# 1 @ 79 St -> 122 (122S downtown, 122N uptown)
# 1 @ 50 St -> 126 (126S downtown, 126N uptown)
# 81 St-Museum of Natural History (B C) -> A21 (A21S downtown, A21N uptown)
# 57 St (6th Ave, M) -> B10 (B10S downtown, B10N uptown)
#
# --- Real MTA Bus Time stop_ids (from stops-for-route, direction-verified) ---
# M79 SBS westbound (towards Lex/West Side, boarding near home):
#   board MTA_401882 (E79/1Av)
# M79 SBS eastbound (towards 1st Ave/home, boarding on the UWS):
#   board MTA_405169 (E79/Lex) -- for the 6-train route
#   board MTA_401869 (E79 Transverse/Central Park) -- for the B train transfer
#   board MTA_401024 (Amsterdam Av/W79) -- for the M7 transfer
#   board MTA_403523 (W79/Broadway) -- for the 1 train transfer
# M31 southbound, towards 6th Ave ("CLINTON 11 AV via 57 ST"):
#   board MTA_402348 (York Av/E79)
# M31 northbound, towards home ("YORKVILLE 91 ST via YORK AV"):
#   board MTA_403621 (W57/6Av)
# M7 southbound, towards Midtown ("14 ST via COLUMBUS via 7 AV"):
#   board MTA_401096 (Columbus Av/W78), alights near MTA_403797 (7Av/W50)
# M7 northbound, towards UWS ("HARLEM 147 ST via 6 AV via AMSTERDAM"):
#   board MTA_400938 (6Av/W47)
M79_ROUTE_ID = "MTA NYCT_M79+"
M31_ROUTE_ID = "MTA NYCT_M31"
M7_ROUTE_ID = "MTA NYCT_M7"


def build_routes_to_work() -> list[RouteOption]:
    candidates: list[Optional[RouteOption]] = [
        _route(
            "6-train-77th",
            "6 train from 77th St",
            [
                _walk_leg("Walk to 77th St station", base_duration_min=15, dx=4, dy=2),
                _subway_leg(
                    "{line} train (local) to 51st St",
                    lines=["6"],
                    board_stop_id="627S",
                    alight_stop_id="630S",
                    fallback_line="6",
                    fallback_min=14,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=14, dx=4, dy=2),
            ],
        ),
        _route(
            "m79-bus-6-train",
            "M79 SBS bus + 6 train",
            [
                _walk_leg("Walk to 1st Ave & 79th St", base_duration_min=0, dx=1, dy=0),
                _bus_leg(
                    "M79 Select Bus westbound to Lexington Ave",
                    stop_id="MTA_401882",
                    route_id=M79_ROUTE_ID,
                    static_ride_min=6,
                    fallback_line="M79+",
                    fallback_min=6,
                ),
                _walk_leg("Walk to 6 train entrance", base_duration_min=3, dx=0, dy=1),
                _subway_leg(
                    "{line} train to 51st St",
                    lines=["6"],
                    board_stop_id="627S",
                    alight_stop_id="630S",
                    fallback_line="6",
                    fallback_min=14,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=14, dx=4, dy=2),
            ],
        ),
        _route(
            "q-train-72nd",
            "Q train from 72nd St",
            [
                _walk_leg("Walk to 72nd St station", base_duration_min=14, dx=2, dy=7),
                _subway_leg(
                    "{line} train to 57th St-7th Ave",
                    lines=["Q", "N"],
                    board_stop_id="Q03S",
                    alight_stop_id="R14S",
                    fallback_line="Q",
                    fallback_min=5,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=11, dx=1, dy=8),
            ],
        ),
        _route(
            "q-train-86th",
            "Q train from 86th St",
            [
                _walk_leg("Walk to 86th St station", base_duration_min=14, dx=2, dy=7),
                _subway_leg(
                    "{line} train to 57th St-7th Ave",
                    lines=["Q", "N"],
                    board_stop_id="Q04S",
                    alight_stop_id="R14S",
                    fallback_line="Q",
                    fallback_min=7,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=11, dx=1, dy=8),
            ],
        ),
        _route(
            "q-63-m-rockefeller",
            "Q train + M train (via Lex-63)",
            [
                _walk_leg("Walk to 72nd St station", base_duration_min=14, dx=2, dy=7),
                _subway_leg(
                    "{line} train to Lexington Av-63 St",
                    lines=["Q", "N"],
                    board_stop_id="Q03S",
                    alight_stop_id="B08S",
                    fallback_line="Q",
                    fallback_min=2,
                ),
                _subway_leg(
                    "{line} train to 47-50 Sts-Rockefeller Ctr",
                    lines=["M"],
                    board_stop_id="B08S",
                    alight_stop_id="D15S",
                    fallback_line="M",
                    fallback_min=4,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=2, dx=0, dy=1),
            ],
        ),
        _route(
            "q-57-nr-49",
            "Q train + N/R train (via 57 St)",
            [
                _walk_leg("Walk to 72nd St station", base_duration_min=14, dx=2, dy=7),
                _subway_leg(
                    "{line} train to 57th St-7th Ave",
                    lines=["Q", "N"],
                    board_stop_id="Q03S",
                    alight_stop_id="R14S",
                    fallback_line="Q",
                    fallback_min=5,
                ),
                _subway_leg(
                    "{line} train to 49th St",
                    lines=["N", "R"],
                    board_stop_id="R14S",
                    alight_stop_id="R15S",
                    fallback_line="R",
                    fallback_min=2,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=4, dx=1, dy=0),
            ],
        ),
        _route(
            "n-direct-72-49",
            "N train from 72nd St (rush hour only)",
            [
                _walk_leg("Walk to 72nd St station", base_duration_min=14, dx=2, dy=7),
                _subway_leg(
                    "{line} train (local) to 49th St",
                    lines=["N"],
                    board_stop_id="Q03S",
                    alight_stop_id="R15S",
                    fallback_line="N",
                    fallback_min=0,
                    required=True,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=4, dx=1, dy=0),
            ],
        ),
        _route(
            "n-direct-86-49",
            "N train from 86th St (rush hour only)",
            [
                _walk_leg("Walk to 86th St station", base_duration_min=14, dx=2, dy=7),
                _subway_leg(
                    "{line} train (local) to 49th St",
                    lines=["N"],
                    board_stop_id="Q04S",
                    alight_stop_id="R15S",
                    fallback_line="N",
                    fallback_min=0,
                    required=True,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=4, dx=1, dy=0),
            ],
        ),
        _route(
            "m79-1-train",
            "M79 SBS bus + 1 train",
            [
                _walk_leg("Walk to 1st Ave & 79th St", base_duration_min=0, dx=1, dy=0),
                _bus_leg(
                    "M79 Select Bus westbound to Broadway",
                    stop_id="MTA_401882",
                    route_id=M79_ROUTE_ID,
                    static_ride_min=14,
                    fallback_line="M79+",
                    fallback_min=14,
                ),
                _walk_leg("Walk to 1 train entrance", base_duration_min=2, dx=0, dy=1),
                _subway_leg(
                    "{line} train to 50th St",
                    lines=["1"],
                    board_stop_id="122S",
                    alight_stop_id="126S",
                    fallback_line="1",
                    fallback_min=9,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=7, dx=2, dy=0),
            ],
        ),
        _route(
            "m79-m7",
            "M79 SBS bus + M7 bus",
            [
                _walk_leg("Walk to 1st Ave & 79th St", base_duration_min=0, dx=1, dy=0),
                _bus_leg(
                    "M79 Select Bus westbound to Amsterdam Ave",
                    stop_id="MTA_401882",
                    route_id=M79_ROUTE_ID,
                    static_ride_min=12,
                    fallback_line="M79+",
                    fallback_min=12,
                ),
                _walk_leg("Walk to Columbus Ave & 78th St", base_duration_min=2, dx=1, dy=1),
                _bus_leg(
                    "M7 bus to 7th Ave & 50th St",
                    stop_id="MTA_401096",
                    route_id=M7_ROUTE_ID,
                    static_ride_min=18,
                    fallback_line="M7",
                    fallback_min=18,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=3, dx=1, dy=0),
            ],
        ),
        _route(
            "m79-b-train",
            "M79 SBS bus + B train",
            [
                _walk_leg("Walk to 1st Ave & 79th St", base_duration_min=0, dx=1, dy=0),
                _bus_leg(
                    "M79 Select Bus westbound to Central Park West",
                    stop_id="MTA_401882",
                    route_id=M79_ROUTE_ID,
                    static_ride_min=10,
                    fallback_line="M79+",
                    fallback_min=10,
                ),
                _walk_leg(
                    "Walk to 81 St-Museum of Natural History station",
                    base_duration_min=3,
                    dx=1,
                    dy=0,
                ),
                _subway_leg(
                    "{line} train to 47-50 Sts-Rockefeller Ctr",
                    lines=["B", "C"],
                    board_stop_id="A21S",
                    alight_stop_id="D15S",
                    fallback_line="B",
                    fallback_min=7,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=2, dx=0, dy=1),
            ],
        ),
        _route(
            "m31-m-train",
            "M31 bus + M train",
            [
                _walk_leg("Walk to York Ave & 79th St", base_duration_min=2, dx=0, dy=0),
                _bus_leg(
                    "M31 bus to 57th St & 6th Ave",
                    stop_id="MTA_402348",
                    route_id=M31_ROUTE_ID,
                    static_ride_min=20,
                    fallback_line="M31",
                    fallback_min=20,
                ),
                _walk_leg("Walk to 57 St station", base_duration_min=2, dx=0, dy=0),
                _subway_leg(
                    "{line} train to 47-50 Sts-Rockefeller Ctr",
                    lines=["M"],
                    board_stop_id="B10S",
                    alight_stop_id="D15S",
                    fallback_line="M",
                    fallback_min=3,
                ),
                _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=2, dx=0, dy=1),
            ],
        ),
        _route(
            "walk-only",
            "Walk the whole way",
            [
                _walk_leg(
                    "Walk straight down to 1221 Ave of the Americas",
                    base_duration_min=58,
                    dx=8,
                    dy=30,
                ),
            ],
            walk_distance_ft=12300,
        ),
    ]
    return [route for route in candidates if route is not None]


def build_routes_to_home() -> list[RouteOption]:
    candidates: list[Optional[RouteOption]] = [
        _route(
            "6-train-77th",
            "6 train to 77th St",
            [
                _walk_leg("Walk to 51st St station", base_duration_min=14, dx=4, dy=2),
                _subway_leg(
                    "{line} train (local) to 77th St",
                    lines=["6"],
                    board_stop_id="630N",
                    alight_stop_id="627N",
                    fallback_line="6",
                    fallback_min=14,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=15, dx=4, dy=2),
            ],
        ),
        _route(
            "m79-bus-6-train",
            "6 train + M79 SBS bus",
            [
                _walk_leg("Walk to 51st St station", base_duration_min=14, dx=4, dy=2),
                _subway_leg(
                    "{line} train to 77th St",
                    lines=["6"],
                    board_stop_id="630N",
                    alight_stop_id="627N",
                    fallback_line="6",
                    fallback_min=14,
                ),
                _walk_leg("Walk to M79 SBS stop", base_duration_min=3, dx=0, dy=1),
                _bus_leg(
                    "M79 Select Bus eastbound to 1st Ave",
                    stop_id="MTA_405169",
                    route_id=M79_ROUTE_ID,
                    static_ride_min=6,
                    fallback_line="M79+",
                    fallback_min=6,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=2, dx=1, dy=0),
            ],
        ),
        _route(
            "q-train-72nd",
            "Q train to 72nd St",
            [
                _walk_leg("Walk to 57th St-7th Ave station", base_duration_min=11, dx=1, dy=8),
                _subway_leg(
                    "{line} train to 72nd St",
                    lines=["Q", "N"],
                    board_stop_id="R14N",
                    alight_stop_id="Q03N",
                    fallback_line="Q",
                    fallback_min=5,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=14, dx=2, dy=7),
            ],
        ),
        _route(
            "q-train-86th",
            "Q train to 86th St",
            [
                _walk_leg("Walk to 57th St-7th Ave station", base_duration_min=11, dx=1, dy=8),
                _subway_leg(
                    "{line} train to 86th St",
                    lines=["Q", "N"],
                    board_stop_id="R14N",
                    alight_stop_id="Q04N",
                    fallback_line="Q",
                    fallback_min=7,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=14, dx=2, dy=7),
            ],
        ),
        _route(
            "q-63-m-rockefeller",
            "M train + Q train (via Lex-63)",
            [
                _walk_leg("Walk to 47-50 Sts station", base_duration_min=2, dx=0, dy=1),
                _subway_leg(
                    "{line} train to Lexington Av-63 St",
                    lines=["M"],
                    board_stop_id="D15N",
                    alight_stop_id="B08N",
                    fallback_line="M",
                    fallback_min=4,
                ),
                _subway_leg(
                    "{line} train to 72nd St",
                    lines=["Q", "N"],
                    board_stop_id="B08N",
                    alight_stop_id="Q03N",
                    fallback_line="Q",
                    fallback_min=2,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=14, dx=2, dy=7),
            ],
        ),
        _route(
            "q-57-nr-49",
            "N/R train + Q train (via 57 St)",
            [
                _walk_leg("Walk to 49th St station", base_duration_min=2, dx=1, dy=0),
                _subway_leg(
                    "{line} train to 57th St-7th Ave",
                    lines=["N", "R"],
                    board_stop_id="R15N",
                    alight_stop_id="R14N",
                    fallback_line="R",
                    fallback_min=2,
                ),
                _subway_leg(
                    "{line} train to 72nd St",
                    lines=["Q", "N"],
                    board_stop_id="R14N",
                    alight_stop_id="Q03N",
                    fallback_line="Q",
                    fallback_min=5,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=14, dx=2, dy=7),
            ],
        ),
        _route(
            "n-direct-72-49",
            "N train to 72nd St (rush hour only)",
            [
                _walk_leg("Walk to 49th St station", base_duration_min=2, dx=1, dy=0),
                _subway_leg(
                    "{line} train (local) to 72nd St",
                    lines=["N"],
                    board_stop_id="R15N",
                    alight_stop_id="Q03N",
                    fallback_line="N",
                    fallback_min=0,
                    required=True,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=14, dx=2, dy=7),
            ],
        ),
        _route(
            "n-direct-86-49",
            "N train to 86th St (rush hour only)",
            [
                _walk_leg("Walk to 49th St station", base_duration_min=2, dx=1, dy=0),
                _subway_leg(
                    "{line} train (local) to 86th St",
                    lines=["N"],
                    board_stop_id="R15N",
                    alight_stop_id="Q04N",
                    fallback_line="N",
                    fallback_min=0,
                    required=True,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=14, dx=2, dy=7),
            ],
        ),
        _route(
            "m79-1-train",
            "1 train + M79 SBS bus",
            [
                _walk_leg("Walk to 50th St station", base_duration_min=7, dx=2, dy=0),
                _subway_leg(
                    "{line} train to 79th St",
                    lines=["1"],
                    board_stop_id="126N",
                    alight_stop_id="122N",
                    fallback_line="1",
                    fallback_min=9,
                ),
                _walk_leg("Walk to M79 SBS stop", base_duration_min=2, dx=0, dy=1),
                _bus_leg(
                    "M79 Select Bus eastbound to 1st Ave",
                    stop_id="MTA_403523",
                    route_id=M79_ROUTE_ID,
                    static_ride_min=14,
                    fallback_line="M79+",
                    fallback_min=14,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=2, dx=1, dy=0),
            ],
        ),
        _route(
            "m79-m7",
            "M7 bus + M79 SBS bus",
            [
                _walk_leg("Walk to 6th Ave & 47th St", base_duration_min=2, dx=0, dy=1),
                _bus_leg(
                    "M7 bus to Amsterdam Ave & 79th St",
                    stop_id="MTA_400938",
                    route_id=M7_ROUTE_ID,
                    static_ride_min=18,
                    fallback_line="M7",
                    fallback_min=18,
                ),
                _walk_leg("Walk to M79 SBS stop", base_duration_min=2, dx=1, dy=1),
                _bus_leg(
                    "M79 Select Bus eastbound to 1st Ave",
                    stop_id="MTA_401024",
                    route_id=M79_ROUTE_ID,
                    static_ride_min=12,
                    fallback_line="M79+",
                    fallback_min=12,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=2, dx=1, dy=0),
            ],
        ),
        _route(
            "m79-b-train",
            "B train + M79 SBS bus",
            [
                _walk_leg("Walk to 47-50 Sts station", base_duration_min=2, dx=0, dy=1),
                _subway_leg(
                    "{line} train to 81 St-Museum of Natural History",
                    lines=["B", "C"],
                    board_stop_id="D15N",
                    alight_stop_id="A21N",
                    fallback_line="B",
                    fallback_min=7,
                ),
                _walk_leg(
                    "Walk to M79 SBS stop",
                    base_duration_min=3,
                    dx=1,
                    dy=0,
                ),
                _bus_leg(
                    "M79 Select Bus eastbound to 1st Ave",
                    stop_id="MTA_401869",
                    route_id=M79_ROUTE_ID,
                    static_ride_min=10,
                    fallback_line="M79+",
                    fallback_min=10,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=2, dx=1, dy=0),
            ],
        ),
        _route(
            "m31-m-train",
            "M train + M31 bus",
            [
                _walk_leg("Walk to 57 St station", base_duration_min=2, dx=0, dy=1),
                _subway_leg(
                    "{line} train to 57th St & 6th Ave",
                    lines=["M"],
                    board_stop_id="D15N",
                    alight_stop_id="B10N",
                    fallback_line="M",
                    fallback_min=3,
                ),
                _walk_leg("Walk to M31 bus stop", base_duration_min=2, dx=0, dy=0),
                _bus_leg(
                    "M31 bus to York Ave & 79th St",
                    stop_id="MTA_403621",
                    route_id=M31_ROUTE_ID,
                    static_ride_min=20,
                    fallback_line="M31",
                    fallback_min=20,
                ),
                _walk_leg("Walk to 435 E 79th St", base_duration_min=2, dx=0, dy=0),
            ],
        ),
        _route(
            "walk-only",
            "Walk the whole way",
            [
                _walk_leg(
                    "Walk straight up to 435 E 79th St",
                    base_duration_min=58,
                    dx=8,
                    dy=30,
                ),
            ],
            walk_distance_ft=12300,
        ),
    ]
    return [route for route in candidates if route is not None]


@router.get("/best-route", response_model=list[RouteOption])
def get_best_route(direction: Literal["to_work", "to_home"] = "to_work") -> list[RouteOption]:
    if direction == "to_home":
        return build_routes_to_home()
    return build_routes_to_work()
