from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from pole_route.ui.drawing_view import DrawingMode, DrawingView
from pole_route.ui.editor_commands import EditableEllipseItem, EditableLineItem, EditableRectItem


def test_drawing_modes_create_expected_shapes(qtbot) -> None:
    scene = QGraphicsScene()
    stack = QUndoStack()
    view = DrawingView(scene, stack)
    qtbot.addWidget(view)

    expected_types = {
        DrawingMode.LINE: EditableLineItem,
        DrawingMode.RECTANGLE: EditableRectItem,
        DrawingMode.ELLIPSE: EditableEllipseItem,
    }
    for mode, expected_type in expected_types.items():
        view.set_mode(mode)
        item = view._new_shape(QPointF(10, 20), QPointF(80, 90))
        assert isinstance(item, expected_type)


def test_finished_drawing_is_undoable_and_editable(qtbot) -> None:
    scene = QGraphicsScene()
    stack = QUndoStack()
    view = DrawingView(scene, stack)
    qtbot.addWidget(view)
    view.set_mode(DrawingMode.RECTANGLE)
    item = view._new_shape(QPointF(10, 20), QPointF(80, 90))
    scene.addItem(item)

    view._finish_item(item)

    assert item.data(0) == "drawing"
    assert item.flags() & item.GraphicsItemFlag.ItemIsSelectable
    assert item.flags() & item.GraphicsItemFlag.ItemIsMovable
    assert stack.count() == 1
    stack.undo()
    assert item.scene() is None
    stack.redo()
    assert item.scene() is scene


def test_select_mode_uses_rubber_band(qtbot) -> None:
    scene = QGraphicsScene()
    view = DrawingView(scene, QUndoStack())
    qtbot.addWidget(view)

    view.set_mode(DrawingMode.LINE)
    assert view.dragMode() == view.DragMode.NoDrag
    view.set_mode(DrawingMode.SELECT)
    assert view.dragMode() == view.DragMode.RubberBandDrag
