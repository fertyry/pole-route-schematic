"""OpenStreetMap surroundings discovered near a confirmed main route."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from pole_route.domain.route import GeoPoint, Route


@dataclass(frozen=True, slots=True)
class FeatureProvenance:
    """One upstream record contributing to a context feature."""

    source: str
    source_id: str = ""
    provider: str = ""
    dataset: str = ""
    resource: str = ""
    record_id: str = ""
    release: str = ""
    version: str = ""
    update_time: str = ""
    confidence: float | None = None
    license: str = ""


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
    """An accepted portable context feature, independent of road calculations."""

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
    source: str = ""
    source_id: str = ""
    source_release: str = ""
    source_version: str = ""
    provider: str = ""
    dataset: str = ""
    resource: str = ""
    record_id: str = ""
    update_time: str = ""
    confidence: float | None = None
    source_license: str = ""
    provenance: tuple[FeatureProvenance, ...] = ()
    conflation_status: str = ""
    matched_source_ids: tuple[str, ...] = ()
    display_geometry_kind: OSMGeometryKind | None = None
    display_parts: tuple[ContextGeometryPart, ...] = ()
    crosses_category: OSMFeatureCategory | None = None
    crosses_feature_key: str = ""
    crosses_source_id: str = ""
    crosses_name: str | None = None

    def __post_init__(self) -> None:
        is_osm = self.osm_type in {"node", "way", "relation"} and self.osm_id > 0
        if not is_osm and not (self.source.strip() and self.source_id.strip()):
            raise ValueError(
                "A context feature requires either an OSM identity or generic source identity"
            )
        if not self.parts:
            raise ValueError("A context feature requires at least one geometry part")
        if is_osm and not self.source:
            object.__setattr__(self, "source", "OpenStreetMap")
        if is_osm and not self.source_id:
            object.__setattr__(self, "source_id", f"{self.osm_type}/{self.osm_id}")
        if is_osm and not self.source_path:
            object.__setattr__(
                self, "source_path", f"OpenStreetMap:{self.osm_type}/{self.osm_id}"
            )

    @property
    def identity(self) -> tuple[str, int]:
        """Return the stable OSM identity used for de-duplication."""

        return self.osm_type, self.osm_id

    @property
    def feature_key(self) -> str:
        """Return a stable source-aware key shared by every exported CAD part."""

        return f"{self.category.value}:{self.source}:{self.source_id}"

    @property
    def render_geometry_kind(self) -> OSMGeometryKind:
        """Return derived display geometry when present, else authoritative geometry."""

        return self.display_geometry_kind or self.geometry_kind

    @property
    def render_parts(self) -> tuple[ContextGeometryPart, ...]:
        """Return derived display parts without replacing authoritative source parts."""

        return self.display_parts or self.parts


def osm_feature_name(tags: Mapping[str, object]) -> str | None:
    """Return a real OSM name, preferring Thai and never inventing a label."""

    for key in ("name:th", "name"):
        value = tags.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


@dataclass(frozen=True, slots=True)
class OSMContext:
    roads: tuple[ContextRoad, ...] = ()
    places: tuple[ContextPlace, ...] = ()
    features: tuple[ContextFeature, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: tuple[tuple[str, float], ...] = ()
