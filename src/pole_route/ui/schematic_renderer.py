"""Render editable Qt objects for a non-scale schematic."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from pole_route.domain.pole import PoleSide
from pole_route.domain.schematic import SchematicLayout

EDITABLE_FLAGS = (
    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
)


def render_schematic(scene: QGraphicsScene, layout: SchematicLayout) -> None:
    """Replace the scene with individually editable schematic objects."""
    scene.clear()
    road_group = QGraphicsItemGroup()
    road_group.setData(0, "road")
    road_group.setFlags(EDITABLE_FLAGS)
    road_pen = QPen(QColor("#d0d0d0"), 3)
    center_pen = QPen(QColor("#6fa8dc"), 2, Qt.PenStyle.DashLine)
    for y, pen in (
        (layout.road_top, road_pen),
        ((layout.road_top + layout.road_bottom) / 2, center_pen),
        (layout.road_bottom, road_pen),
    ):
        road_line = QGraphicsLineItem(layout.road_left, y, layout.road_right, y)
        road_line.setPen(pen)
        road_group.addToGroup(road_line)
    scene.addItem(road_group)

    for pole in layout.poles:
        color = QColor("#27ae60" if pole.side is PoleSide.LEFT else "#eb5757")
        pole_item = QGraphicsEllipseItem(-7, -7, 14, 14)
        pole_item.setData(0, "pole")
        pole_item.setData(1, pole.number)
        pole_item.setPos(pole.x, pole.y)
        pole_item.setPen(QPen(color, 2))
        pole_item.setBrush(QBrush(QColor("#202020")))
        pole_item.setFlags(EDITABLE_FLAGS)
        pole_item.setToolTip(
            f"Pole {pole.number}\nSide: {pole.side.value}\n"
            f"Source station: {pole.source_station_metres:.2f} m"
        )
        scene.addItem(pole_item)

        label_text = pole.number + (f"  {pole.detail}" if pole.detail else "")
        label = QGraphicsSimpleTextItem(label_text)
        label.setData(0, "label")
        label.setData(1, pole.number)
        label.setBrush(QBrush(color))
        label.setFlags(EDITABLE_FLAGS)
        label_offset_y = -34 if pole.side is PoleSide.LEFT else 16
        label.setPos(pole.x + 10, pole.y + label_offset_y)
        scene.addItem(label)

    scene.setSceneRect(0, 0, layout.width, layout.height)
