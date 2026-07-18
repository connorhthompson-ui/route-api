from typing import Literal, Optional

from fastapi import APIRouter

from app.models import Leg, RouteOption

router = APIRouter()

# A walking leg that crosses both avenues and streets can cut corners
# instead of walking the full rectangle. The closer dx (avenue-blocks) and
# dy (street-blocks) are to each other, the more "diagonal" the walk is,
# and the bigger the time saving versus the naive block-by-block estimate.
MAX_SAVINGS = 0.25


def _diagonal_discount(dx: int, dy: int) -> float:
    ratio = 0.0 if dx == 0 or dy == 0 else min(dx, dy) / max(dx, dy)
    return 1.0 - (ratio * MAX_SAVINGS)


def _walk_leg(description: str, base_duration_min: int, dx: int, dy: int) -> Leg:
    discount = _diagonal_discount(dx, dy)
    return Leg(
        mode="walk",
        description=description,
        base_duration_min=base_duration_min,
        duration_min=round(base_duration_min * discount),
    )


def _transit_leg(
    mode: Literal["subway", "bus"], line: str, description: str, duration_min: int
) -> Leg:
    return Leg(mode=mode, line=line, description=description, duration_min=duration_min)


def _route(
    id_: str, label: str, legs: list[Leg], walk_distance_ft: Optional[int] = None
) -> RouteOption:
    return RouteOption(
        id=id_,
        label=label,
        total_duration_min=sum(leg.duration_min for leg in legs),
        legs=legs,
        walk_distance_ft=walk_distance_ft,
    )


ROUTES_TO_WORK: list[RouteOption] = [
    _route(
        "6-train-77th",
        "6 train from 77th St",
        [
            _walk_leg("Walk to 77th St station", base_duration_min=6, dx=4, dy=2),
            _transit_leg("subway", "6", "6 train (local) to 51st St", 14),
            _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=7, dx=4, dy=2),
        ],
    ),
    _route(
        "m79-bus-6-train",
        "M79 SBS bus + 6 train",
        [
            _walk_leg("Walk to 1st Ave & 79th St", base_duration_min=2, dx=1, dy=0),
            _transit_leg("bus", "M79 SBS", "M79 Select Bus westbound to Lexington Ave", 6),
            _walk_leg("Walk to 6 train entrance", base_duration_min=2, dx=0, dy=1),
            _transit_leg("subway", "6", "6 train to 51st St", 14),
            _walk_leg("Walk to 1221 Ave of the Americas", base_duration_min=7, dx=4, dy=2),
        ],
    ),
    _route(
        "walk-only",
        "Walk the whole way",
        [
            _walk_leg(
                "Walk straight down to 1221 Ave of the Americas",
                base_duration_min=51,
                dx=8,
                dy=30,
            ),
        ],
        walk_distance_ft=12300,
    ),
]

ROUTES_TO_HOME: list[RouteOption] = [
    _route(
        "6-train-77th",
        "6 train to 77th St",
        [
            _walk_leg("Walk to 51st St station", base_duration_min=7, dx=4, dy=2),
            _transit_leg("subway", "6", "6 train (local) to 77th St", 14),
            _walk_leg("Walk to 435 E 79th St", base_duration_min=6, dx=4, dy=2),
        ],
    ),
    _route(
        "m79-bus-6-train",
        "6 train + M79 SBS bus",
        [
            _walk_leg("Walk to 51st St station", base_duration_min=7, dx=4, dy=2),
            _transit_leg("subway", "6", "6 train to 77th St", 14),
            _walk_leg("Walk to M79 SBS stop", base_duration_min=2, dx=0, dy=1),
            _transit_leg("bus", "M79 SBS", "M79 Select Bus eastbound to 1st Ave", 6),
            _walk_leg("Walk to 435 E 79th St", base_duration_min=2, dx=1, dy=0),
        ],
    ),
    _route(
        "walk-only",
        "Walk the whole way",
        [
            _walk_leg(
                "Walk straight up to 435 E 79th St",
                base_duration_min=51,
                dx=8,
                dy=30,
            ),
        ],
        walk_distance_ft=12300,
    ),
]

ROUTES_BY_DIRECTION = {
    "to_work": ROUTES_TO_WORK,
    "to_home": ROUTES_TO_HOME,
}


@router.get("/best-route", response_model=list[RouteOption])
def get_best_route(direction: Literal["to_work", "to_home"] = "to_work") -> list[RouteOption]:
    return ROUTES_BY_DIRECTION[direction]
