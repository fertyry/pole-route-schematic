"""OpenStreetMap surroundings discovered near a confirmed main route."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

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


class OSMFeatureCategory(StrEnum):
    """Semantic categories supported by the OSM Surround V2 foundation."""

    ROAD_BRIDGE = "road_bridge"
    FOOTBRIDGE = "footbridge"
    RIVER = "river"
    CANAL = "canal"
    BUILDING = "building"
    FUEL = "fuel"
    SHOP = "shop"
    POI = "poi"


class OSMGeometryKind(StrEnum):
    """Portable geometry kinds stored without Qt or Shapely objects."""

    POINT = "point"
    LINESTRING = "linestring"
    POLYGON = "polygon"
    MULTILINESTRING = "multilinestring"
    MULTIPOLYGON = "multipolygon"


@dataclass(frozen=True, slots=True)
class ContextGeometryPart:
    """One point/line part or one polygon exterior with optional interior rings."""

    coordinates: tuple[GeoPoint, ...]
    holes: tuple[tuple[GeoPoint, ...], ...] = ()

    def __post_init__(self) -> None:
        if not self.coordinates:
            raise ValueError("An OSM geometry part requires at least one coordinate")


@dataclass(frozen=True, slots=True)
class ContextFeature:
    """An accepted portable OSM feature, independent of road calculations."""

    osm_type: str
    osm_id: int
    category: OSMFeatureCategory
    geometry_kind: OSMGeometryKind
    parts: tuple[ContextGeometryPart, ...]
    name: str | None = None
    tags: tuple[tuple[str, str], ...] = ()
    recommended: bool = True
    recommendation: str = ""
    source_path: str = ""

    def __post_init__(self) -> None:
        if self.osm_type not in {"node", "way", "relation"}:
            raise ValueError("OSM feature type must be node, way, or relation")
        if self.osm_id <= 0:
            raise ValueError("OSM feature ID must be greater than zero")
        if not self.parts:
            raise ValueError("An OSM feature requires at least one geometry part")
        if not self.source_path:
            object.__setattr__(
                self, "source_path", f"OpenStreetMap:{self.osm_type}/{self.osm_id}"
            )

    @property
    def identity(self) -> tuple[str, int]:
        """Return the stable OSM identity used for de-duplication."""

        return self.osm_type, self.osm_id


def osm_feature_name(tags: Mapping[str, object]) -> str | None:
    """Return a real OSM name, preferring Thai and never inventing a label."""

    for key in ("name:th", "name"):
        value = tags.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


@dataclass(frozen=True, slots=True)
class OSMContext:
    roads: tuple[ContextRoad, ...]
    places: tuple[ContextPlace, ...]
    features: tuple[ContextFeature, ...] = ()
