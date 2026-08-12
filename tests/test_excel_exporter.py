import gc

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import GeoPoint, Route
from pole_route.exporters.excel_exporter import (
    ExcelExportSettings,
    collect_excel_objects,
    collect_scene_objects,
    prepare_excel_pages,
)
from pole_route.geometry.road_geometry import build_road_geometry
from pole_route.geometry.schematic_layout import create_schematic_layout
from pole_route.ui.editor_commands import EditableRectItem, EditableTextItem
from pole_route.ui.schematic_renderer import render_schematic


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


def test_collecting_export_snapshot_retains_renderer_owned_canvas_items(qapp) -> None:
    scene = QGraphicsScene()
    route = Route("Road", "route.kml", (GeoPoint(100, 13), GeoPoint(100.01, 13)))
    pole = Pole("P-1", 13.0001, 100.005, side=PoleSide.LEFT)
    layout = create_schematic_layout(build_road_geometry(route, [pole], 6, 2))
    render_schematic(scene, layout, QUndoStack())
    expected_count = len(scene.items())

    snapshot = collect_scene_objects(scene)
    gc.collect()

    assert snapshot
    assert len(scene.items()) == expected_count
    assert len(scene._pole_route_item_refs) == expected_count
    assert all(item.scene() is scene for item in scene._pole_route_item_refs)


def test_drawing_can_be_split_into_numbered_paper_sheets(qapp) -> None:
    scene = QGraphicsScene()
    scene.addLine(0, 50, 1000, 50)
    for x in (100, 300, 700, 900):
        pole = EditableRectItem(-5, -5, 10, 10, undo_stack=QUndoStack())
        pole.setData(0, "pole")
        pole.setPos(x, 20)
        scene.addItem(pole)

    pages = prepare_excel_pages(
        collect_scene_objects(scene),
        ExcelExportSettings(page_count=2),
    )

    assert len(pages) == 2
    assert all(any(item.role == "pole" for item in page) for page in pages)
    footers = [next(item.text for item in page if item.role == "footer") for page in pages]
    assert "Sheet 1 / 2" in footers[0]
    assert "Sheet 2 / 2" in footers[1]
