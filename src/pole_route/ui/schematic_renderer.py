"""Render editable Qt objects for a non-scale schematic."""

from math import cos, radians, sin

from PySide6.QtCore import QLineF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
)
from shapely.geometry import Point

from pole_route.domain.pole import PoleSide
from pole_route.domain.schematic import SchematicLayout
from pole_route.domain.context import ContextFeature
from pole_route.geometry.road_geometry import RoadNetworkGeometry
from pole_route.ui.osm_feature_renderer import render_osm_features
from pole_route.ui.editor_commands import EditableItemGroup, EditableRectItem, EditableTextItem
from pole_route.ui.scene_lifecycle import clear_scene, retain_scene_items

EDITABLE_FLAGS = (
    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
)


def render_schematic(
    scene: QGraphicsScene,
    layout: SchematicLayout,
    undo_stack: QUndoStack,
    osm_features: tuple[ContextFeature, ...] = (),
    geometry: RoadNetworkGeometry | None = None,
) -> None:
    """Replace the scene with individually editable schematic objects."""
    clear_scene(scene)
    if osm_features and geometry is not None:
        project = (
            _network_osm_projector(layout, geometry)
            if layout.roads
            else _straight_osm_projector(layout, geometry, osm_features)
        )
        render_osm_features(scene, osm_features, project)
    road_group = EditableItemGroup(undo_stack)
    road_group.setData(0, "road")
    road_group.setFlags(EDITABLE_FLAGS)
    road_group.setData(2, road_group.pos())
    road_pen = QPen(QColor("#d0d0d0"), 3)
    center_pen = QPen(QColor("#6fa8dc"), 2, Qt.PenStyle.DashLine)
    if layout.roads:
        if layout.road_boundaries:
            for points in layout.road_boundaries:
                path = QPainterPath()
                path.moveTo(*points[0])
                for point in points[1:]:
                    path.lineTo(*point)
                road_group.addToGroup(scene.addPath(path, road_pen))
        for road_index, road in enumerate(layout.roads):
            road_parts = (
                ((road.centerline, center_pen),)
                if layout.road_boundaries
                else (
                    (road.left_edge, road_pen),
                    (road.centerline, center_pen),
                    (road.right_edge, road_pen),
                )
            )
            for points, pen in road_parts:
                path = QPainterPath()
                path.moveTo(*points[0])
                for point in points[1:]:
                    path.lineTo(*point)
                road_line = scene.addPath(path, pen)
                if points is road.centerline:
                    if road.is_main_route:
                        road_line.setData(5, "main_centerline")
                        road_line.setData(6, f"main-{road_index}")
                    elif road.name:
                        road_line.setData(6, road.name)
                road_group.addToGroup(road_line)
    else:
        for y, pen in (
            (layout.road_top, road_pen),
            ((layout.road_top + layout.road_bottom) / 2, center_pen),
            (layout.road_bottom, road_pen),
        ):
            road_line = QGraphicsLineItem(layout.road_left, y, layout.road_right, y)
            road_line.setPen(pen)
            road_group.addToGroup(road_line)
    scene.addItem(road_group)

    rendered_road_names: set[str] = set()
    for road in layout.roads:
        if (
            not road.name
            or road.label_position is None
            or road.name in rendered_road_names
        ):
            continue
        rendered_road_names.add(road.name)
        road_name = EditableTextItem(road.name, undo_stack)
        road_name.setData(0, "road_name")
        road_name.setData(1, road.name)
        road_name.setBrush(QBrush(QColor("#d0d0d0")))
        road_name.setFlags(EDITABLE_FLAGS)
        road_name.setRotation(0.0)
        road_name.setPos(road.label_position[0] + 6, road.label_position[1] - 18)
        road_name.setData(2, road_name.pos())
        scene.addItem(road_name)

    rendered_markers: set[str] = set()
    for pole in layout.poles:
        color = QColor("#27ae60" if pole.side is PoleSide.LEFT else "#eb5757")
        marker_id = pole.marker_id or pole.number
        if marker_id not in rendered_markers:
            rendered_markers.add(marker_id)
            marker_count = 2 if pole.physical_kind == "transformer_rack" else 1
            angle = radians(pole.road_angle_degrees)
            offsets = (-12.0, 12.0) if marker_count == 2 else (0.0,)
            positions = []
            for marker_index, offset in enumerate(offsets, start=1):
                x = pole.x + cos(angle) * offset
                y = pole.y + sin(angle) * offset
                positions.append((x, y))
                pole_item = EditableRectItem(-7, -7, 14, 14, undo_stack=undo_stack)
                pole_item.setData(0, "pole")
                pole_item.setData(1, marker_id)
                pole_item.setData(8, pole.physical_kind)
                pole_item.setPos(x, y)
                pole_item.setTransformOriginPoint(pole_item.boundingRect().center())
                pole_item.setRotation(pole.road_angle_degrees)
                pole_item.setData(2, pole_item.pos())
                pole_item.setPen(QPen(color, 2))
                pole_item.setBrush(QBrush(QColor("#202020")))
                pole_item.setFlags(EDITABLE_FLAGS)
                pole_item.setToolTip(
                    f"Physical pole: {marker_id} ({marker_index}/{marker_count})\n"
                    f"Side: {pole.side.value}\nSource station: {pole.source_station_metres:.2f} m"
                )
                scene.addItem(pole_item)
            if marker_count == 2:
                rack = QGraphicsLineItem(QLineF(*positions[0], *positions[1]))
                rack.setData(0, "transformer_rack")
                rack.setData(1, marker_id)
                rack.setPen(QPen(color, 3))
                scene.addItem(rack)

        label_text = pole.number + (f"  {pole.detail}" if pole.detail else "")
        label = EditableTextItem(label_text, undo_stack)
        label.setData(0, "label")
        label.setData(1, pole.number)
        label.setData(7, pole.installed_quantity)
        label.setBrush(QBrush(color))
        label.setFlags(EDITABLE_FLAGS)
        label_offset_y = -34 if pole.side is PoleSide.LEFT else 16
        label.setPos(pole.x + 10, pole.y + label_offset_y)
        label.setData(2, label.pos())
        scene.addItem(label)

    scene.setSceneRect(0, 0, layout.width, layout.height)
    retain_scene_items(scene)


def _network_osm_projector(layout, geometry):
    coordinates = [
        coordinate
        for road in geometry.roads
        for line in (road.centerline, road.left_edge, road.right_edge)
        for coordinate in line.coords
    ]
    min_x = min(x for x, _y in coordinates)
    max_x = max(x for x, _y in coordinates)
    min_y = min(y for _x, y in coordinates)
    max_y = max(y for _x, y in coordinates)
    margin = 120.0
    scale = min(
        (layout.width - 2 * margin) / max(max_x - min_x, 1e-9),
        (layout.height - 2 * margin) / max(max_y - min_y, 1e-9),
    )

    def project(point):
        x, y = geometry.projection.to_metric(point)
        return margin + (x - min_x) * scale, margin + (max_y - y) * scale

    return project


def _straight_osm_projector(layout, geometry, features):
    """Place context by main-route station and signed lateral distance."""
    main = next((road for road in geometry.roads if road.is_main_route), geometry.roads[0])
    center_y = (layout.road_top + layout.road_bottom) / 2.0
    metric_points = [
        geometry.projection.to_metric(point)
        for feature in features
        for part in feature.parts
        for ring in (part.coordinates, *part.holes)
        for point in ring
    ]

    def station_and_offset(x, y):
        source = Point(x, y)
        station = main.centerline.project(source)
        nearest = main.centerline.interpolate(station)
        delta = min(max(main.centerline.length * 1e-6, 0.01), 1.0)
        before = main.centerline.interpolate(max(0.0, station - delta))
        after = main.centerline.interpolate(min(main.centerline.length, station + delta))
        cross = (after.x - before.x) * (y - nearest.y) - (after.y - before.y) * (x - nearest.x)
        return station, source.distance(nearest) * (1.0 if cross >= 0 else -1.0)

    offsets = [abs(station_and_offset(x, y)[1]) for x, y in metric_points]
    available = max(min(center_y - 20.0, layout.height - center_y - 20.0), 1.0)
    lateral_scale = min(2.0, available / max(offsets, default=1.0))

    def project(point):
        station, offset = station_and_offset(*geometry.projection.to_metric(point))
        x = layout.road_left + station / max(main.centerline.length, 1e-9) * (
            layout.road_right - layout.road_left
        )
        return x, center_y - offset * lateral_scale

    return project
