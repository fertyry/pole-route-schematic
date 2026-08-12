import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from pole_route.exporters.excel_exporter import collect_excel_objects
from pole_route.ui.editor_commands import EditableRectItem, EditableTextItem


def test_scene_is_flattened_to_editable_excel_objects(qapp) -> None:
    scene = QGraphicsScene()
    line = QGraphicsLineItem(10, 20, 100, 20)
    line.setPen(QPen(QColor("#d0d0d0"), 3))
    scene.addItem(line)
    pole = EditableRectItem(-7, -7, 14, 14, undo_stack=QUndoStack())
    pole.setPos(QPointF(60, 5))
    pole.setPen(QPen(QColor("#eb5757"), 2))
    pole.setBrush(QBrush(QColor("#202020")))
    scene.addItem(pole)
    label = EditableTextItem("P-1", QUndoStack())
    label.setPos(70, 25)
    label.setBrush(QBrush(QColor("#eb5757")))
    scene.addItem(label)

    objects = collect_excel_objects(scene)

    assert [item.kind for item in objects] == ["line", "rectangle", "text"]
    assert objects[2].text == "P-1"
    assert all(point[0] >= 24 and point[1] >= 24 for item in objects for point in item.points)


def test_rotated_square_keeps_its_original_size(qapp) -> None:
    scene = QGraphicsScene()
    pole = EditableRectItem(-7, -7, 14, 14, undo_stack=QUndoStack())
    pole.setRotation(45)
    scene.addItem(pole)

    exported = collect_excel_objects(scene)[0]
    (left, top), (right, bottom) = exported.points

    assert exported.rotation == 45
    assert right - left == bottom - top
    assert right - left == pytest.approx(14 * 0.72)
