import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QUndoStack, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene

from pole_route.ui.drawing_view import DrawingMode, DrawingView, snap_line_endpoint
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


def test_shift_line_endpoint_snaps_to_45_degree_increments() -> None:
    start = QPointF(10, 10)

    horizontal = snap_line_endpoint(start, QPointF(90, 22))
    diagonal = snap_line_endpoint(start, QPointF(70, 63))
    vertical = snap_line_endpoint(start, QPointF(18, 90))

    assert horizontal.y() == pytest.approx(10)
    assert abs((diagonal.x() - 10) - (diagonal.y() - 10)) < 1e-8
    assert vertical.x() == pytest.approx(10)


def test_ctrl_wheel_zooms_without_changing_scene_items(qtbot) -> None:
    scene = QGraphicsScene(0, 0, 2000, 2000)
    stack = QUndoStack()
    item = EditableEllipseItem(-5, -5, 10, 10, undo_stack=stack)
    item.setPos(500, 600)
    scene.addItem(item)
    view = DrawingView(scene, stack)
    view.resize(400, 300)
    qtbot.addWidget(view)
    view.show()
    before_scale = view.transform().m11()
    before_position = QPointF(item.pos())

    event = QWheelEvent(
        QPointF(100, 100),
        QPointF(100, 100),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    view.wheelEvent(event)

    assert view.transform().m11() > before_scale
    assert item.pos() == before_position
    assert item.scene() is scene


def test_wheel_scrolls_without_transforming_or_removing_items(qtbot) -> None:
    scene = QGraphicsScene(0, 0, 2000, 2000)
    stack = QUndoStack()
    item = EditableEllipseItem(-5, -5, 10, 10, undo_stack=stack)
    item.setPos(500, 600)
    scene.addItem(item)
    view = DrawingView(scene, stack)
    view.resize(400, 300)
    qtbot.addWidget(view)
    view.show()
    view.verticalScrollBar().setValue(500)
    before_scroll = view.verticalScrollBar().value()
    before_scale = view.transform().m11()

    event = QWheelEvent(
        QPointF(100, 100),
        QPointF(100, 100),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    view.wheelEvent(event)

    assert view.verticalScrollBar().value() < before_scroll
    assert view.transform().m11() == before_scale
    assert item.scene() is scene
