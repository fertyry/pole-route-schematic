"""Road-centerline route data."""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A geographic coordinate read from a route source."""

    longitude: float
    latitude: float
    altitude: float | None = None

    def __post_init__(self) -> None:
        if not -180 <= self.longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        if not -90 <= self.latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90")


@dataclass(frozen=True, slots=True)
class Route:
    """A confirmed KML/KMZ road centerline."""

    name: str
    source_path: str
    points: tuple[GeoPoint, ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("A route LineString requires at least two points")


class RouteType(StrEnum):
    MAIN_ROUTE = "Main route"
    ROAD = "Road / Soi"
    BRIDGE = "Vehicle bridge"
    FOOTBRIDGE = "Footbridge"
    CANAL = "Canal"
    RAILWAY = "Railway"
    REFERENCE = "Reference"
    IGNORE = "Ignore"


@dataclass(frozen=True, slots=True)
class ClassifiedRoute:
    route: Route
    type: RouteType
    width_metres: float | None
    pole_offset_metres: float | None = 2.0

    def __post_init__(self) -> None:
        if self.type in {RouteType.MAIN_ROUTE, RouteType.ROAD, RouteType.BRIDGE} and (
            self.width_metres is None or self.width_metres <= 0
        ):
            raise ValueError(f"{self.type.value} requires a width greater than zero")
        if self.type in {RouteType.MAIN_ROUTE, RouteType.ROAD, RouteType.BRIDGE} and (
            self.pole_offset_metres is None or self.pole_offset_metres < 0
        ):
            raise ValueError(f"{self.type.value} requires a pole offset of zero or greater")
