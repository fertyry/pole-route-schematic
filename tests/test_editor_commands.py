from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QUndoStack
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSimpleTextItem

from pole_route.ui.editor_commands import (
    ChangePenCommand,
    ChangeZCommand,
    DeleteItemsCommand,
    EditableEllipseItem,
    MoveItemCommand,
    ResetLayoutCommand,
    RotateItemsCommand,
    editable_scene_items,
)
from pole_route.ui.schematic_renderer import EDITABLE_FLAGS


def _item(scene, stack, x, y):
    item = EditableEllipseItem(-5, -5, 10, 10, undo_stack=stack)
    item.setData(0, "pole")
    item.setFlags(EDITABLE_FLAGS)
    item.setPos(x, y)
    item.setData(2, item.pos())
    scene.addItem(item)
    return item


def test_move_command_undoes_and_redoes_position(qapp) -> None:
    scene = QGraphicsScene()
    stack = QUndoStack()
    item = _item(scene, stack, 10, 20)
    item.setPos(80, 90)

    stack.push(MoveItemCommand(item, QPointF(10, 20), QPointF(80, 90)))
    stack.undo()
    assert item.pos() == QPointF(10, 20)
    stack.redo()
    assert item.pos() == QPointF(80, 90)


def test_delete_command_restores_selected_item(qapp) -> None:
    scene = QGraphicsScene()
    stack = QUndoStack()
    item = _item(scene, stack, 10, 20)

    stack.push(DeleteItemsCommand(scene, [item]))
    assert item.scene() is None
    stack.undo()
    assert item.scene() is scene
    assert item.isSelected()
    stack.redo()
    assert item.scene() is None


def test_reset_layout_is_undoable(qapp) -> None:
    scene = QGraphicsScene()
    stack = QUndoStack()
    first = _item(scene, stack, 10, 20)
    second = _item(scene, stack, 30, 40)
    first.setPos(100, 200)
    second.setPos(300, 400)

    stack.push(ResetLayoutCommand(editable_scene_items(scene)))
    assert first.pos() == QPointF(10, 20)
    assert second.pos() == QPointF(30, 40)
    stack.undo()
    assert first.pos() == QPointF(100, 200)
    assert second.pos() == QPointF(300, 400)


def test_rotation_pen_and_order_are_undoable(qapp) -> None:
    scene = QGraphicsScene()
    stack = QUndoStack()
    item = _item(scene, stack, 10, 20)

    stack.push(RotateItemsCommand([item], 45.0))
    assert item.rotation() == 45.0
    stack.undo()
    assert item.rotation() == 0.0

    stack.push(ChangePenCommand([item], width=4.0))
    assert item.pen().widthF() == 4.0
    stack.undo()

    stack.push(ChangeZCommand([item], 1.0))
    assert item.zValue() == 1.0
    stack.undo()
    assert item.zValue() == 0.0

    label = QGraphicsSimpleTextItem("Pole 1")
    scene.addItem(label)
    before_color = label.brush().color()
    stack.push(ChangePenCommand([label], color=QColor("#00ff00")))
    assert label.brush().color() == QColor("#00ff00")
    stack.undo()
    assert label.brush().color() == before_color
