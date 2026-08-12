"""Road-centerline route data."""

from dataclasses import dataclass


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

