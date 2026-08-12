import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from pole_route.exporters.excel_exporter import ExcelExportSettings, collect_excel_objects
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

    objects = collect_excel_objects(scene, ExcelExportSettings(frame_style="none"))

    assert [item.kind for item in objects] == ["line", "rectangle", "text"]
    assert next(item for item in objects if item.kind == "text").text == "P-1"
    assert all(point[0] >= 24 and point[1] >= 24 for item in objects for point in item.points)


def test_rotated_square_keeps_its_original_size(qapp) -> None:
    scene = QGraphicsScene()
    pole = EditableRectItem(-7, -7, 14, 14, undo_stack=QUndoStack())
    pole.setRotation(45)
    scene.addItem(pole)

    exported = collect_excel_objects(scene, ExcelExportSettings(frame_style="none"))[0]
    (left, top), (right, bottom) = exported.points

    assert exported.rotation == 45
    assert right - left == bottom - top
    assert right - left > 0


def test_monochrome_style_frame_and_pole_paper_size(qapp) -> None:
    scene = QGraphicsScene()
    pole = EditableRectItem(-7, -7, 14, 14, undo_stack=QUndoStack())
    pole.setData(0, "pole")
    pole.setPen(QPen(QColor("red"), 2))
    pole.setBrush(QBrush(QColor("red")))
    scene.addItem(pole)

    objects = collect_excel_objects(
        scene,
        ExcelExportSettings(project_title="Test Project", pole_size_mm=4.0),
    )

    exported_pole = next(item for item in objects if item.role == "pole")
    (left, _top), (right, _bottom) = exported_pole.points
    assert exported_pole.line_color == 0
    assert exported_pole.fill_color == 0
    assert right - left == pytest.approx(4 * 72 / 25.4)
    assert any(item.role == "frame" for item in objects)
    assert any(item.role == "title" and item.text == "Test Project" for item in objects)
