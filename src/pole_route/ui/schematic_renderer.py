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
from pole_route.ui.editor_commands import EditableEllipseItem, EditableItemGroup, EditableTextItem

EDITABLE_FLAGS = (
    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
)


class SchematicRenderError(RuntimeError):
    """The generated layout could not produce a complete editable scene."""


def render_schematic(scene: QGraphicsScene, layout: SchematicLayout, undo_stack: QUndoStack) -> None:
    """Build off-screen, validate, then replace the visible scene atomically."""
    staging = QGraphicsScene()
    _render_schematic(staging, layout, undo_stack)
    top_level_items = [item for item in staging.items() if item.parentItem() is None]
    item_types = {item.data(0) for item in top_level_items}
    required = {"road"}
    if layout.poles:
        required.update({"pole", "label"})
    missing = required - item_types
    if missing:
        raise SchematicRenderError(
            f"Generated scene is missing: {', '.join(sorted(missing))}"
        )

    scene.clear()
    for item in top_level_items:
        staging.removeItem(item)
        scene.addItem(item)
    scene.setSceneRect(0, 0, layout.width, layout.height)


def _render_schematic(
    scene: QGraphicsScene,
    layout: SchematicLayout,
    undo_stack: QUndoStack,
) -> None:
    """Populate a staging scene with editable schematic objects."""
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
        for road in layout.roads:
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

    rendered_markers: set[str] = set()
    for pole in layout.poles:
        color = QColor("#27ae60" if pole.side is PoleSide.LEFT else "#eb5757")
        marker_id = pole.marker_id or pole.number
        if marker_id not in rendered_markers:
            rendered_markers.add(marker_id)
            pole_item = EditableEllipseItem(-7, -7, 14, 14, undo_stack=undo_stack)
            pole_item.setData(0, "pole")
            pole_item.setData(1, marker_id)
            pole_item.setPos(pole.x, pole.y)
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
