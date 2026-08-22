from __future__ import annotations

from pole_route.domain.route import GeoPoint, Route
from pole_route.importers.route_batches import split_route_by_distance


def _route(delta_latitude: float) -> Route:
    return Route(
        "Route", "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.0 + delta_latitude)),
    )


def test_short_route_stays_in_one_batch():
    batches = split_route_by_distance(_route(0.01), batch_metres=3000, overlap_metres=150)
    assert len(batches) == 1
    assert batches[0].route == _route(0.01)


def test_long_route_is_split_by_metric_distance_with_overlap():
    batches = split_route_by_distance(_route(0.09), batch_metres=3000, overlap_metres=150)
    assert len(batches) == 4
    assert batches[0].start_metres == 0
    assert batches[0].end_metres == 3000
    assert batches[1].start_metres == 3000
    assert batches[-1].end_metres > 9000
    # Adjacent fetched routes overlap even though their reported core intervals do not.
    assert batches[0].route.points[-1].latitude > batches[1].route.points[0].latitude


def test_batch_distance_and_overlap_validation():
    route = _route(0.01)
    for distance, overlap in ((0, 0), (100, -1), (100, 100)):
        try:
            split_route_by_distance(route, distance, overlap)
        except ValueError:
            pass
        else:
            raise AssertionError((distance, overlap))
