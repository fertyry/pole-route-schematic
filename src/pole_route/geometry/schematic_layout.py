"""Create selectable non-scale schematic pole layouts."""

from enum import StrEnum
from math import atan2, degrees

from shapely.geometry import LineString
from shapely.ops import substring, unary_union

from pole_route.domain.pole import PoleSide
from pole_route.domain.schematic import SchematicLayout, SchematicPole, SchematicRoad
from pole_route.geometry.road_geometry import RoadGeometry, RoadNetworkGeometry

DEFAULT_POLE_SPACING = 150.0
ROAD_HALF_HEIGHT = 36.0
POLE_DISTANCE_FROM_EDGE = 72.0
HORIZONTAL_MARGIN = 120.0
VERTICAL_CENTER = 250.0
PROJECTED_LAYOUT_LENGTH = 1200.0
CONTEXT_ROAD_DISPLAY_LENGTH = 70.0


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
    transformer_rack_groups: tuple[frozenset[str], ...] = (),
) -> SchematicLayout:
    """Order poles by route station and apply the selected visual spacing."""
    if isinstance(geometry, RoadNetworkGeometry) and layout_mode in {
        None,
        SchematicLayoutMode.NETWORK,
    }:
        return _create_network_layout(geometry, same_pole_groups, transformer_rack_groups)

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
                installed_quantity=projected.pole.installed_quantity,
                physical_kind=_physical_kind(projected.pole.number, transformer_rack_groups),
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
    transformer_rack_groups: tuple[frozenset[str], ...],
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

    display_lines = []
    display_widths = []
    roads_list = []
    for road in geometry.roads:
        centerline = LineString(line_points(road.centerline))
        if not road.is_main_route:
            centerline = _fit_context_display_length(
                centerline, CONTEXT_ROAD_DISPLAY_LENGTH
            )
        display_width = max(road.road_width_metres * scale, 3.0)
        half_width = display_width / 2.0
        left_edge = _longest_line(
            centerline.offset_curve(half_width, join_style="round")
        )
        right_edge = _longest_line(
            centerline.offset_curve(-half_width, join_style="round")
        )
        if left_edge is None or right_edge is None:
            # The road surface still renders correctly; retain a safe editable
            # centerline instead of failing the whole schematic.
            left_edge = left_edge or centerline
            right_edge = right_edge or centerline
        visible_name = road.route_name if not road.route_name.startswith("Unnamed") else ""
        roads_list.append(
            SchematicRoad(
                tuple(centerline.coords),
                tuple(left_edge.coords),
                tuple(right_edge.coords),
                road.is_main_route,
                visible_name,
                tuple(centerline.coords[-1]) if visible_name and not road.is_main_route else None,
            )
        )
        display_lines.append(centerline)
        display_widths.append(display_width)
    roads = tuple(roads_list)
    road_surface = unary_union([
        line.buffer(width / 2.0, cap_style="flat", join_style="round")
        for line, width in zip(display_lines, display_widths, strict=True)
    ])
    boundaries = tuple(
        tuple(line.coords)
        for line in _open_display_road_boundaries(road_surface, display_lines, display_widths)
    )

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
            projected.pole.installed_quantity,
            _physical_kind(projected.pole.number, transformer_rack_groups),
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
                pole.installed_quantity,
                pole.physical_kind,
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


def _fit_context_display_length(line: LineString, target_length: float) -> LineString:
    """Keep context roads readable without letting them dominate the page."""
    if line.length <= 1e-9:
        return line
    if line.length > target_length:
        midpoint = line.length / 2.0
        half_length = target_length / 2.0
        clipped = substring(line, midpoint - half_length, midpoint + half_length)
        return clipped if isinstance(clipped, LineString) else line
    if line.length == target_length:
        return line
    coordinates = list(line.coords)
    start_x, start_y = coordinates[0]
    end_x, end_y = coordinates[-1]
    dx, dy = end_x - start_x, end_y - start_y
    chord = max((dx * dx + dy * dy) ** 0.5, 1e-9)
    extension = (target_length - line.length) / 2.0
    unit_x, unit_y = dx / chord, dy / chord
    coordinates[0] = (start_x - unit_x * extension, start_y - unit_y * extension)
    coordinates[-1] = (end_x + unit_x * extension, end_y + unit_y * extension)
    return LineString(coordinates)


def _longest_line(geometry) -> LineString | None:
    """Return a stable LineString when an offset splits into multiple parts."""
    if geometry.is_empty:
        return None
    if isinstance(geometry, LineString):
        return geometry
    parts = [part for part in geometry.geoms if isinstance(part, LineString) and not part.is_empty]
    return max(parts, key=lambda part: part.length, default=None)


def _open_display_road_boundaries(road_surface, lines, widths):
    """Remove exposed end caps after context roads are lengthened for display."""
    cap_lines = []
    for line, width in zip(lines, widths, strict=True):
        half_width = width / 2.0
        left = _longest_line(line.offset_curve(half_width, join_style="round"))
        right = _longest_line(line.offset_curve(-half_width, join_style="round"))
        if left is None or right is None:
            continue
        cap_lines.extend((
            LineString((left.coords[0], right.coords[0])),
            LineString((left.coords[-1], right.coords[-1])),
        ))
    tolerance = max(min(widths) * 0.02, 0.01)
    opened = road_surface.boundary.difference(unary_union(cap_lines).buffer(tolerance))
    return list(opened.geoms) if hasattr(opened, "geoms") else [opened]


def _marker_id(number: str, groups: tuple[frozenset[str], ...]) -> str:
    for index, group in enumerate(groups, start=1):
        if number in group:
            return f"same-pole-{index}"
    return number


def _physical_kind(number: str, transformer_rack_groups: tuple[frozenset[str], ...]) -> str:
    return "transformer_rack" if any(number in group for group in transformer_rack_groups) else "single"
