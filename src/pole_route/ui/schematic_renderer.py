"""Render editable Qt objects for a non-scale schematic."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
)

from pole_route.domain.pole import PoleSide
from pole_route.domain.schematic import SchematicLayout
from pole_route.ui.editor_commands import EditableItemGroup, EditableRectItem, EditableTextItem

EDITABLE_FLAGS = (
    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
)


def render_schematic(scene: QGraphicsScene, layout: SchematicLayout, undo_stack: QUndoStack) -> None:
    """Replace the scene with individually editable schematic objects."""
    scene.clear()
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
            pole_item = EditableRectItem(-7, -7, 14, 14, undo_stack=undo_stack)
            pole_item.setData(0, "pole")
            pole_item.setData(1, marker_id)
            pole_item.setPos(pole.x, pole.y)
            pole_item.setTransformOriginPoint(pole_item.boundingRect().center())
            pole_item.setRotation(pole.road_angle_degrees)
            pole_item.setData(2, pole_item.pos())
            pole_item.setPen(QPen(color, 2))
            pole_item.setBrush(QBrush(QColor("#202020")))
            pole_item.setFlags(EDITABLE_FLAGS)
            pole_item.setToolTip(
                f"Physical pole: {marker_id}\nSide: {pole.side.value}\n"
                f"Source station: {pole.source_station_metres:.2f} m"
            )
            scene.addItem(pole_item)

        label_text = pole.number + (f"  {pole.detail}" if pole.detail else "")
        label = EditableTextItem(label_text, undo_stack)
        label.setData(0, "label")
        label.setData(1, pole.number)
        label.setBrush(QBrush(color))
        label.setFlags(EDITABLE_FLAGS)
        label_offset_y = -34 if pole.side is PoleSide.LEFT else 16
        label.setPos(pole.x + 10, pole.y + label_offset_y)
        label.setData(2, label.pos())
        scene.addItem(label)

    scene.setSceneRect(0, 0, layout.width, layout.height)
