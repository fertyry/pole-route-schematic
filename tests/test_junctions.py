from shapely.geometry import LineString

from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.geometry.junctions import prepare_manual_junctions
from pole_route.geometry.projection import MetricProjection


def _route(name, route_type, points):
    return ClassifiedRoute(
        Route(name, "test.kml", tuple(GeoPoint(x, y) for x, y in points)),
        route_type,
        10.0,
        None,
        False,
    )


def test_cross_road_small_gap_is_connected_to_main():
    main = _route("main", RouteType.MAIN_ROUTE, ((100.0, 13.0), (100.01, 13.0)))
    cross = _route(
        "cross", RouteType.CROSS_ROAD, ((100.005, 12.999), (100.005, 12.99999))
    )
    prepared, changes, errors = prepare_manual_junctions([main, cross], 5.0)
    projection = MetricProjection.for_points(main.route.points + cross.route.points)
    main_line = LineString(projection.to_metric(point) for point in prepared[0].route.points)
    cross_line = LineString(projection.to_metric(point) for point in prepared[1].route.points)
    assert cross_line.intersects(main_line)
    assert changes
    assert not errors


def test_t_junction_that_does_not_reach_main_is_rejected():
    main = _route("main", RouteType.MAIN_ROUTE, ((100.0, 13.0), (100.01, 13.0)))
    branch = _route(
        "branch", RouteType.T_JUNCTION, ((100.005, 13.001), (100.006, 13.001))
    )
    _prepared, _changes, errors = prepare_manual_junctions([main, branch], 5.0)
    assert errors


def test_t_junction_crossing_main_is_trimmed_to_longer_arm():
    main = _route("main", RouteType.MAIN_ROUTE, ((100.0, 13.0), (100.01, 13.0)))
    branch = _route(
        "branch",
        RouteType.T_JUNCTION,
        ((100.005, 13.002), (100.005, 12.9995)),
    )
    prepared, changes, errors = prepare_manual_junctions([main, branch], 5.0)
    projection = MetricProjection.for_points(main.route.points + branch.route.points)
    result = LineString(projection.to_metric(point) for point in prepared[1].route.points)
    main_line = LineString(projection.to_metric(point) for point in main.route.points)
    assert result.distance(main_line) < 0.01
    assert result.length < 230.0
    assert changes
    assert not errors
