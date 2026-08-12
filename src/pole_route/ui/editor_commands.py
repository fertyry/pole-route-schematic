"""Undoable commands and move-aware schematic graphics items."""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
)


class MoveItemCommand(QUndoCommand):
    def __init__(self, item: QGraphicsItem, before: QPointF, after: QPointF) -> None:
        super().__init__(f"Move {item.data(0) or 'object'}")
        self.item = item
        self.before = QPointF(before)
        self.after = QPointF(after)
        self._first_redo = True

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        self.item.setPos(self.after)

    def undo(self) -> None:
        self.item.setPos(self.before)


class DeleteItemsCommand(QUndoCommand):
    def __init__(self, scene: QGraphicsScene, items: list[QGraphicsItem]) -> None:
        super().__init__(f"Delete {len(items)} object(s)")
        self.scene = scene
        self.items = items

    def redo(self) -> None:
        for item in self.items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)

    def undo(self) -> None:
        for item in self.items:
            if item.scene() is None:
                self.scene.addItem(item)
                item.setSelected(True)


class ResetLayoutCommand(QUndoCommand):
    def __init__(self, items: list[QGraphicsItem]) -> None:
        super().__init__("Reset layout")
        self.positions = [(item, QPointF(item.pos()), QPointF(item.data(2))) for item in items]

    def redo(self) -> None:
        for item, _current, initial in self.positions:
            item.setPos(initial)

    def undo(self) -> None:
        for item, current, _initial in self.positions:
            item.setPos(current)


class _MoveTrackingMixin:
    undo_stack: QUndoStack
    _drag_start: QPointF | None

    def _initialize_move_tracking(self, undo_stack: QUndoStack) -> None:
        self.undo_stack = undo_stack
        self._drag_start = None

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._drag_start = QPointF(self.pos())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._drag_start is not None and self.pos() != self._drag_start:
            self.undo_stack.push(MoveItemCommand(self, self._drag_start, self.pos()))
        self._drag_start = None


class EditableEllipseItem(_MoveTrackingMixin, QGraphicsEllipseItem):
    def __init__(self, *args, undo_stack: QUndoStack) -> None:
        super().__init__(*args)
        self._initialize_move_tracking(undo_stack)


class EditableTextItem(_MoveTrackingMixin, QGraphicsSimpleTextItem):
    def __init__(self, text: str, undo_stack: QUndoStack) -> None:
        super().__init__(text)
        self._initialize_move_tracking(undo_stack)


class EditableItemGroup(_MoveTrackingMixin, QGraphicsItemGroup):
    def __init__(self, undo_stack: QUndoStack) -> None:
        super().__init__()
        self._initialize_move_tracking(undo_stack)


def editable_scene_items(scene: QGraphicsScene) -> list[QGraphicsItem]:
    """Return top-level editor objects, excluding grouped road children."""
    return [
        item
        for item in scene.items()
        if item.parentItem() is None and item.data(0) in {"road", "pole", "label", "drawing"}
    ]

