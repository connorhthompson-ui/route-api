from typing import Literal, Optional

from pydantic import BaseModel


class Leg(BaseModel):
    mode: Literal["walk", "wait", "subway", "bus"]
    line: Optional[str] = None
    description: str
    duration_min: int
    base_duration_min: Optional[int] = None
    source: Optional[Literal["realtime", "scheduled_fallback"]] = None


class RouteOption(BaseModel):
    id: str
    label: str
    total_duration_min: int
    legs: list[Leg]
    walk_distance_ft: Optional[int] = None
