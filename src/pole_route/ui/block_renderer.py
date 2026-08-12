"""Create editable two-point schematic block graphics."""

from math import hypot

from PySide6.QtCore import QLineF, QPointF, Qt
from PySide6.QtGui import QColor, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsLineItem

from pole_route.domain.blocks import BlockType
from pole_route.ui.editor_commands import EditableItemGroup
from pole_route.ui.schematic_renderer import EDITABLE_FLAGS

ROAD_HALF_WIDTH = 18.0


def create_block_item(
    block_type: BlockType,
    start: QPointF,
    end: QPointF,
    undo_stack: QUndoStack,
) -> EditableItemGroup:
    """Build a semantic block group using two scene points."""
    delta_x = end.x() - start.x()
    delta_y = end.y() - start.y()
    length = hypot(delta_x, delta_y)
    if length < 1e-9:
        raise ValueError("Block requires two different points")
    unit_x, unit_y = delta_x / length, delta_y / length
    normal_x, normal_y = -unit_y, unit_x

    group = EditableItemGroup(undo_stack)
    group.setData(0, "block")
    group.setData(1, block_type.value)
    group.setData(3, (start.x(), start.y()))
    group.setData(4, (end.x(), end.y()))
    group.setFlags(EDITABLE_FLAGS)
    road_pen = QPen(QColor("#d0d0d0"), 3)
    detail_pen = QPen(QColor("#f2c94c"), 2)

    if block_type in {BlockType.SIDE_ROAD, BlockType.T_JUNCTION}:
        _add_parallel(group, start, end, normal_x, normal_y, ROAD_HALF_WIDTH, road_pen)
        if block_type is BlockType.T_JUNCTION:
            _add_crossbar(group, end, unit_x, unit_y, normal_x, normal_y, 28, detail_pen)
    elif block_type is BlockType.CROSSROAD:
        opposite = QPointF(start.x() - delta_x, start.y() - delta_y)
        _add_parallel(group, opposite, end, normal_x, normal_y, ROAD_HALF_WIDTH, road_pen)
    elif block_type is BlockType.VEHICLE_BRIDGE:
        _add_parallel(group, start, end, normal_x, normal_y, ROAD_HALF_WIDTH, road_pen)
        _add_crossbar(group, start, unit_x, unit_y, normal_x, normal_y, 26, detail_pen)
        _add_crossbar(group, end, unit_x, unit_y, normal_x, normal_y, 26, detail_pen)
    else:
        _add_line(group, start, end, QPen(QColor("#f2c94c"), 4))
        step_count = max(3, int(length // 28))
        for index in range(step_count + 1):
            ratio = index / step_count
            center = QPointF(start.x() + delta_x * ratio, start.y() + delta_y * ratio)
            _add_crossbar(group, center, unit_x, unit_y, normal_x, normal_y, 12, detail_pen)

    group.setData(2, group.pos())
    group.setToolTip(block_type.value.replace("_", " ").title())
    return group


def _add_parallel(group, start, end, normal_x, normal_y, offset, pen) -> None:
    for sign in (-1, 1):
        shift = QPointF(normal_x * offset * sign, normal_y * offset * sign)
        _add_line(group, start + shift, end + shift, pen)


def _add_crossbar(group, center, unit_x, unit_y, normal_x, normal_y, half_width, pen) -> None:
    del unit_x, unit_y
    start = QPointF(center.x() - normal_x * half_width, center.y() - normal_y * half_width)
    end = QPointF(center.x() + normal_x * half_width, center.y() + normal_y * half_width)
    _add_line(group, start, end, pen)


def _add_line(group, start, end, pen) -> None:
    line = QGraphicsLineItem(QLineF(start, end))
    line.setPen(pen)
    line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    group.addToGroup(line)

