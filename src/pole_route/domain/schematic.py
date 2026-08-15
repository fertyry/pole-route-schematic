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
    marker_id: str = ""
    road_angle_degrees: float = 0.0
    installed_quantity: int = 1


@dataclass(frozen=True, slots=True)
class SchematicRoad:
    centerline: tuple[tuple[float, float], ...]
    left_edge: tuple[tuple[float, float], ...]
    right_edge: tuple[tuple[float, float], ...]
    is_main_route: bool = False
    name: str = ""
    label_position: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class SchematicLayout:
    width: float
    height: float
    road_left: float
    road_right: float
    road_top: float
    road_bottom: float
    poles: tuple[SchematicPole, ...]
    roads: tuple[SchematicRoad, ...] = ()
    road_boundaries: tuple[tuple[tuple[float, float], ...], ...] = ()
