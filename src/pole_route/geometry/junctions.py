"""Validate and gently connect user-drawn large junction routes to Main routes."""

from dataclasses import replace

from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, substring, unary_union

from pole_route.domain.route import ClassifiedRoute, Route, RouteType
from pole_route.geometry.projection import MetricProjection


def prepare_manual_junctions(
    routes: list[ClassifiedRoute], tolerance_metres: float = 5.0
) -> tuple[list[ClassifiedRoute], tuple[str, ...], tuple[str, ...]]:
    """Snap small drawing gaps and report junctions that need source correction."""
    main_routes = [item for item in routes if item.type is RouteType.MAIN_ROUTE]
    junctions = [
        item
        for item in routes
        if item.type in {RouteType.CROSS_ROAD, RouteType.T_JUNCTION}
    ]
    if not main_routes or not junctions:
        return routes, (), ()

    projection = MetricProjection.for_points(
        tuple(point for item in routes for point in item.route.points)
    )
    main_axis = unary_union(
        [LineString(projection.to_metric(point) for point in item.route.points) for item in main_routes]
    )
    prepared: list[ClassifiedRoute] = []
    changes: list[str] = []
    errors: list[str] = []
    for item in routes:
        if item.type not in {RouteType.CROSS_ROAD, RouteType.T_JUNCTION}:
            prepared.append(item)
            continue
        line = LineString(projection.to_metric(point) for point in item.route.points)
        if item.type is RouteType.CROSS_ROAD:
            if line.intersects(main_axis):
                prepared.append(item)
                continue
            gap = line.distance(main_axis)
            if gap > tolerance_metres:
                errors.append(
                    f"Cross road '{item.route.name}' does not cross a Main route "
                    f"(nearest gap {gap:.1f} m)."
                )
                prepared.append(item)
                continue
            road_point, main_point = nearest_points(line, main_axis)
            adjusted = _insert_connection(line, road_point, main_point)
        else:
            endpoints = (Point(line.coords[0]), Point(line.coords[-1]))
            endpoint = min(endpoints, key=lambda point: point.distance(main_axis))
            endpoint_gap = endpoint.distance(main_axis)
            gap = line.distance(main_axis)
            if endpoint_gap <= tolerance_metres:
                _unused, main_point = nearest_points(endpoint, main_axis)
                coords = list(line.coords)
                coords[0 if endpoint.equals(Point(coords[0])) else -1] = main_point.coords[0]
                adjusted = LineString(coords)
            elif gap <= tolerance_metres:
                road_point, main_point = nearest_points(line, main_axis)
                adjusted = _trim_t_branch(line, road_point, main_point)
            else:
                errors.append(
                    f"T-junction '{item.route.name}' does not reach a Main route "
                    f"(nearest gap {gap:.1f} m)."
                )
                prepared.append(item)
                continue
        route = Route(
            item.route.name,
            item.route.source_path,
            tuple(projection.to_geographic(x, y) for x, y in adjusted.coords),
        )
        prepared.append(replace(item, route=route))
        changes.append(f"{item.route.name}: snapped to Main route ({gap:.1f} m gap)")
    return prepared, tuple(changes), tuple(errors)


def _trim_t_branch(line: LineString, road_point: Point, main_point: Point) -> LineString:
    """Cut a T route at the Main axis and retain its longer approach arm."""
    station = line.project(road_point)
    before = substring(line, 0.0, station)
    after = substring(line, station, line.length)
    if before.length >= after.length:
        coords = list(before.coords)
        coords.extend((road_point.coords[0], main_point.coords[0]))
    else:
        coords = [main_point.coords[0], road_point.coords[0]]
        coords.extend(after.coords)
    return LineString(_without_adjacent_duplicates(coords))


def _without_adjacent_duplicates(coords):
    result = []
    for coord in coords:
        if not result or coord != result[-1]:
            result.append(coord)
    return result


def _insert_connection(line: LineString, road_point: Point, main_point: Point) -> LineString:
    coords = list(line.coords)
    station = line.project(road_point)
    insert_at = 1
    travelled = 0.0
    for index, (start, end) in enumerate(zip(coords, coords[1:])):
        segment = LineString((start, end))
        if travelled + segment.length >= station:
            insert_at = index + 1
            break
        travelled += segment.length
    dx = main_point.x - road_point.x
    dy = main_point.y - road_point.y
    length = max((dx * dx + dy * dy) ** 0.5, 1e-9)
    # Continue a few centimetres beyond the axis so inverse projection rounding
    # cannot leave a visually connected Cross road microscopically short.
    beyond = (main_point.x + dx / length * 0.05, main_point.y + dy / length * 0.05)
    connection = [road_point.coords[0], main_point.coords[0], beyond]
    return LineString(coords[:insert_at] + connection + coords[insert_at:])
