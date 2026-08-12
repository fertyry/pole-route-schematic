"""Fetch and classify OpenStreetMap context around a confirmed route."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import LineString
from shapely.ops import nearest_points, substring

from pole_route.domain.context import ContextPlace, ContextRoad, OSMContext
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.projection import MetricProjection

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
DEFAULT_CORRIDOR_METRES = 15.0
CONTEXT_ROAD_EXTENSION_METRES = 35.0


class OSMContextError(RuntimeError):
    """OpenStreetMap surroundings cannot be downloaded or interpreted."""


def fetch_osm_context(
    main_route: Route,
    corridor_metres: float = DEFAULT_CORRIDOR_METRES,
    *,
    fetcher: Callable[[str], bytes] | None = None,
) -> OSMContext:
    """Return roads and named landmarks within a corridor of ``main_route``."""
    if corridor_metres <= 0:
        raise ValueError("Context corridor must be greater than zero")
    query = _build_query(main_route, corridor_metres)
    try:
        payload = (fetcher or _download_overpass)(query)
        document = json.loads(payload)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise OSMContextError(f"Could not contact OpenStreetMap: {error}") from error
    except (json.JSONDecodeError, TypeError) as error:
        raise OSMContextError("OpenStreetMap returned an invalid response") from error
    return parse_osm_context(document, main_route, corridor_metres)


def parse_osm_context(
    document: dict,
    main_route: Route,
    corridor_metres: float = DEFAULT_CORRIDOR_METRES,
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

    for element in elements:
        tags = element.get("tags") or {}
        if element.get("type") == "way" and tags.get("highway"):
            if tags.get("highway") in {
                "footway",
                "path",
                "cycleway",
                "steps",
                "bridleway",
                "corridor",
                "construction",
                "proposed",
            }:
                continue
            points = _way_points(element, nodes)
            if len(points) < 2:
                continue
            candidate = LineString([projection.to_metric(point) for point in points])
            distance_to_main = candidate.distance(main_metric)
            if distance_to_main > corridor_metres or candidate.length < 8.0:
                continue
            highway = str(tags["highway"])
            source_name = tags.get("name") or tags.get("name:th")
            if highway == "service" and (
                not source_name
                or tags.get("service") in {"driveway", "parking_aisle", "drive-through"}
            ):
                continue
            if not source_name and distance_to_main > 18.0:
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
                )
            )
        place = _place_from_element(element, nodes)
        if place is not None:
            point_metric = projection.to_metric(place.point)
            if main_metric.distance(LineString([point_metric, point_metric])) <= corridor_metres:
                places.append(place)

    roads.sort(key=lambda item: item.route.name.casefold())
    places.sort(key=lambda item: item.name.casefold())
    return OSMContext(tuple(roads), tuple(places))


def _build_query(route: Route, corridor_metres: float) -> str:
    coordinates = ",".join(
        f"{point.latitude:.7f},{point.longitude:.7f}" for point in route.points
    )
    area = f"(around:{corridor_metres:.0f},{coordinates})"
    return (
        "[out:json][timeout:35];("
        f'way["highway"]{area};'
        f'nwr["name"]["amenity"~"hospital|school|university|college|marketplace|place_of_worship"]{area};'
        f'nwr["name"]["shop"="mall"]{area};'
        f'nwr["name"]["tourism"~"attraction|museum"]{area};'
        f'nwr["name"]["leisure"~"stadium|sports_centre"]{area};'
        ");out tags center geom;"
    )


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
