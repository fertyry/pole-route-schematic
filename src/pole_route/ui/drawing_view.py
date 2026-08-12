"""Interactive schematic canvas drawing modes."""

from enum import StrEnum
from math import atan2, cos, hypot, pi, sin

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView, QInputDialog

from pole_route.domain.blocks import BlockType
from pole_route.ui.block_renderer import create_block_item
from pole_route.ui.editor_commands import (
    AddItemCommand,
    EditableEllipseItem,
    EditableLineItem,
    EditableRectItem,
    EditableTextItem,
)
from pole_route.ui.schematic_renderer import EDITABLE_FLAGS


class DrawingMode(StrEnum):
    SELECT = "select"
    LINE = "line"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    TEXT = "text"
    BLOCK = "block"


class DrawingView(QGraphicsView):
    """A graphics view that creates basic undoable drawing objects."""

    modeChanged = Signal(str)

    def __init__(self, scene, undo_stack: QUndoStack, parent=None) -> None:
        super().__init__(scene, parent)
        self.undo_stack = undo_stack
        self.mode = DrawingMode.SELECT
        self._start: QPointF | None = None
        self._preview: QGraphicsItem | None = None
        self.line_color = QColor("#f2c94c")
        self.line_width = 2.0
        self.block_type = BlockType.SIDE_ROAD
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def set_mode(self, mode: DrawingMode) -> None:
        self._discard_preview()
        self.mode = mode
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if mode is DrawingMode.SELECT
            else QGraphicsView.DragMode.NoDrag
        )
        self.setCursor(
            Qt.CursorShape.ArrowCursor
            if mode is DrawingMode.SELECT
            else Qt.CursorShape.CrossCursor
        )
        self.modeChanged.emit(mode.value)

    def set_block_mode(self, block_type: BlockType) -> None:
        self.block_type = block_type
        self.set_mode(DrawingMode.BLOCK)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.mode is DrawingMode.SELECT or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        if self.mode is DrawingMode.BLOCK and not (
            event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            point = nearest_road_point(self.scene(), point, 28.0) or point
        if self.mode is DrawingMode.TEXT:
            self._add_text(point)
            return
        self._start = point
        preview_end = QPointF(point.x() + 1, point.y()) if self.mode is DrawingMode.BLOCK else point
        self._preview = self._new_shape(point, preview_end)
        self.scene().addItem(self._preview)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start is None or self._preview is None:
            super().mouseMoveEvent(event)
            return
        end = self.mapToScene(event.position().toPoint())
        if self.mode is DrawingMode.LINE and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            end = snap_line_endpoint(self._start, end)
        if self.mode is DrawingMode.BLOCK:
            self.scene().removeItem(self._preview)
            self._preview = create_block_item(self.block_type, self._start, end, self.undo_stack)
            self.scene().addItem(self._preview)
        else:
            self._update_shape(self._preview, self._start, end)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._start is None or self._preview is None:
            super().mouseReleaseEvent(event)
            return
        end = self.mapToScene(event.position().toPoint())
        if self.mode is DrawingMode.LINE and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            end = snap_line_endpoint(self._start, end)
        start = QPointF(self._start)
        if self.mode is DrawingMode.BLOCK:
            self.scene().removeItem(self._preview)
            item = create_block_item(self.block_type, start, end, self.undo_stack)
            self.scene().addItem(item)
        else:
            self._update_shape(self._preview, start, end)
            item = self._preview
        self._start = None
        self._preview = None
        if QPointF(end - start).manhattanLength() < 3:
            self.scene().removeItem(item)
            return
        self._finish_item(item)

    def _new_shape(self, start: QPointF, end: QPointF) -> QGraphicsItem:
        pen = QPen(self.line_color, self.line_width)
        if self.mode is DrawingMode.BLOCK:
            return create_block_item(self.block_type, start, end, self.undo_stack)
        if self.mode is DrawingMode.LINE:
            item = EditableLineItem(start.x(), start.y(), end.x(), end.y(), undo_stack=self.undo_stack)
        elif self.mode is DrawingMode.RECTANGLE:
            item = EditableRectItem(QRectF(start, end).normalized(), undo_stack=self.undo_stack)
        else:
            item = EditableEllipseItem(QRectF(start, end).normalized(), undo_stack=self.undo_stack)
        item.setPen(pen)
        if hasattr(item, "setBrush"):
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def _update_shape(self, item: QGraphicsItem, start: QPointF, end: QPointF) -> None:
        if self.mode is DrawingMode.BLOCK:
            self.scene().removeItem(item)
            self._preview = create_block_item(self.block_type, start, end, self.undo_stack)
            self.scene().addItem(self._preview)
            return
        if isinstance(item, EditableLineItem):
            item.setLine(start.x(), start.y(), end.x(), end.y())
        else:
            item.setRect(QRectF(start, end).normalized())

    def _shape_origin(self, item: QGraphicsItem) -> QPointF:
        if isinstance(item, EditableLineItem):
            return item.line().p1()
        return item.rect().topLeft()

    def _start_point_for_finished(self, item: QGraphicsItem) -> QPointF:
        if item.data(0) == "block":
            start_x, start_y = item.data(3)
            return QPointF(start_x, start_y)
        return self._shape_origin(item)

    def _add_text(self, point: QPointF) -> None:
        text, accepted = QInputDialog.getText(self, "Add text", "Text")
        if not accepted or not text.strip():
            return
        item = EditableTextItem(text.strip(), self.undo_stack)
        item.setBrush(QBrush(self.line_color))
        item.setPos(point)
        self.scene().addItem(item)
        self._finish_item(item)

    def _finish_item(self, item: QGraphicsItem) -> None:
        if not item.data(0):
            item.setData(0, "drawing")
        item.setData(2, item.pos())
        item.setFlags(EDITABLE_FLAGS)
        item.setSelected(True)
        self.undo_stack.push(AddItemCommand(self.scene(), item))

    def _discard_preview(self) -> None:
        if self._preview is not None and self._preview.scene() is self.scene():
            self.scene().removeItem(self._preview)
        self._start = None
        self._preview = None


def snap_line_endpoint(start: QPointF, end: QPointF, increment_degrees: float = 45.0) -> QPointF:
    """Preserve drag length while snapping its angle to a fixed increment."""
    delta_x = end.x() - start.x()
    delta_y = end.y() - start.y()
    length = hypot(delta_x, delta_y)
    if length == 0:
        return QPointF(end)
    increment = increment_degrees * pi / 180.0
    angle = round(atan2(delta_y, delta_x) / increment) * increment
    return QPointF(start.x() + cos(angle) * length, start.y() + sin(angle) * length)


def nearest_road_point(scene, point: QPointF, maximum_distance: float) -> QPointF | None:
    """Find the closest projected point on the generated main-road lines."""
    closest: QPointF | None = None
    closest_distance = maximum_distance
    for road in (item for item in scene.items() if item.data(0) == "road"):
        for child in road.childItems():
            if not hasattr(child, "line"):
                continue
            line = child.line()
            start = child.mapToScene(line.p1())
            end = child.mapToScene(line.p2())
            candidate = _project_to_segment(point, start, end)
            distance = hypot(candidate.x() - point.x(), candidate.y() - point.y())
            if distance < closest_distance:
                closest, closest_distance = candidate, distance
    return closest


def _project_to_segment(point: QPointF, start: QPointF, end: QPointF) -> QPointF:
    delta_x = end.x() - start.x()
    delta_y = end.y() - start.y()
    denominator = delta_x * delta_x + delta_y * delta_y
    if denominator == 0:
        return QPointF(start)
    ratio = (
        (point.x() - start.x()) * delta_x + (point.y() - start.y()) * delta_y
    ) / denominator
    ratio = max(0.0, min(1.0, ratio))
    return QPointF(start.x() + ratio * delta_x, start.y() + ratio * delta_y)
