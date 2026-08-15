"""Export metric road geometry as an editable AutoCAD DXF drawing."""

from __future__ import annotations

from math import atan2, degrees
from pathlib import Path

import ezdxf
from ezdxf import units
from shapely.geometry import GeometryCollection, LineString, MultiLineString
from shapely.ops import nearest_points, unary_union

from pole_route.domain.route import RouteType
from pole_route.geometry.road_geometry import RoadNetworkGeometry


class DxfExportError(RuntimeError):
    """The metric geometry cannot be written as DXF."""


LAYERS = (
    ("MAIN_CENTERLINE", 8, "DASHED"),
    ("MAIN_ROAD_EDGE", 7, "CONTINUOUS"),
    ("CROSS_CENTERLINE", 1, "DASHED"),
    ("CROSS_ROAD_EDGE", 1, "CONTINUOUS"),
    ("T_CENTERLINE", 30, "DASHED"),
    ("T_ROAD_EDGE", 30, "CONTINUOUS"),
    ("SOI_CENTERLINE", 8, "DASHED"),
    ("SOI_EDGE", 9, "CONTINUOUS"),
    ("POLE_OFFSET", 3, "DASHED"),
    ("POLES", 1, "CONTINUOUS"),
    ("POLE_LABELS", 7, "CONTINUOUS"),
    ("ROAD_LABELS", 7, "CONTINUOUS"),
)


def export_geometry_to_dxf(geometry: RoadNetworkGeometry, path: str | Path) -> int:
    """Write real metric geometry, Unicode labels, CAD layers, and pole blocks."""
    if not geometry.roads:
        raise DxfExportError("There is no road geometry to export.")

    document = ezdxf.new("R2010", setup=True)
    document.units = units.M
    if "THAI" not in document.styles:
        document.styles.add("THAI", font="tahoma.ttf")
    for name, color, line_type in LAYERS:
        if name not in document.layers:
            document.layers.add(name, color=color, linetype=line_type)

    pole_block = document.blocks.new("POLE_1M")
    pole_block.add_lwpolyline(
        ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)),
        close=True,
        dxfattribs={"layer": "POLES"},
    )
    modelspace = document.modelspace()
    main_corridors = [
        road.centerline.buffer(road.road_width_metres / 2.0, cap_style="flat")
        for road in geometry.roads
        if road.is_main_route
    ]
    main_corridor = unary_union(main_corridors) if main_corridors else None

    export_roads = _deduplicate_context_roads(geometry)
    labelled_roads: set[str] = set()
    object_count = 0
    for road in export_roads:
        center_layer, edge_layer = _road_layers(road)
        _add_dxf_line(modelspace, center_layer, road.centerline)
        object_count += 1
        for edge in (road.left_edge, road.right_edge):
            visible = (
                edge
                if road.is_main_route or main_corridor is None
                else edge.difference(main_corridor.buffer(0.02))
            )
            for part in _line_parts(visible):
                _add_dxf_line(modelspace, edge_layer, part)
                object_count += 1
        if road.pole_line_enabled:
            _add_dxf_line(modelspace, "POLE_OFFSET", road.left_pole_line)
            _add_dxf_line(modelspace, "POLE_OFFSET", road.right_pole_line)
            object_count += 2
        normalized_name = _normalized_road_name(road.route_name)
        if normalized_name and normalized_name not in labelled_roads:
            labelled_roads.add(normalized_name)
            midpoint = road.centerline.interpolate(road.centerline.length / 2.0)
            _add_dxf_text(
                modelspace, "ROAD_LABELS", midpoint.x, midpoint.y, road.route_name, 2.5
            )
            object_count += 1

    rendered_poles: set[tuple[float, float]] = set()
    for projected in geometry.projected_poles:
        position = (round(projected.snapped.x, 3), round(projected.snapped.y, 3))
        if position not in rendered_poles:
            rendered_poles.add(position)
            road = geometry.roads[projected.route_index]
            rotation = _line_angle(road.centerline, road.centerline.project(projected.snapped))
            modelspace.add_blockref(
                "POLE_1M",
                (projected.snapped.x, projected.snapped.y),
                dxfattribs={"layer": "POLES", "rotation": rotation},
            )
            object_count += 1
        label = projected.pole.number
        if projected.pole.detail:
            label += f"  {projected.pole.detail}"
        _add_dxf_text(
            modelspace,
            "POLE_LABELS",
            projected.snapped.x + 1.5,
            projected.snapped.y + 1.5,
            label,
            1.8,
        )
        object_count += 1

    try:
        document.saveas(Path(path))
    except (OSError, ezdxf.DXFError) as error:
        raise DxfExportError(f"DXF could not be saved: {error}") from error
    return object_count


def _add_dxf_line(modelspace, layer: str, line: LineString) -> None:
    if len(line.coords) >= 2:
        modelspace.add_lwpolyline(line.coords, dxfattribs={"layer": layer})


def _add_dxf_text(
    modelspace, layer: str, x: float, y: float, value: str, height: float
) -> None:
    modelspace.add_text(
        value,
        height=height,
        dxfattribs={"layer": layer, "style": "THAI"},
    ).set_placement((x, y))


def _deduplicate_context_roads(geometry: RoadNetworkGeometry):
    """Collapse split OSM carriageways at the same named junction for CAD."""
    main_roads = [road for road in geometry.roads if road.is_main_route]
    manual_roads = [
        road
        for road in geometry.roads
        if road.route_type in {RouteType.CROSS_ROAD, RouteType.T_JUNCTION}
    ]
    context_roads = [
        road
        for road in geometry.roads
        if not road.is_main_route and road not in manual_roads
    ]
    if not main_roads:
        return tuple(geometry.roads)
    main_axis = unary_union([road.centerline for road in main_roads])
    accepted = []
    junctions: list[tuple[str, object]] = []
    for road in context_roads:
        anchor, _ = nearest_points(main_axis, road.centerline)
        if any(
            anchor.distance(nearest_points(main_axis, manual.centerline)[0])
            <= max(12.0, manual.road_width_metres / 2.0 + 5.0)
            for manual in manual_roads
        ):
            continue
        name = _normalized_road_name(road.route_name)
        duplicate_distance = 12.0 if name else 6.0
        if any(
            existing_name == name and anchor.distance(existing_anchor) <= duplicate_distance
            for existing_name, existing_anchor in junctions
        ):
            continue
        junctions.append((name, anchor))
        accepted.append(road)
    return tuple(main_roads + manual_roads + accepted)


def _road_layers(road) -> tuple[str, str]:
    if road.route_type is RouteType.MAIN_ROUTE:
        return "MAIN_CENTERLINE", "MAIN_ROAD_EDGE"
    if road.route_type is RouteType.CROSS_ROAD:
        return "CROSS_CENTERLINE", "CROSS_ROAD_EDGE"
    if road.route_type is RouteType.T_JUNCTION:
        return "T_CENTERLINE", "T_ROAD_EDGE"
    return "SOI_CENTERLINE", "SOI_EDGE"


def _normalized_road_name(value: str) -> str:
    name = value.strip()
    return "" if not name or name.startswith("Unnamed") else name.casefold()


def _line_parts(geometry) -> tuple[LineString, ...]:
    if isinstance(geometry, LineString):
        return (geometry,) if geometry.length > 0 else ()
    if isinstance(geometry, (MultiLineString, GeometryCollection)):
        return tuple(
            part
            for child in geometry.geoms
            for part in _line_parts(child)
            if part.length > 0
        )
    return ()


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


def _add_polyline(add, layer: str, points, closed: bool = False) -> None:
    points = tuple(points)
    if len(points) < 2:
        return
    add(0, "POLYLINE")
    add(8, layer)
    add(66, 1)
    add(10, 0.0)
    add(20, 0.0)
    add(30, 0.0)
    add(70, 1 if closed else 0)
    for x, y in points:
        add(0, "VERTEX")
        add(8, layer)
        add(10, float(x))
        add(20, float(y))
        add(30, 0.0)
    add(0, "SEQEND")
    add(8, layer)


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
