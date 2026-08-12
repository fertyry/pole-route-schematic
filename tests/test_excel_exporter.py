import gc

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import GeoPoint, Route
from pole_route.exporters.excel_exporter import (
    ExcelExportSettings,
    ExcelObject,
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


def test_work_description_is_rendered_as_third_header_row(qapp) -> None:
    objects = prepare_excel_pages(
        [ExcelObject("line", ((0, 0), (100, 0)), role="road_edge")],
        ExcelExportSettings(
            project_title="Project",
            location="Route",
            work_description="144 poles and New Cable Tray 1 Set",
        ),
    )[0]

    description = next(item for item in objects if item.role == "work_description")
    assert description.text == "144 poles and New Cable Tray 1 Set"


def test_compass_uses_an_arrow_pointing_to_north_label(qapp) -> None:
    objects = prepare_excel_pages(
        [ExcelObject("line", ((0, 0), (100, 0)), role="road_edge")],
        ExcelExportSettings(show_compass=True),
    )[0]

    arrow = next(item for item in objects if item.role == "compass" and item.kind == "arrow")
    north = next(item for item in objects if item.role == "compass" and item.text == "N")
    assert arrow.points[1][1] < arrow.points[0][1]
    assert north.points[0][1] < arrow.points[1][1]


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


def test_page_boundaries_are_real_repeated_poles(qapp) -> None:
    objects = [
        ExcelObject("line", ((0, 0), (500, 0)), role="main_centerline", group_id="main")
    ]
    for index, x in enumerate((20, 80, 210, 350, 480), start=1):
        group = f"P-{index}"
        objects.extend(
            [
                ExcelObject("rectangle", ((x - 3, -3), (x + 3, 3)), role="pole", group_id=group),
                ExcelObject("text", ((x, 10), (x + 30, 20)), f"{group} detail", role="label", group_id=group),
            ]
        )

    pages = prepare_excel_pages(objects, ExcelExportSettings(page_count=2))

    first_groups = {item.group_id for item in pages[0] if item.role == "pole"}
    second_groups = {item.group_id for item in pages[1] if item.role == "pole"}
    assert first_groups & second_groups == {"P-3"}
    assert {item.text for item in pages[0] if item.role == "pole_sequence"} == {"1", "2", "3"}
    assert {item.text for item in pages[1] if item.role == "pole_sequence"} == {"3", "4", "5"}


def test_export_preserves_generated_relative_pole_spacing(qapp) -> None:
    objects = [
        ExcelObject("line", ((0, 0), (500, 0)), role="main_centerline", group_id="main")
    ]
    for index, x in enumerate((20, 80, 210, 350, 480), start=1):
        group = f"P-{index}"
        objects.append(
            ExcelObject(
                "rectangle", ((x - 3, -3), (x + 3, 3)), role="pole", group_id=group
            )
        )

    page = prepare_excel_pages(objects, ExcelExportSettings(page_count=2))[0]
    xs = {
        item.group_id: sum(x for x, _ in item.points) / len(item.points)
        for item in page
        if item.role == "pole"
    }

    # One affine transform preserves the 60:130 source gap ratio.
    assert (xs["P-2"] - xs["P-1"]) / (xs["P-3"] - xs["P-2"]) == pytest.approx(60 / 130)


def test_page_lines_are_clipped_at_match_poles(qapp) -> None:
    objects = [
        ExcelObject("line", ((-200, 0), (700, 0)), role="main_centerline", group_id="main")
    ]
    for index, x in enumerate((0, 100, 200, 300, 400), start=1):
        objects.append(
            ExcelObject("rectangle", ((x - 3, -3), (x + 3, 3)), role="pole", group_id=f"P-{index}")
        )

    pages = prepare_excel_pages(objects, ExcelExportSettings(page_count=2))

    for page in pages:
        pole_xs = [x for item in page if item.role == "pole" for x, _ in item.points]
        line_xs = [x for item in page if item.role == "main_centerline" for x, _ in item.points]
        assert min(line_xs) >= min(pole_xs) - 5
        assert max(line_xs) <= max(pole_xs) + 5


def test_context_roads_are_clipped_to_export_corridor(qapp) -> None:
    objects = [
        ExcelObject("line", ((0, 0), (500, 0)), role="main_centerline", group_id="main"),
        ExcelObject("line", ((250, -100), (250, 100)), role="centerline", group_id="Soi Test"),
        ExcelObject("line", ((245, -100), (245, 100)), role="road_edge"),
        ExcelObject("text", ((-200, 80), (-140, 95)), "Soi Test", role="road_name", group_id="Soi Test"),
    ]
    for index, x in enumerate((0, 250, 500), start=1):
        objects.append(
            ExcelObject("rectangle", ((x - 2, -2), (x + 2, 2)), role="pole", group_id=f"P-{index}")
        )

    page = prepare_excel_pages(
        objects, ExcelExportSettings(page_count=1, context_road_length=20.0)
    )[0]

    road_lines = [
        item for item in page if item.role in {"centerline", "road_edge"}
    ]
    poles = [item for item in page if item.role == "pole"]
    pole_y = sum(y for item in poles for _, y in item.points) / sum(
        len(item.points) for item in poles
    )
    assert road_lines
    assert max(abs(y - pole_y) for item in road_lines for _, y in item.points) < 20.0
    road_name = next(item for item in page if item.role == "road_name")
    assert abs(road_name.rotation) == pytest.approx(90.0)
    road_name_center_x = sum(x for x, _ in road_name.points) / len(road_name.points)
    context_center_x = sum(x for item in road_lines for x, _ in item.points) / sum(
        len(item.points) for item in road_lines
    )
    assert road_name_center_x == pytest.approx(context_center_x, abs=35.0)


def test_legacy_road_name_without_group_uses_nearest_context_road(qapp) -> None:
    objects = [
        ExcelObject("line", ((0, 0), (500, 0)), role="main_centerline", group_id="main"),
        ExcelObject("line", ((300, -80), (300, 80)), role="centerline"),
        ExcelObject("text", ((285, 65), (385, 80)), "Legacy Soi", role="road_name"),
    ]
    for index, x in enumerate((0, 250, 500), start=1):
        objects.append(
            ExcelObject("rectangle", ((x - 2, -2), (x + 2, 2)), role="pole", group_id=f"P-{index}")
        )

    page = prepare_excel_pages(
        objects, ExcelExportSettings(page_count=1, context_road_length=20.0)
    )[0]

    label = next(item for item in page if item.role == "road_name")
    context = next(item for item in page if item.role == "centerline")
    label_x = sum(x for x, _ in label.points) / len(label.points)
    context_x = sum(x for x, _ in context.points) / len(context.points)
    assert label_x == pytest.approx(context_x, abs=35.0)
    assert abs(label.rotation) == pytest.approx(90.0)


def test_all_sheets_use_one_affine_display_scale(qapp) -> None:
    objects = [
        ExcelObject("line", ((0, 0), (500, 0)), role="main_centerline", group_id="main")
    ]
    for index, x in enumerate((0, 100, 200, 300, 400), start=1):
        objects.append(
            ExcelObject("rectangle", ((x - 3, -3), (x + 3, 3)), role="pole", group_id=f"P-{index}")
        )

    first, second = prepare_excel_pages(objects, ExcelExportSettings(page_count=2))

    def gap(page, left_group, right_group):
        centers = {
            item.group_id: sum(x for x, _ in item.points) / len(item.points)
            for item in page
            if item.role == "pole"
        }
        return centers[right_group] - centers[left_group]

    assert gap(first, "P-1", "P-2") == pytest.approx(
        gap(second, "P-3", "P-4")
    )


def test_sheet_boundaries_follow_route_distance_not_pole_count(qapp) -> None:
    objects = [
        ExcelObject("line", ((0, 0), (500, 0)), role="main_centerline", group_id="main")
    ]
    for index, x in enumerate((0, 10, 20, 30, 400, 500), start=1):
        objects.append(
            ExcelObject(
                "rectangle", ((x - 2, -2), (x + 2, 2)), role="pole", group_id=f"P-{index}"
            )
        )

    first, second = prepare_excel_pages(objects, ExcelExportSettings(page_count=2))

    first_groups = {item.group_id for item in first if item.role == "pole"}
    second_groups = {item.group_id for item in second if item.role == "pole"}
    # Half the route is station 250; P-5 at station 400 is closer than P-4 at 30.
    assert first_groups & second_groups == {"P-5"}


def test_tagged_main_route_is_split_start_to_end_and_rotated_horizontal(qapp) -> None:
    objects = [
        ExcelObject(
            "line",
            ((index * 100, index * 100), ((index + 1) * 100, (index + 1) * 100)),
            role="main_centerline",
            group_id="main-0",
        )
        for index in range(4)
    ]
    for index, position in enumerate((50, 150, 250, 350), start=1):
        objects.extend(
            [
                ExcelObject(
                    "rectangle",
                    ((position - 5, position - 5), (position + 5, position + 5)),
                    role="pole",
                    group_id=f"P-{index}",
                ),
                ExcelObject(
                    "text",
                    ((position + 10, position + 10), (position + 30, position + 20)),
                    text=f"P-{index}",
                    role="label",
                    group_id=f"P-{index}",
                ),
            ]
        )

    pages = prepare_excel_pages(
        objects, ExcelExportSettings(page_count=2)
    )

    # The boundary pole is repeated as the match pole on both adjacent sheets.
    assert [sum(item.role == "pole" for item in page) for page in pages] == [2, 3]
    assert [sum(item.role == "pole_sequence" for item in page) for page in pages] == [2, 3]
    assert all(any(item.role == "schedule" for item in page) for page in pages)
    for page in pages:
        main_lines = [item for item in page if item.role == "main_centerline"]
        assert main_lines
        assert all(abs(a[1] - b[1]) < 1e-6 for item in main_lines for a, b in [item.points])
    assert any(item.text == "Sheet 2 →" for item in pages[0])
    assert any(item.text == "← Sheet 1" for item in pages[1])
