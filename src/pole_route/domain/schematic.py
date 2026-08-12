"""Non-scale schematic layout data."""

from dataclasses import dataclass

from pole_route.domain.pole import PoleSide


@dataclass(frozen=True, slots=True)
class SchematicPole:
    number: str
    detail: str
    side: PoleSide
    x: float
    y: float
    source_station_metres: float


@dataclass(frozen=True, slots=True)
class SchematicLayout:
    width: float
    height: float
    road_left: float
    road_right: float
    road_top: float
    road_bottom: float
    poles: tuple[SchematicPole, ...]

