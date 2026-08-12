"""Interactive schematic canvas drawing modes."""

from enum import StrEnum
from math import atan2, cos, hypot, pi, sin

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView, QInputDialog

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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.mode is DrawingMode.SELECT or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        if self.mode is DrawingMode.TEXT:
            self._add_text(point)
            return
        self._start = point
        self._preview = self._new_shape(point, point)
        self.scene().addItem(self._preview)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start is None or self._preview is None:
            super().mouseMoveEvent(event)
            return
        end = self.mapToScene(event.position().toPoint())
        if self.mode is DrawingMode.LINE and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            end = snap_line_endpoint(self._start, end)
        self._update_shape(self._preview, self._start, end)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._start is None or self._preview is None:
            super().mouseReleaseEvent(event)
            return
        end = self.mapToScene(event.position().toPoint())
        if self.mode is DrawingMode.LINE and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            end = snap_line_endpoint(self._start, end)
        self._update_shape(self._preview, self._start, end)
        item = self._preview
        self._start = None
        self._preview = None
        if QPointF(end - self._shape_origin(item)).manhattanLength() < 3:
            self.scene().removeItem(item)
            return
        self._finish_item(item)

    def _new_shape(self, start: QPointF, end: QPointF) -> QGraphicsItem:
        pen = QPen(self.line_color, self.line_width)
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
        if isinstance(item, EditableLineItem):
            item.setLine(start.x(), start.y(), end.x(), end.y())
        else:
            item.setRect(QRectF(start, end).normalized())

    def _shape_origin(self, item: QGraphicsItem) -> QPointF:
        if isinstance(item, EditableLineItem):
            return item.line().p1()
        return item.rect().topLeft()

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
