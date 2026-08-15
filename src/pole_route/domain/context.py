"""OpenStreetMap surroundings discovered near a confirmed main route."""

from dataclasses import dataclass

from pole_route.domain.route import GeoPoint, Route


@dataclass(frozen=True, slots=True)
class ContextRoad:
    """A nearby OSM road candidate with a suggested schematic width."""

    route: Route
    highway: str
    suggested_width_metres: float
    recommended: bool = True
    recommendation: str = "Connects to the Main route"


@dataclass(frozen=True, slots=True)
class ContextPlace:
    """A named landmark returned by OpenStreetMap."""

    name: str
    category: str
    point: GeoPoint


@dataclass(frozen=True, slots=True)
class OSMContext:
    roads: tuple[ContextRoad, ...]
    places: tuple[ContextPlace, ...]
