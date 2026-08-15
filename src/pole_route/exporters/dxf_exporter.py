"""Export metric road geometry as an editable AutoCAD DXF drawing."""

from __future__ import annotations

from math import atan2, degrees
from pathlib import Path

from shapely.geometry import LineString

from pole_route.geometry.road_geometry import RoadNetworkGeometry


class DxfExportError(RuntimeError):
    """The metric geometry cannot be written as DXF."""


LAYERS = (
    ("MAIN_CENTERLINE", 8, "DASHED"),
    ("ROAD_EDGE", 7, "CONTINUOUS"),
    ("CONTEXT_ROAD", 9, "CONTINUOUS"),
    ("POLE_OFFSET", 3, "DASHED"),
    ("POLES", 1, "CONTINUOUS"),
    ("LABELS", 7, "CONTINUOUS"),
)


def export_geometry_to_dxf(geometry: RoadNetworkGeometry, path: str | Path) -> int:
    """Write real metric geometry, CAD layers, and reusable pole blocks."""
    if not geometry.roads:
        raise DxfExportError("There is no road geometry to export.")

    pairs: list[tuple[int, object]] = []

    def add(code: int, value: object) -> None:
        pairs.append((code, value))

    add(0, "SECTION")
    add(2, "HEADER")
    add(9, "$ACADVER")
    add(1, "AC1021")
    add(9, "$INSUNITS")
    add(70, 6)  # metres
    add(0, "ENDSEC")

    add(0, "SECTION")
    add(2, "TABLES")
    add(0, "TABLE")
    add(2, "LTYPE")
    add(70, 2)
    _add_linetype(add, "CONTINUOUS", ())
    _add_linetype(add, "DASHED", (0.6, -0.3))
    add(0, "ENDTAB")
    add(0, "TABLE")
    add(2, "LAYER")
    add(70, len(LAYERS))
    for name, color, line_type in LAYERS:
        add(0, "LAYER")
        add(2, name)
        add(70, 0)
        add(62, color)
        add(6, line_type)
    add(0, "ENDTAB")
    add(0, "ENDSEC")

    add(0, "SECTION")
    add(2, "BLOCKS")
    add(0, "BLOCK")
    add(8, "POLES")
    add(2, "POLE_1M")
    add(70, 0)
    add(10, 0.0)
    add(20, 0.0)
    add(30, 0.0)
    _add_polyline(add, "POLES", ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)), True)
    add(0, "ENDBLK")
    add(8, "POLES")
    add(0, "ENDSEC")

    add(0, "SECTION")
    add(2, "ENTITIES")
    object_count = 0
    for road in geometry.roads:
        center_layer = "MAIN_CENTERLINE" if road.is_main_route else "CONTEXT_ROAD"
        _add_polyline(add, center_layer, tuple(road.centerline.coords))
        _add_polyline(add, "ROAD_EDGE", tuple(road.left_edge.coords))
        _add_polyline(add, "ROAD_EDGE", tuple(road.right_edge.coords))
        object_count += 3
        if road.pole_line_enabled:
            _add_polyline(add, "POLE_OFFSET", tuple(road.left_pole_line.coords))
            _add_polyline(add, "POLE_OFFSET", tuple(road.right_pole_line.coords))
            object_count += 2
        if road.route_name:
            midpoint = road.centerline.interpolate(road.centerline.length / 2.0)
            _add_text(add, "LABELS", midpoint.x, midpoint.y, road.route_name, 2.5)
            object_count += 1

    rendered_poles: set[tuple[float, float]] = set()
    for projected in geometry.projected_poles:
        position = (round(projected.snapped.x, 3), round(projected.snapped.y, 3))
        if position not in rendered_poles:
            rendered_poles.add(position)
            road = geometry.roads[projected.route_index]
            rotation = _line_angle(road.centerline, road.centerline.project(projected.snapped))
            _add_insert(add, "POLES", "POLE_1M", projected.snapped.x, projected.snapped.y, rotation)
            object_count += 1
        label = projected.pole.number
        if projected.pole.detail:
            label += f"  {projected.pole.detail}"
        _add_text(
            add,
            "LABELS",
            projected.snapped.x + 1.5,
            projected.snapped.y + 1.5,
            label,
            1.8,
        )
        object_count += 1

    add(0, "ENDSEC")
    add(0, "EOF")
    document = "\n".join(f"{code}\n{_format(value)}" for code, value in pairs) + "\n"
    try:
        Path(path).write_text(document, encoding="ascii")
    except OSError as error:
        raise DxfExportError(f"DXF could not be saved: {error}") from error
    return object_count


def _add_linetype(add, name: str, segments: tuple[float, ...]) -> None:
    add(0, "LTYPE")
    add(2, name)
    add(70, 0)
    add(3, name.title())
    add(72, 65)
    add(73, len(segments))
    add(40, sum(abs(value) for value in segments))
    for value in segments:
        add(49, value)
        add(74, 0)


def _add_polyline(add, layer: str, points, closed: bool = False) -> None:
    points = tuple(points)
    if len(points) < 2:
        return
    add(0, "LWPOLYLINE")
    add(8, layer)
    add(90, len(points))
    add(70, 1 if closed else 0)
    for x, y in points:
        add(10, float(x))
        add(20, float(y))


def _add_insert(add, layer: str, name: str, x: float, y: float, rotation: float) -> None:
    add(0, "INSERT")
    add(8, layer)
    add(2, name)
    add(10, x)
    add(20, y)
    add(30, 0.0)
    add(50, rotation)


def _add_text(add, layer: str, x: float, y: float, value: str, height: float) -> None:
    add(0, "TEXT")
    add(8, layer)
    add(10, x)
    add(20, y)
    add(30, 0.0)
    add(40, height)
    add(1, _dxf_text(value))


def _line_angle(line: LineString, station: float) -> float:
    step = max(min(line.length * 0.001, 1.0), 0.01)
    before = line.interpolate(max(0.0, station - step))
    after = line.interpolate(min(line.length, station + step))
    return degrees(atan2(after.y - before.y, after.x - before.x))


def _dxf_text(value: str) -> str:
    return "".join(character if ord(character) < 128 else f"\\U+{ord(character):04X}" for character in value)


def _format(value: object) -> str:
    return f"{value:.9f}" if isinstance(value, float) else str(value)
