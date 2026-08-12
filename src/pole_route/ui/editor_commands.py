"""Undoable commands and move-aware schematic graphics items."""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPen, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsRectItem,
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


class AddItemCommand(QUndoCommand):
    def __init__(self, scene: QGraphicsScene, item: QGraphicsItem) -> None:
        super().__init__(f"Add {item.data(0) or 'object'}")
        self.scene = scene
        self.item = item
        self._first_redo = True

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self.item.scene() is None:
            self.scene.addItem(self.item)

    def undo(self) -> None:
        if self.item.scene() is self.scene:
            self.scene.removeItem(self.item)


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


class RotateItemsCommand(QUndoCommand):
    def __init__(self, items: list[QGraphicsItem], degrees: float) -> None:
        super().__init__(f"Rotate {len(items)} object(s)")
        self.changes = [(item, item.rotation(), degrees) for item in items]

    def redo(self) -> None:
        for item, _before, after in self.changes:
            item.setTransformOriginPoint(item.boundingRect().center())
            item.setRotation(after)

    def undo(self) -> None:
        for item, before, _after in self.changes:
            item.setRotation(before)


class ChangePenCommand(QUndoCommand):
    def __init__(
        self,
        items: list[QGraphicsItem],
        *,
        color: QColor | None = None,
        width: float | None = None,
    ) -> None:
        super().__init__(f"Change appearance of {len(items)} object(s)")
        targets = [target for item in items for target in pen_items(item)]
        self.pen_changes = []
        for target in targets:
            before = QPen(target.pen())
            after = QPen(before)
            if color is not None:
                after.setColor(color)
            if width is not None:
                after.setWidthF(width)
            self.pen_changes.append((target, before, after))
        self.brush_changes = []
        if color is not None:
            for target in brush_items(items):
                before = target.brush()
                after = type(before)(before)
                after.setColor(color)
                self.brush_changes.append((target, before, after))

    def redo(self) -> None:
        for item, _before, after in self.pen_changes:
            item.setPen(after)
        for item, _before, after in self.brush_changes:
            item.setBrush(after)

    def undo(self) -> None:
        for item, before, _after in self.pen_changes:
            item.setPen(before)
        for item, before, _after in self.brush_changes:
            item.setBrush(before)


class ChangeZCommand(QUndoCommand):
    def __init__(self, items: list[QGraphicsItem], step: float) -> None:
        super().__init__(f"Change order of {len(items)} object(s)")
        self.changes = [(item, item.zValue(), item.zValue() + step) for item in items]

    def redo(self) -> None:
        for item, _before, after in self.changes:
            item.setZValue(after)

    def undo(self) -> None:
        for item, before, _after in self.changes:
            item.setZValue(before)


def pen_items(item: QGraphicsItem) -> list[QGraphicsItem]:
    """Return pen-bearing parts of an object without changing its scene structure."""
    candidates = [item, *item.childItems()]
    return [candidate for candidate in candidates if hasattr(candidate, "pen")]


def brush_items(items: list[QGraphicsItem]) -> list[QGraphicsItem]:
    candidates = [candidate for item in items for candidate in (item, *item.childItems())]
    return [
        candidate
        for candidate in candidates
        if hasattr(candidate, "brush") and candidate.brush().style().value != 0
    ]


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


class EditableLineItem(_MoveTrackingMixin, QGraphicsLineItem):
    def __init__(self, *args, undo_stack: QUndoStack) -> None:
        super().__init__(*args)
        self._initialize_move_tracking(undo_stack)


class EditableRectItem(_MoveTrackingMixin, QGraphicsRectItem):
    def __init__(self, *args, undo_stack: QUndoStack) -> None:
        super().__init__(*args)
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
        if item.parentItem() is None
        and item.data(0) in {"road", "pole", "label", "drawing", "block"}
    ]
