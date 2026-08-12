"""Create selectable non-scale schematic pole layouts."""

from enum import StrEnum
from math import atan2, degrees

from shapely.geometry import LineString
from shapely.ops import unary_union

from pole_route.domain.pole import PoleSide
from pole_route.domain.schematic import SchematicLayout, SchematicPole, SchematicRoad
from pole_route.geometry.road_geometry import RoadGeometry, RoadNetworkGeometry

DEFAULT_POLE_SPACING = 150.0
ROAD_HALF_HEIGHT = 36.0
POLE_DISTANCE_FROM_EDGE = 72.0
HORIZONTAL_MARGIN = 120.0
VERTICAL_CENTER = 250.0
PROJECTED_LAYOUT_LENGTH = 1200.0


class PoleSpacingMode(StrEnum):
    EQUAL = "equal"
    PROJECTED_STATION = "projected_station"


class SchematicLayoutMode(StrEnum):
    NETWORK = "network"
    STRAIGHT_EQUAL = "straight_equal"
    STRAIGHT_RELATIVE = "straight_relative"


def create_schematic_layout(
    geometry: RoadGeometry | RoadNetworkGeometry,
    spacing_mode: PoleSpacingMode = PoleSpacingMode.EQUAL,
    layout_mode: SchematicLayoutMode | None = None,
    same_pole_groups: tuple[frozenset[str], ...] = (),
) -> SchematicLayout:
    """Order poles by route station and apply the selected visual spacing."""
    if isinstance(geometry, RoadNetworkGeometry) and layout_mode in {
        None,
        SchematicLayoutMode.NETWORK,
    }:
        return _create_network_layout(geometry, same_pole_groups)

    if isinstance(geometry, RoadNetworkGeometry):
        spacing_mode = (
            PoleSpacingMode.EQUAL
            if layout_mode is SchematicLayoutMode.STRAIGHT_EQUAL
            else PoleSpacingMode.PROJECTED_STATION
        )
        geometry = RoadGeometry(
            geometry.projection,
            geometry.roads[0].centerline,
            geometry.roads[0].left_edge,
            geometry.roads[0].right_edge,
            geometry.roads[0].left_pole_line,
            geometry.roads[0].right_pole_line,
            geometry.projected_poles,
            geometry.unplaced_poles,
            geometry.roads[0].road_width_metres,
            geometry.roads[0].pole_offset_metres,
            geometry.roads[0].pole_line_enabled,
        )

    def source_station(item):
        if isinstance(geometry, RoadNetworkGeometry):
            return geometry.roads[item.route_index].centerline.project(item.snapped)
        return geometry.centerline.project(item.snapped)

    ordered = sorted(
        geometry.projected_poles,
        key=lambda item: (item.route_index, source_station(item), item.pole.number),
    )
    pole_count = len(ordered)
    if spacing_mode is PoleSpacingMode.EQUAL:
        content_length = max(pole_count - 1, 0) * DEFAULT_POLE_SPACING
    else:
        content_length = PROJECTED_LAYOUT_LENGTH if pole_count > 1 else 0.0
    road_length = max(760.0, content_length + 240.0)
    width = road_length + 2 * HORIZONTAL_MARGIN
    road_left = HORIZONTAL_MARGIN
    road_right = width - HORIZONTAL_MARGIN
    road_top = VERTICAL_CENTER - ROAD_HALF_HEIGHT
    road_bottom = VERTICAL_CENTER + ROAD_HALF_HEIGHT
    first_x = (width - content_length) / 2
    if ordered:
        stations = [source_station(item) for item in ordered]
        station_min = min(stations)
        station_span = max(max(stations) - station_min, 1e-9)
    else:
        stations = []
        station_span = 1.0

    poles = []
    equal_positions: list[int] = []
    distinct_position = -1
    previous_key = None
    for projected in ordered:
        # Poles snapped onto exactly the same location are deliberately stacked.
        key = (projected.route_index, round(source_station(projected), 3))
        if key != previous_key:
            distinct_position += 1
            previous_key = key
        equal_positions.append(distinct_position)
    if spacing_mode is PoleSpacingMode.EQUAL:
        content_length = max(distinct_position, 0) * DEFAULT_POLE_SPACING
        road_length = max(760.0, content_length + 240.0)
        width = road_length + 2 * HORIZONTAL_MARGIN
        road_right = width - HORIZONTAL_MARGIN
        first_x = (width - content_length) / 2
    for index, projected in enumerate(ordered):
        side = projected.pole.side
        y = (
            road_top - POLE_DISTANCE_FROM_EDGE
            if side is PoleSide.LEFT
            else road_bottom + POLE_DISTANCE_FROM_EDGE
        )
        poles.append(
            SchematicPole(
                projected.pole.number,
                projected.pole.detail,
                side,
                (
                    first_x + equal_positions[index] * DEFAULT_POLE_SPACING
                    if spacing_mode is PoleSpacingMode.EQUAL
                    else first_x + ((stations[index] - station_min) / station_span) * content_length
                ),
                y,
                stations[index],
                _marker_id(projected.pole.number, same_pole_groups),
            )
        )

    return SchematicLayout(
        width,
        500.0,
        road_left,
        road_right,
        road_top,
        road_bottom,
        tuple(poles),
    )


def _create_network_layout(
    geometry: RoadNetworkGeometry,
    same_pole_groups: tuple[frozenset[str], ...],
) -> SchematicLayout:
    """Preserve the shared topology of every imported road in one editable schematic."""
    canvas_width = 1600.0
    canvas_height = 850.0
    margin = 120.0
    all_lines = [
        line
        for road in geometry.roads
        for line in (road.centerline, road.left_edge, road.right_edge)
    ]
    coordinates = [coordinate for line in all_lines for coordinate in line.coords]
    min_x = min(x for x, _y in coordinates)
    max_x = max(x for x, _y in coordinates)
    min_y = min(y for _x, y in coordinates)
    max_y = max(y for _x, y in coordinates)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    scale = min(
        (canvas_width - 2 * margin) / span_x,
        (canvas_height - 2 * margin) / span_y,
    )

    def point_xy(x: float, y: float) -> tuple[float, float]:
        return (
            margin + (x - min_x) * scale,
            margin + (max_y - y) * scale,
        )

    def line_points(line) -> tuple[tuple[float, float], ...]:
        return tuple(point_xy(x, y) for x, y in line.coords)

    roads = tuple(
        SchematicRoad(
            line_points(road.centerline),
            line_points(road.left_edge),
            line_points(road.right_edge),
        )
        for road in geometry.roads
    )
    road_surface = unary_union([
        road.centerline.buffer(road.road_width_metres / 2.0, cap_style="flat", join_style="round")
        for road in geometry.roads
    ])
    boundaries = tuple(line_points(line) for line in _open_road_boundaries(road_surface, geometry))

    raw_poles = [
        SchematicPole(
            projected.pole.number,
            projected.pole.detail,
            projected.pole.side,
            *point_xy(projected.snapped.x, projected.snapped.y),
            geometry.roads[projected.route_index].centerline.project(projected.snapped),
            _marker_id(projected.pole.number, same_pole_groups),
            _schematic_road_angle(
                geometry.roads[projected.route_index].centerline,
                geometry.roads[projected.route_index].centerline.project(projected.snapped),
            ),
        )
        for projected in geometry.projected_poles
    ]
    marker_positions: dict[str, tuple[float, float]] = {}
    poles = []
    for pole in raw_poles:
        position = marker_positions.setdefault(pole.marker_id or pole.number, (pole.x, pole.y))
        poles.append(
            SchematicPole(
                pole.number,
                pole.detail,
                pole.side,
                position[0],
                position[1],
                pole.source_station_metres,
                pole.marker_id,
                pole.road_angle_degrees,
            )
        )
    return SchematicLayout(
        canvas_width,
        canvas_height,
        margin,
        canvas_width - margin,
        canvas_height / 2 - ROAD_HALF_HEIGHT,
        canvas_height / 2 + ROAD_HALF_HEIGHT,
        tuple(poles),
        roads,
        boundaries,
    )


def _schematic_road_angle(line, station: float) -> float:
    """Return local road direction after map Y is flipped for the canvas."""
    step = max(min(line.length * 0.001, 1.0), 0.01)
    before = line.interpolate(max(0.0, station - step))
    after = line.interpolate(min(line.length, station + step))
    return degrees(atan2(-(after.y - before.y), after.x - before.x))


def _open_road_boundaries(road_surface, geometry: RoadNetworkGeometry):
    """Remove only exposed end caps while retaining joined junction boundaries."""
    cap_lines = []
    for road in geometry.roads:
        cap_lines.extend(
            (
                LineString((road.left_edge.coords[0], road.right_edge.coords[0])),
                LineString((road.left_edge.coords[-1], road.right_edge.coords[-1])),
            )
        )
    tolerance = max(min(road.road_width_metres for road in geometry.roads) * 0.02, 0.01)
    opened = road_surface.boundary.difference(unary_union(cap_lines).buffer(tolerance))
    return list(opened.geoms) if hasattr(opened, "geoms") else [opened]


def _marker_id(number: str, groups: tuple[frozenset[str], ...]) -> str:
    for index, group in enumerate(groups, start=1):
        if number in group:
            return f"same-pole-{index}"
    return number
