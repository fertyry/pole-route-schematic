"""Fetch and classify OpenStreetMap context around a confirmed route."""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from dataclasses import replace
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import nearest_points, substring

from pole_route.domain.context import (
    ContextFeature,
    ContextGeometryPart,
    ContextPlace,
    ContextRoad,
    OSMContext,
    OSMFeatureCategory,
    OSMGeometryKind,
    osm_feature_name,
)
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.projection import MetricProjection
from pole_route.importers.osm_geometry import geometry_parts_from_element

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
DEFAULT_CORRIDOR_METRES = 15.0
BUILDING_POI_CORRIDOR_METRES = 100.0
FEATURE_CORRIDOR_METRES = BUILDING_POI_CORRIDOR_METRES
WATER_CONTEXT_MARGIN_METRES = 175.0
CONTEXT_ROAD_EXTENSION_METRES = 35.0
MINIMUM_CONTEXT_ROAD_METRES = 8.0
EXCLUDED_HIGHWAYS = {
    "footway",
    "path",
    "cycleway",
    "steps",
    "bridleway",
    "corridor",
    "construction",
    "proposed",
    "track",
    "pedestrian",
}
RECOMMENDED_HIGHWAYS = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "residential",
    "unclassified",
    "living_street",
}


class OSMContextError(RuntimeError):
    """OpenStreetMap surroundings cannot be downloaded or interpreted."""


class OSMFeatureParseWarning(RuntimeWarning):
    """One malformed OSM feature candidate was skipped."""


def fetch_osm_context(
    main_route: Route,
    corridor_metres: float = DEFAULT_CORRIDOR_METRES,
    *,
    feature_corridor_metres: float = FEATURE_CORRIDOR_METRES,
    fetcher: Callable[[str], bytes] | None = None,
) -> OSMContext:
    """Return roads and named landmarks within a corridor of ``main_route``."""
    if corridor_metres <= 0:
        raise ValueError("Context corridor must be greater than zero")
    if feature_corridor_metres <= 0:
        raise ValueError("Feature corridor must be greater than zero")
    query = _build_query(main_route, corridor_metres, feature_corridor_metres)
    try:
        payload = (fetcher or _download_overpass)(query)
        document = json.loads(payload)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise OSMContextError(f"Could not contact OpenStreetMap: {error}") from error
    except (json.JSONDecodeError, TypeError) as error:
        raise OSMContextError("OpenStreetMap returned an invalid response") from error
    return parse_osm_context(
        document,
        main_route,
        corridor_metres,
        feature_corridor_metres=feature_corridor_metres,
    )


def parse_osm_context(
    document: dict,
    main_route: Route,
    corridor_metres: float = DEFAULT_CORRIDOR_METRES,
    *,
    feature_corridor_metres: float = FEATURE_CORRIDOR_METRES,
) -> OSMContext:
    """Parse an Overpass JSON document and apply the metric route corridor."""
    elements = document.get("elements")
    if not isinstance(elements, list):
        raise OSMContextError("OpenStreetMap response has no element list")

    nodes = {
        element["id"]: GeoPoint(float(element["lon"]), float(element["lat"]))
        for element in elements
        if element.get("type") == "node" and "lon" in element and "lat" in element
    }
    projection = MetricProjection.for_points(main_route.points)
    main_metric = LineString([projection.to_metric(point) for point in main_route.points])
    roads: list[ContextRoad] = []
    places: list[ContextPlace] = []
    features: list[ContextFeature] = []
    feature_keys: set[tuple[str, int, OSMFeatureCategory]] = set()

    for element in elements:
        tags = element.get("tags") or {}
        # Feature parsing is intentionally independent from the legacy road
        # candidate pipeline below.  That pipeline has several early exits
        # (including excluded pedestrian highway classes) which must not
        # suppress an otherwise valid bridge or water feature.
        categories = _feature_categories(tags)
        if categories and element.get("type") in {"node", "way", "relation"}:
            try:
                osm_type = str(element["type"])
                osm_id = int(element["id"])
            except (KeyError, TypeError, ValueError) as error:
                for category in categories:
                    warnings.warn(
                        f"Could not parse {category.value} {element.get('type')}/"
                        f"{element.get('id')}: invalid OSM identity ({error})",
                        OSMFeatureParseWarning,
                        stacklevel=2,
                    )
            else:
                new_categories = tuple(
                    category for category in categories
                    if (osm_type, osm_id, category) not in feature_keys
                )
                parsed_features = _features_from_element(
                    element,
                    nodes,
                    new_categories,
                    projection,
                    main_metric,
                    feature_corridor_metres,
                )
                for feature in parsed_features:
                    key = (feature.osm_type, feature.osm_id, feature.category)
                    feature_keys.add(key)
                    features.append(feature)
        if element.get("type") == "way" and tags.get("highway"):
            if tags.get("highway") in EXCLUDED_HIGHWAYS:
                continue
            points = _way_points(element, nodes)
            if len(points) < 2:
                continue
            candidate = LineString([projection.to_metric(point) for point in points])
            distance_to_main = candidate.distance(main_metric)
            # OSM side-road centerlines often terminate at a divided road's near
            # carriageway instead of the user-drawn Main centerline.  Apply the
            # requested corridor here; limiting this to a tiny snap tolerance
            # silently discarded valid sois beside wide roads.
            if (
                distance_to_main > corridor_metres
                or candidate.length < MINIMUM_CONTEXT_ROAD_METRES
            ):
                continue
            highway = str(tags["highway"])
            source_name = tags.get("name") or tags.get("name:th")
            if highway == "service" and (
                not source_name
                or tags.get("service") in {"driveway", "parking_aisle", "drive-through"}
            ):
                continue
            main_buffer_overlap = candidate.intersection(main_metric.buffer(8.0)).length
            if main_buffer_overlap / candidate.length > 0.70:
                continue
            name = source_name or f"Unnamed connecting road {element['id']}"
            point_on_candidate, _point_on_main = nearest_points(candidate, main_metric)
            station = candidate.project(point_on_candidate)
            clipped = substring(
                candidate,
                max(0.0, station - CONTEXT_ROAD_EXTENSION_METRES),
                min(candidate.length, station + CONTEXT_ROAD_EXTENSION_METRES),
            )
            if not isinstance(clipped, LineString) or clipped.length < 5.0:
                continue
            clipped_points = tuple(
                projection.to_geographic(float(x), float(y)) for x, y in clipped.coords
            )
            roads.append(
                ContextRoad(
                    Route(
                        str(name),
                        f"OpenStreetMap:way/{element['id']}",
                        clipped_points,
                    ),
                    highway,
                    _suggested_width(highway, tags),
                    bool(source_name) and highway in RECOMMENDED_HIGHWAYS,
                    (
                        "Named road connected to the Main route"
                        if source_name and highway in RECOMMENDED_HIGHWAYS
                        else "Review manually: unnamed or low-priority access road"
                    ),
                )
            )
        place = _place_from_element(element, nodes)
        if place is not None:
            point_metric = projection.to_metric(place.point)
            if main_metric.distance(LineString([point_metric, point_metric])) <= corridor_metres:
                places.append(place)

    roads = _deduplicate_junction_roads(roads, projection, main_metric)
    roads.sort(key=lambda item: (not item.recommended, item.route.name.casefold()))
    places.sort(key=lambda item: item.name.casefold())
    features = list(prepare_context_features(
        features, main_route, feature_corridor_metres=feature_corridor_metres
    ))
    features.sort(key=lambda item: (item.category.value, item.name or "", item.osm_id))
    return OSMContext(tuple(roads), tuple(places), tuple(features))


def prepare_context_features(
    features: list[ContextFeature] | tuple[ContextFeature, ...],
    main_route: Route,
    *,
    feature_corridor_metres: float = FEATURE_CORRIDOR_METRES,
) -> tuple[ContextFeature, ...]:
    """Derive presentation geometry and conservative relations from source features.

    This is also used when opening projects saved before display geometry was
    persisted.  It never replaces the authoritative ``parts`` coordinates.
    """

    projection = MetricProjection.for_points(main_route.points)
    main_metric = LineString(projection.to_metric(point) for point in main_route.points)
    return tuple(_prepare_water_and_bridge_context(
        list(features), projection, main_metric, feature_corridor_metres
    ))


def _deduplicate_junction_roads(
    roads: list[ContextRoad], projection: MetricProjection, main_metric: LineString
) -> list[ContextRoad]:
    """Keep one OSM candidate when split ways describe the same nearby junction."""
    accepted: list[ContextRoad] = []
    keys: set[tuple[str, str, int]] = set()
    for road in roads:
        metric = LineString(projection.to_metric(point) for point in road.route.points)
        _road_point, main_point = nearest_points(metric, main_metric)
        station_bucket = round(main_metric.project(main_point) / 8.0)
        normalized_name = road.route.name.casefold()
        if normalized_name.startswith("unnamed connecting road"):
            normalized_name = "unnamed"
        key = (normalized_name, road.highway, station_bucket)
        if key in keys:
            continue
        keys.add(key)
        accepted.append(road)
    return accepted


def _build_query(
    route: Route,
    corridor_metres: float,
    feature_corridor_metres: float = FEATURE_CORRIDOR_METRES,
) -> str:
    coordinates = ",".join(
        f"{point.latitude:.7f},{point.longitude:.7f}" for point in route.points
    )
    area = f"(around:{corridor_metres:.0f},{coordinates})"
    feature_area = f"(around:{feature_corridor_metres:.0f},{coordinates})"
    return (
        "[out:json][timeout:35];("
        f'way["highway"]{area};'
        f'nwr["name"]["amenity"~"hospital|school|university|college|marketplace|place_of_worship"]{area};'
        f'nwr["name"]["shop"="mall"]{area};'
        f'nwr["name"]["tourism"~"attraction|museum"]{area};'
        f'nwr["name"]["leisure"~"stadium|sports_centre"]{area};'
        f'way["highway"]["bridge"]{feature_area};'
        f'way["highway"~"^(footway|pedestrian|path)$"]["bridge"]{feature_area};'
        f'way["waterway"="river"]{feature_area};'
        f'relation["waterway"="river"]{feature_area};'
        f'way["waterway"="riverbank"]{feature_area};'
        f'relation["waterway"="riverbank"]{feature_area};'
        f'way["natural"="water"]["water"="river"]{feature_area};'
        f'relation["natural"="water"]["water"="river"]{feature_area};'
        f'way["waterway"="canal"]{feature_area};'
        f'relation["waterway"="canal"]{feature_area};'
        f'way["natural"="water"]["water"="canal"]{feature_area};'
        f'relation["natural"="water"]["water"="canal"]{feature_area};'
        f'way["building"]{feature_area};'
        f'relation["building"]{feature_area};'
        f'nwr["amenity"="fuel"]{feature_area};'
        f'nwr["shop"~"^(mall|department_store|supermarket)$"]{feature_area};'
        f'nwr["amenity"~"^(hospital|school|university|college|marketplace|place_of_worship)$"]{feature_area};'
        f'nwr["tourism"~"^(museum|attraction)$"]{feature_area};'
        f'nwr["leisure"~"^(stadium|sports_centre)$"]{feature_area};'
        ");out tags center geom;"
    )


def _feature_categories(tags: dict) -> tuple[OSMFeatureCategory, ...]:
    """Return every semantic category supported by an OSM tag set.

    An OSM element can be both a physical footprint and a semantic landmark,
    for example ``building=yes`` with ``amenity=place_of_worship``.  Preserve
    each supported meaning as a separate candidate with the same OSM identity.
    """
    categories: list[OSMFeatureCategory] = []

    def add(category: OSMFeatureCategory) -> None:
        if category not in categories:
            categories.append(category)

    bridge = str(tags.get("bridge", "")).strip().casefold()
    if bridge and bridge not in {"no", "false", "0"} and tags.get("highway"):
        highway = str(tags["highway"]).casefold()
        if highway in {"footway", "pedestrian", "path"}:
            if _allows_footbridge(highway, tags):
                add(OSMFeatureCategory.FOOTBRIDGE)
        else:
            add(OSMFeatureCategory.ROAD_BRIDGE)

    waterway = str(tags.get("waterway", "")).casefold()
    water = str(tags.get("water", "")).casefold()
    natural_water = tags.get("natural") == "water"
    if waterway in {"river", "riverbank"} or (natural_water and water == "river"):
        add(OSMFeatureCategory.RIVER)
    elif waterway == "canal" or (natural_water and water == "canal"):
        add(OSMFeatureCategory.CANAL)
    if tags.get("amenity") == "fuel":
        add(OSMFeatureCategory.FUEL)
    if tags.get("shop") in {"mall", "department_store", "supermarket"}:
        add(OSMFeatureCategory.SHOP)
    if tags.get("amenity") in {
        "hospital",
        "school",
        "university",
        "college",
        "marketplace",
        "place_of_worship",
    } or tags.get("tourism") in {"museum", "attraction"} or tags.get("leisure") in {
        "stadium",
        "sports_centre",
    }:
        add(OSMFeatureCategory.POI)
    if tags.get("building"):
        add(OSMFeatureCategory.BUILDING)
    return tuple(categories)


def _allows_footbridge(highway: str, tags: dict) -> bool:
    foot = str(tags.get("foot", "")).casefold()
    access = str(tags.get("access", "")).casefold()
    if foot in {"no", "private"}:
        return False
    if foot in {"yes", "designated", "permissive"}:
        return True
    if access in {"no", "private"}:
        return False
    return highway in {"footway", "pedestrian", "path"}


def _features_from_element(
    element: dict,
    nodes: dict[int, GeoPoint],
    categories: tuple[OSMFeatureCategory, ...],
    projection: MetricProjection,
    main_metric: LineString,
    corridor_metres: float,
) -> list[ContextFeature]:
    """Build category candidates while reusing each geometry interpretation."""
    tags = element.get("tags") or {}
    osm_type = str(element.get("type", ""))
    parsed: dict[bool, tuple[OSMGeometryKind, tuple] | Exception] = {}
    corridor_results: dict[bool, bool] = {}
    features: list[ContextFeature] = []
    for category in categories:
        polygonal = _is_polygonal_feature(category, tags, osm_type)
        if polygonal not in parsed:
            try:
                parsed[polygonal] = geometry_parts_from_element(
                    element, nodes, polygonal=polygonal
                )
            except (KeyError, TypeError, ValueError) as error:
                parsed[polygonal] = error
        geometry_result = parsed[polygonal]
        if isinstance(geometry_result, Exception):
            warnings.warn(
                f"Could not parse {category.value} {element.get('type')}/"
                f"{element.get('id')}: {geometry_result}",
                OSMFeatureParseWarning,
                stacklevel=2,
            )
            continue
        geometry_kind, parts = geometry_result
        feature = ContextFeature(
            osm_type=osm_type,
            osm_id=int(element["id"]),
            category=category,
            geometry_kind=geometry_kind,
            parts=parts,
            name=osm_feature_name(tags),
            tags=_normalized_feature_tags(tags),
            recommended=True,
            recommendation=f"OSM {category.value.replace('_', ' ')} within route corridor",
        )
        if polygonal not in corridor_results:
            metric_geometry = _feature_metric_geometry(feature, projection)
            if feature.geometry_kind in {
                OSMGeometryKind.POLYGON,
                OSMGeometryKind.MULTIPOLYGON,
            }:
                corridor_results[polygonal] = metric_geometry.intersects(
                    main_metric.buffer(corridor_metres)
                )
            else:
                corridor_results[polygonal] = (
                    metric_geometry.distance(main_metric) <= corridor_metres
                )
        if corridor_results[polygonal]:
            features.append(feature)
    return features


def _is_polygonal_water(category: OSMFeatureCategory, tags: dict) -> bool:
    if category not in {OSMFeatureCategory.RIVER, OSMFeatureCategory.CANAL}:
        return False
    return (
        tags.get("natural") == "water"
        or tags.get("waterway") == "riverbank"
        or tags.get("type") == "multipolygon"
        or tags.get("area") == "yes"
    )


def _is_polygonal_feature(
    category: OSMFeatureCategory, tags: dict, osm_type: str
) -> bool:
    if category is OSMFeatureCategory.BUILDING:
        return True
    if category in {
        OSMFeatureCategory.FUEL,
        OSMFeatureCategory.SHOP,
        OSMFeatureCategory.POI,
    }:
        return osm_type in {"way", "relation"}
    return _is_polygonal_water(category, tags)


def _normalized_feature_tags(tags: dict) -> tuple[tuple[str, str], ...]:
    allowed = {
        "access",
        "area",
        "bridge",
        "building",
        "foot",
        "highway",
        "layer",
        "leisure",
        "amenity",
        "name",
        "name:th",
        "natural",
        "shop",
        "tourism",
        "type",
        "water",
        "waterway",
    }
    return tuple(
        sorted(
            (str(key), str(value))
            for key, value in tags.items()
            if key in allowed
        )
    )


def _feature_metric_geometry(feature: ContextFeature, projection: MetricProjection):
    def xy(points: tuple[GeoPoint, ...]) -> list[tuple[float, float]]:
        return [projection.to_metric(point) for point in points]

    if feature.geometry_kind is OSMGeometryKind.POINT:
        return Point(projection.to_metric(feature.parts[0].coordinates[0]))
    if feature.geometry_kind is OSMGeometryKind.LINESTRING:
        return LineString(xy(feature.parts[0].coordinates))
    if feature.geometry_kind is OSMGeometryKind.MULTILINESTRING:
        return MultiLineString([xy(part.coordinates) for part in feature.parts])
    polygons = [
        Polygon(xy(part.coordinates), [xy(hole) for hole in part.holes])
        for part in feature.parts
    ]
    if feature.geometry_kind is OSMGeometryKind.POLYGON:
        return polygons[0]
    if feature.geometry_kind is OSMGeometryKind.MULTIPOLYGON:
        return MultiPolygon(polygons)
    raise ValueError(f"Unsupported feature geometry: {feature.geometry_kind}")


def _prepare_water_and_bridge_context(
    features: list[ContextFeature],
    projection: MetricProjection,
    main_metric: LineString,
    corridor_metres: float,
) -> list[ContextFeature]:
    """Add derived display geometry and conservative bridge/water relationships."""

    prepared: list[ContextFeature] = []
    waters: list[tuple[ContextFeature, object]] = []
    for feature in features:
        metric = _feature_metric_geometry(feature, projection)
        if feature.category in {OSMFeatureCategory.RIVER, OSMFeatureCategory.CANAL}:
            display = _clip_water_context(
                metric, main_metric, corridor_metres, WATER_CONTEXT_MARGIN_METRES
            )
            converted = _portable_parts(display, projection)
            if converted is not None:
                kind, parts = converted
                feature = replace(
                    feature, display_geometry_kind=kind, display_parts=parts
                )
            waters.append((feature, metric))
        prepared.append(feature)

    result: list[ContextFeature] = []
    for feature in prepared:
        if feature.category not in {
            OSMFeatureCategory.ROAD_BRIDGE,
            OSMFeatureCategory.FOOTBRIDGE,
        }:
            result.append(feature)
            continue
        bridge = _feature_metric_geometry(feature, projection)
        # Sub-metre tolerance covers independent OSM ways whose coordinates
        # describe the same crossing without sharing an identical node.
        matches = [
            (water, geometry) for water, geometry in waters
            if bridge.intersects(geometry) or bridge.distance(geometry) <= 0.25
        ]
        if len(matches) != 1:
            result.append(replace(
                feature,
                crosses_category=None,
                crosses_feature_key="",
                crosses_source_id="",
                crosses_name=None,
                recommendation=feature.recommendation.partition("; crosses ")[0],
            ))
            continue
        water, _geometry = matches[0]
        label = water.category.value.replace("_", " ").title()
        if water.name:
            label += f" — {water.name}"
        result.append(replace(
            feature,
            crosses_category=water.category,
            crosses_feature_key=water.feature_key,
            crosses_source_id=water.source_id,
            crosses_name=water.name,
            recommendation=(
                f"{feature.recommendation.partition('; crosses ')[0]}; crosses {label}"
            ),
        ))
    return result


def _clip_water_context(water, main: LineString, corridor: float, margin: float):
    """Clip water for display while keeping the authoritative geometry untouched."""

    if isinstance(water, (Polygon, MultiPolygon)):
        return water.intersection(main.buffer(corridor + margin))
    lines = list(water.geoms) if isinstance(water, MultiLineString) else [water]
    clipped = []
    core = main.buffer(corridor)
    for line in lines:
        relevant = line.intersection(core)
        if relevant.is_empty:
            continue
        coordinates = []
        for geometry in getattr(relevant, "geoms", (relevant,)):
            if isinstance(geometry, (LineString, Point)):
                coordinates.extend(geometry.coords)
        if not coordinates:
            continue
        stations = [line.project(Point(coordinate)) for coordinate in coordinates]
        segment = substring(
            line, max(0.0, min(stations) - margin), min(line.length, max(stations) + margin)
        )
        if isinstance(segment, LineString) and segment.length > 0:
            clipped.append(segment)
    if not clipped:
        return water
    return clipped[0] if len(clipped) == 1 else MultiLineString(clipped)


def _portable_parts(geometry, projection: MetricProjection):
    """Convert a derived metric geometry to the portable domain representation."""

    if geometry.is_empty:
        return None
    if isinstance(geometry, GeometryCollection):
        usable = [item for item in geometry.geoms if isinstance(item, (LineString, Polygon))]
        if not usable:
            return None
        line_items = [item for item in usable if isinstance(item, LineString)]
        polygon_items = [item for item in usable if isinstance(item, Polygon)]
        geometry = MultiPolygon(polygon_items) if polygon_items else MultiLineString(line_items)

    def points(coords):
        return tuple(projection.to_geographic(float(x), float(y)) for x, y in coords)

    if isinstance(geometry, LineString):
        return OSMGeometryKind.LINESTRING, (ContextGeometryPart(points(geometry.coords)),)
    if isinstance(geometry, MultiLineString):
        return OSMGeometryKind.MULTILINESTRING, tuple(
            ContextGeometryPart(points(line.coords)) for line in geometry.geoms if line.length > 0
        )
    polygons = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
    parts = tuple(
        ContextGeometryPart(
            points(polygon.exterior.coords),
            tuple(points(ring.coords) for ring in polygon.interiors),
        )
        for polygon in polygons if isinstance(polygon, Polygon) and not polygon.is_empty
    )
    if not parts:
        return None
    kind = OSMGeometryKind.POLYGON if len(parts) == 1 else OSMGeometryKind.MULTIPOLYGON
    return kind, parts


def _download_overpass(query: str) -> bytes:
    body = urlencode({"data": query}).encode("utf-8")
    last_error = None
    for endpoint in OVERPASS_URLS:
        request = Request(
            endpoint,
            data=body,
            headers={"User-Agent": "PoleRoute-Schematic/0.1 (OSM context preview)"},
        )
        try:
            with urlopen(request, timeout=25) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            last_error = error
    assert last_error is not None
    raise last_error


def _way_points(element: dict, nodes: dict[int, GeoPoint]) -> tuple[GeoPoint, ...]:
    geometry = element.get("geometry")
    if isinstance(geometry, list):
        return tuple(
            GeoPoint(float(point["lon"]), float(point["lat"]))
            for point in geometry
            if "lon" in point and "lat" in point
        )
    return tuple(nodes[node_id] for node_id in element.get("nodes", []) if node_id in nodes)


def _suggested_width(highway: str, tags: dict) -> float:
    if tags.get("width"):
        try:
            return max(1.0, float(str(tags["width"]).split()[0]))
        except ValueError:
            pass
    return {
        "motorway": 14.0,
        "trunk": 12.0,
        "primary": 10.0,
        "secondary": 8.0,
        "tertiary": 7.0,
        "residential": 6.0,
        "unclassified": 5.0,
        "service": 4.0,
        "living_street": 4.0,
    }.get(highway, 4.0)


def _place_from_element(element: dict, nodes: dict[int, GeoPoint]) -> ContextPlace | None:
    tags = element.get("tags") or {}
    name = tags.get("name") or tags.get("name:th")
    category = next((tags[key] for key in ("amenity", "shop", "tourism", "leisure") if key in tags), None)
    if not name or not category:
        return None
    if element.get("type") == "node" and element.get("id") in nodes:
        point = nodes[element["id"]]
    elif isinstance(element.get("center"), dict):
        center = element["center"]
        point = GeoPoint(float(center["lon"]), float(center["lat"]))
    else:
        return None
    return ContextPlace(str(name), str(category), point)
