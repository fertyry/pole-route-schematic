"""Create selectable non-scale schematic pole layouts."""

from enum import StrEnum

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


def create_schematic_layout(
    geometry: RoadGeometry | RoadNetworkGeometry,
    spacing_mode: PoleSpacingMode = PoleSpacingMode.EQUAL,
) -> SchematicLayout:
    """Order poles by route station and apply the selected visual spacing."""
    if isinstance(geometry, RoadNetworkGeometry):
        return _create_network_layout(geometry)

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


def _create_network_layout(geometry: RoadNetworkGeometry) -> SchematicLayout:
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
    poles = tuple(
        SchematicPole(
            projected.pole.number,
            projected.pole.detail,
            projected.pole.side,
            *point_xy(projected.snapped.x, projected.snapped.y),
            geometry.roads[projected.route_index].centerline.project(projected.snapped),
        )
        for projected in geometry.projected_poles
    )
    return SchematicLayout(
        canvas_width,
        canvas_height,
        margin,
        canvas_width - margin,
        canvas_height / 2 - ROAD_HALF_HEIGHT,
        canvas_height / 2 + ROAD_HALF_HEIGHT,
        poles,
        roads,
    )
