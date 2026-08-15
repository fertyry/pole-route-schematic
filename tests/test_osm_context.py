import json

from pole_route.domain.route import GeoPoint, Route
from pole_route.importers.osm_context import fetch_osm_context, parse_osm_context
from pole_route.ui.osm_context_worker import OSMContextWorker


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


def test_osm_context_keeps_only_true_connections_and_deduplicates_split_ways() -> None:
    document = {
        "elements": [
            {
                "type": "way",
                "id": 1,
                "geometry": [
                    {"lat": 13.005, "lon": 99.9995},
                    {"lat": 13.005, "lon": 100.0},
                ],
                "tags": {"highway": "residential", "name": "Soi One"},
            },
            {
                "type": "way",
                "id": 2,
                "geometry": [
                    {"lat": 13.005, "lon": 100.0},
                    {"lat": 13.005, "lon": 100.0005},
                ],
                "tags": {"highway": "residential", "name": "Soi One"},
            },
            {
                "type": "way",
                "id": 3,
                "geometry": [
                    {"lat": 13.0, "lon": 100.00003},
                    {"lat": 13.01, "lon": 100.00003},
                ],
                "tags": {"highway": "residential", "name": "Parallel Road"},
            },
        ]
    }

    context = parse_osm_context(document, _main_route(), 15.0)

    assert [road.route.name for road in context.roads] == ["Soi One"]
    assert context.roads[0].recommended is True


def test_osm_context_worker_reports_success_and_finishes(qtbot, monkeypatch) -> None:
    import pole_route.ui.osm_context_worker as worker_module

    expected = parse_osm_context({"elements": []}, _main_route(), 15.0)
    monkeypatch.setattr(worker_module, "fetch_osm_context", lambda _route: expected)
    worker = OSMContextWorker(_main_route())

    with qtbot.waitSignal(worker.finished), qtbot.waitSignal(worker.succeeded) as succeeded:
        worker.run()

    assert succeeded.args == [expected]
