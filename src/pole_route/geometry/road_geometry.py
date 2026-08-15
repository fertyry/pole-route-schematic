"""Build metric road offsets and snap poles to their designated side."""

from dataclasses import dataclass

from shapely.geometry import LineString, Point

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.geometry.projection import MetricProjection


class RoadGeometryError(ValueError):
    """Road or pole inputs cannot produce usable offset geometry."""


@dataclass(frozen=True, slots=True)
class ProjectedPole:
    pole: Pole
    original: Point
    snapped: Point
    route_index: int = 0

    @property
    def displacement_metres(self) -> float:
        return self.original.distance(self.snapped)


@dataclass(frozen=True, slots=True)
class RoadGeometry:
    projection: MetricProjection
    centerline: LineString
    left_edge: LineString
    right_edge: LineString
    left_pole_line: LineString
    right_pole_line: LineString
    projected_poles: tuple[ProjectedPole, ...]
    unplaced_poles: tuple[Pole, ...]
    road_width_metres: float
    pole_offset_metres: float
    pole_line_enabled: bool = True
    is_main_route: bool = False
    route_name: str = ""
    route_type: RouteType = RouteType.ROAD


@dataclass(frozen=True, slots=True)
class RoadNetworkGeometry:
    """Metric geometry for every selected road LineString."""

    projection: MetricProjection
    roads: tuple[RoadGeometry, ...]
    projected_poles: tuple[ProjectedPole, ...]
    unplaced_poles: tuple[Pole, ...]
    skipped_context_routes: tuple[str, ...] = ()

    @property
    def centerline(self) -> LineString:
        """Compatibility centerline used by the current single-road schematic."""
        return self.roads[0].centerline


def build_road_geometry(
    route: Route,
    poles: list[Pole],
    road_width_metres: float,
    pole_offset_metres: float,
) -> RoadGeometry:
    """Create road edges/pole lines and snap known-side poles in a metric CRS."""
    if road_width_metres <= 0:
        raise RoadGeometryError("Road width must be greater than zero")
    if pole_offset_metres < 0:
        raise RoadGeometryError("Pole offset cannot be negative")

    projection = MetricProjection.for_points(route.points)
    centerline = LineString(projection.to_metric(point) for point in route.points)
    if centerline.length <= 0:
        raise RoadGeometryError("Route centerline has zero length")

    half_width = road_width_metres / 2.0
    pole_distance = half_width + pole_offset_metres
    left_edge = _offset(centerline, half_width, "left road edge")
    right_edge = _offset(centerline, -half_width, "right road edge")
    left_pole_line = _offset(centerline, pole_distance, "left pole line")
    right_pole_line = _offset(centerline, -pole_distance, "right pole line")

    projected: list[ProjectedPole] = []
    unplaced: list[Pole] = []
    for pole in poles:
        if pole.side is PoleSide.UNKNOWN:
            unplaced.append(pole)
            continue
        original = Point(projection.to_metric(_pole_point(pole)))
        target = left_pole_line if pole.side is PoleSide.LEFT else right_pole_line
        snapped = target.interpolate(target.project(original))
        projected.append(ProjectedPole(pole, original, snapped))

    return RoadGeometry(
        projection,
        centerline,
        left_edge,
        right_edge,
        left_pole_line,
        right_pole_line,
        tuple(projected),
        tuple(unplaced),
        road_width_metres,
        pole_offset_metres,
        True,
        True,
        route.name,
        RouteType.MAIN_ROUTE,
    )


def build_road_network_geometry(
    routes: list[ClassifiedRoute],
    poles: list[Pole],
) -> RoadNetworkGeometry:
    """Build every selected road and project each pole to its nearest matching offset line."""
    road_routes = [
        item
        for item in routes
        if item.type in {
            RouteType.MAIN_ROUTE,
            RouteType.CROSS_ROAD,
            RouteType.T_JUNCTION,
            RouteType.ROAD,
            RouteType.BRIDGE,
        }
    ]
    if not road_routes:
        raise RoadGeometryError("At least one road route is required")

    projection = MetricProjection.for_points(
        tuple(point for item in road_routes for point in item.route.points)
    )
    roads_list: list[RoadGeometry] = []
    skipped_context_routes: list[str] = []
    for item in road_routes:
        try:
            roads_list.append(_build_road_with_projection(item, projection))
        except RoadGeometryError as error:
            if item.type is RouteType.MAIN_ROUTE:
                raise RoadGeometryError(
                    f"Main route '{item.route.name}' is invalid: {error}"
                ) from error
            skipped_context_routes.append(item.route.name)
    roads = tuple(roads_list)
    if not roads:
        raise RoadGeometryError("No usable road geometry could be created")
    projected: list[ProjectedPole] = []
    unplaced: list[Pole] = []
    for pole in poles:
        if pole.side is PoleSide.UNKNOWN:
            unplaced.append(pole)
            continue
        original = Point(projection.to_metric(_pole_point(pole)))
        candidates = [
            (index, road.left_pole_line if pole.side is PoleSide.LEFT else road.right_pole_line)
            for index, road in enumerate(roads)
            if road.pole_line_enabled
        ]
        if not candidates:
            unplaced.append(pole)
            continue
        route_index, target = min(candidates, key=lambda item: item[1].distance(original))
        snapped = target.interpolate(target.project(original))
        projected.append(ProjectedPole(pole, original, snapped, route_index))

    return RoadNetworkGeometry(
        projection,
        roads,
        tuple(projected),
        tuple(unplaced),
        tuple(skipped_context_routes),
    )


def _build_road_with_projection(
    item: ClassifiedRoute,
    projection: MetricProjection,
) -> RoadGeometry:
    width = item.width_metres
    pole_offset = item.pole_offset_metres if item.create_pole_line else 0.0
    if width is None or width <= 0:
        raise RoadGeometryError(f"Road width for '{item.route.name}' must be greater than zero")
    if pole_offset is None or pole_offset < 0:
        raise RoadGeometryError(f"Pole offset for '{item.route.name}' cannot be negative")
    centerline = LineString(projection.to_metric(point) for point in item.route.points)
    if centerline.length <= 0:
        raise RoadGeometryError("centerline has zero length")
    half_width = width / 2.0
    pole_distance = half_width + pole_offset
    return RoadGeometry(
        projection,
        centerline,
        _offset(centerline, half_width, f"left road edge for '{item.route.name}'"),
        _offset(centerline, -half_width, f"right road edge for '{item.route.name}'"),
        _offset(centerline, pole_distance, f"left pole line for '{item.route.name}'"),
        _offset(centerline, -pole_distance, f"right pole line for '{item.route.name}'"),
        (),
        (),
        width,
        pole_offset,
        item.create_pole_line,
        item.type is RouteType.MAIN_ROUTE,
        item.route.name,
        item.type,
    )


def _offset(centerline: LineString, distance: float, label: str) -> LineString:
    result = centerline.offset_curve(distance, join_style="round")
    if result.is_empty or not isinstance(result, LineString):
        raise RoadGeometryError(f"Could not create {label} from this centerline")
    return result


def _pole_point(pole: Pole) -> GeoPoint:
    return GeoPoint(pole.longitude, pole.latitude)
