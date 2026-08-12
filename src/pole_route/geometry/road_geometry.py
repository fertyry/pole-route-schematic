"""Build metric road offsets and snap poles to their designated side."""

from dataclasses import dataclass

from shapely.geometry import LineString, Point

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.projection import MetricProjection


class RoadGeometryError(ValueError):
    """Road or pole inputs cannot produce usable offset geometry."""


@dataclass(frozen=True, slots=True)
class ProjectedPole:
    pole: Pole
    original: Point
    snapped: Point

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
    )


def _offset(centerline: LineString, distance: float, label: str) -> LineString:
    result = centerline.offset_curve(distance, join_style="round")
    if result.is_empty or not isinstance(result, LineString):
        raise RoadGeometryError(f"Could not create {label} from this centerline")
    return result


def _pole_point(pole: Pole) -> GeoPoint:
    return GeoPoint(pole.longitude, pole.latitude)
