import json

from pole_route.domain.route import GeoPoint, Route
from pole_route.importers.osm_context import fetch_osm_context, parse_osm_context


def _main_route() -> Route:
    return Route("Main", "A003.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.01)))


def test_parse_osm_context_keeps_and_clips_nearby_roads_and_named_places() -> None:
    document = {
        "elements": [
            {"type": "node", "id": 1, "lat": 13.005, "lon": 99.999},
            {"type": "node", "id": 2, "lat": 13.005, "lon": 100.001},
            {"type": "node", "id": 3, "lat": 13.005, "lon": 100.02},
            {"type": "node", "id": 4, "lat": 13.006, "lon": 100.02},
            {
                "type": "way",
                "id": 10,
                "geometry": [
                    {"lat": 13.005, "lon": 99.999},
                    {"lat": 13.005, "lon": 100.001},
                ],
                "tags": {"highway": "residential", "name": "Soi Test"},
            },
            {"type": "way", "id": 11, "nodes": [3, 4], "tags": {"highway": "service"}},
            {
                "type": "node",
                "id": 20,
                "lat": 13.004,
                "lon": 100.0001,
                "tags": {"name": "Test School", "amenity": "school"},
            },
        ]
    }

    context = parse_osm_context(document, _main_route(), 15.0)

    assert [road.route.name for road in context.roads] == ["Soi Test"]
    assert context.roads[0].suggested_width_metres == 6.0
    assert context.roads[0].route.points[0].longitude > 99.999
    assert context.roads[0].route.points[-1].longitude < 100.001
    assert [(place.name, place.category) for place in context.places] == [("Test School", "school")]


def test_fetch_osm_context_uses_injected_transport() -> None:
    captured = []

    def fetcher(query: str) -> bytes:
        captured.append(query)
        return json.dumps({"elements": []}).encode()

    context = fetch_osm_context(_main_route(), fetcher=fetcher)

    assert context.roads == ()
    assert context.places == ()
    assert 'way["highway"]' in captured[0]
    assert "(around:15," in captured[0]
