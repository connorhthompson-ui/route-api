from fastapi import APIRouter

from app.models import Leg, RouteOption

router = APIRouter()

FAKE_ROUTES: list[RouteOption] = [
    RouteOption(
        id="6-train-77th",
        label="6 train from 77th St",
        total_duration_min=25,
        legs=[
            Leg(
                mode="walk",
                description="Walk to 77th St station",
                duration_min=5,
            ),
            Leg(
                mode="subway",
                line="6",
                description="6 train (local) to 51st St",
                duration_min=14,
            ),
            Leg(
                mode="walk",
                description="Walk to 1221 Ave of the Americas",
                duration_min=6,
            ),
        ],
    ),
    RouteOption(
        id="m79-bus-6-train",
        label="M79 SBS bus + 6 train",
        total_duration_min=30,
        legs=[
            Leg(
                mode="walk",
                description="Walk to 1st Ave & 79th St",
                duration_min=2,
            ),
            Leg(
                mode="bus",
                line="M79 SBS",
                description="M79 Select Bus westbound to Lexington Ave",
                duration_min=6,
            ),
            Leg(
                mode="walk",
                description="Walk to 6 train entrance",
                duration_min=2,
            ),
            Leg(
                mode="subway",
                line="6",
                description="6 train to 51st St",
                duration_min=14,
            ),
            Leg(
                mode="walk",
                description="Walk to 1221 Ave of the Americas",
                duration_min=6,
            ),
        ],
    ),
    RouteOption(
        id="walk-only",
        label="Walk the whole way",
        total_duration_min=48,
        walk_distance_ft=12300,
        legs=[
            Leg(
                mode="walk",
                description="Walk straight down to 1221 Ave of the Americas",
                duration_min=48,
            ),
        ],
    ),
]


@router.get("/best-route", response_model=list[RouteOption])
def get_best_route() -> list[RouteOption]:
    return FAKE_ROUTES
