import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QGraphicsPathItem,
    QGraphicsView,
    QTableWidgetSelectionRange,
)

from pole_route.importers.pole_importer import PoleTable
from pole_route.main import create_application
from pole_route.ui.column_mapping_dialog import ColumnMappingDialog
from pole_route.ui.geometry_settings_dialog import GeometrySettingsDialog
from pole_route.ui.main_window import MainWindow
from pole_route.ui.route_import_dialog import RouteImportDialog
from pole_route.ui.schematic_settings_dialog import SchematicSettingsDialog


def test_application_metadata(qtbot) -> None:
    application = create_application([])

    assert application.applicationName() == "PoleRoute Schematic"
    assert application.applicationVersion() == "0.1.0"


def test_main_window_contains_canvas(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "PoleRoute Schematic - Sprint 3"
    assert window.findChild(QGraphicsView, "schematicCanvas") is not None


def test_main_window_can_show_poles(qtbot) -> None:
    from pole_route.domain.pole import Pole, PoleSide

    window = MainWindow()
    qtbot.addWidget(window)
    window.show_poles([Pole("P-001", 13.7563, 100.5018, "Transformer", PoleSide.LEFT)])

    assert window.pole_table.rowCount() == 1
    assert window.pole_table.item(0, 0).text() == "P-001"
    assert window.pole_table.item(0, 4).text() == "Left"


def test_geometry_action_requires_route_and_poles(qtbot) -> None:
    from pole_route.domain.pole import Pole
    from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType

    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.build_geometry_action.isEnabled()

    window.current_route = Route(
        "Road",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )
    window.current_routes = [
        ClassifiedRoute(window.current_route, RouteType.MAIN_ROUTE, 6.0, 2.0)
    ]
    window._update_geometry_action()
    assert not window.build_geometry_action.isEnabled()

    window.current_poles = [Pole("1", 13.0, 100.001)]
    window._update_geometry_action()
    assert window.build_geometry_action.isEnabled()


def test_mapping_dialog_uses_explicit_confirmation(qtbot) -> None:
    table = PoleTable(
        ("No", "Latitude", "Longitude"),
        (("1", 13.7, 100.5),),
        header_row=1,
    )
    dialog = ColumnMappingDialog(
        table,
        {"number": "No", "latitude": "Latitude", "longitude": "Longitude", "detail": None, "side": None},
    )
    qtbot.addWidget(dialog)
    buttons = dialog.findChild(QDialogButtonBox)

    assert buttons.button(QDialogButtonBox.StandardButton.Ok).text() == "Confirm import"


def test_route_dialog_uses_explicit_confirmation(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route

    route = Route("Road", "route.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.1, 13.1)))
    dialog = RouteImportDialog([route])
    qtbot.addWidget(dialog)
    buttons = dialog.findChild(QDialogButtonBox)

    assert dialog.selected_route() is route
    assert buttons.button(QDialogButtonBox.StandardButton.Ok).text() == "Confirm routes"


def test_route_dialog_classifies_multiple_lines(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route, RouteType

    routes = [
        Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100.1, 13.1))),
        Route("Soi", "route.kml", (GeoPoint(100.05, 13.05), GeoPoint(100.06, 13.06))),
    ]
    dialog = RouteImportDialog(routes)
    qtbot.addWidget(dialog)
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    dialog.table.cellWidget(1, 2).setCurrentText(RouteType.ROAD.value)
    dialog.table.cellWidget(1, 3).setValue(4.0)
    dialog.table.item(1, 4).setCheckState(Qt.CheckState.Checked)

    classified = dialog.classified_routes()

    assert [item.type for item in classified] == [RouteType.MAIN_ROUTE, RouteType.ROAD]
    assert classified[0].width_metres == 6.0
    assert classified[1].width_metres == 4.0
    assert classified[0].pole_offset_metres == 2.0


def test_route_dialog_uses_arabic_digits_and_previews_checked_routes(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route

    routes = [
        Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100.1, 13.1))),
        Route("Soi", "route.kml", (GeoPoint(100.05, 13.05), GeoPoint(100.06, 13.06))),
    ]
    dialog = RouteImportDialog(routes)
    qtbot.addWidget(dialog)

    assert dialog.table.cellWidget(0, 3).locale().zeroDigit() == "0"
    assert dialog.table.cellWidget(0, 5).locale().zeroDigit() == "0"
    assert dialog.preview_all_button.text() == "Preview selected routes"

    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    qtbot.mouseClick(dialog.preview_all_button, Qt.MouseButton.LeftButton)

    paths = [item for item in dialog.scene.items() if isinstance(item, QGraphicsPathItem)]
    assert len(paths) == 2
    assert dialog.details.text().startswith("Previewing 2 selected routes")


def test_route_dialog_allows_multiple_main_routes(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route, RouteType

    routes = [
        Route("Main 1", "route.kml", (GeoPoint(100, 13), GeoPoint(100.1, 13.1))),
        Route("Main 2", "route.kml", (GeoPoint(100.1, 13.1), GeoPoint(100.2, 13.2))),
    ]
    dialog = RouteImportDialog(routes)
    qtbot.addWidget(dialog)
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    dialog.table.cellWidget(1, 2).setCurrentText(RouteType.MAIN_ROUTE.value)
    dialog.table.cellWidget(1, 3).setValue(8.0)
    dialog.table.item(1, 4).setCheckState(Qt.CheckState.Checked)
    dialog.table.cellWidget(1, 5).setValue(3.0)

    classified = dialog.classified_routes()

    assert [item.type for item in classified] == [RouteType.MAIN_ROUTE, RouteType.MAIN_ROUTE]
    assert [item.width_metres for item in classified] == [6.0, 8.0]
    assert [item.pole_offset_metres for item in classified] == [2.0, 3.0]


def test_geometry_settings_use_arabic_digits(qtbot) -> None:
    dialog = GeometrySettingsDialog()
    qtbot.addWidget(dialog)

    assert dialog.road_width.locale().zeroDigit() == "0"
    assert dialog.pole_offset.locale().zeroDigit() == "0"


def test_schematic_spacing_dialog_returns_spacing_enum(qtbot) -> None:
    from pole_route.geometry.schematic_layout import PoleSpacingMode, SchematicLayoutMode

    dialog = SchematicSettingsDialog()
    qtbot.addWidget(dialog)

    assert dialog.layout_mode() is SchematicLayoutMode.NETWORK
    assert dialog.spacing_mode() is PoleSpacingMode.PROJECTED_STATION
    dialog.spacing.setCurrentIndex(1)
    assert dialog.layout_mode() is SchematicLayoutMode.STRAIGHT_EQUAL
    assert dialog.spacing_mode() is PoleSpacingMode.EQUAL


def test_main_window_marks_selected_rows_as_one_physical_pole(qtbot) -> None:
    from pole_route.domain.pole import Pole

    window = MainWindow()
    qtbot.addWidget(window)
    poles = [Pole("6", 13.0, 100.0), Pole("7", 13.1, 100.1)]
    window.current_poles = poles
    window.show_poles(poles)
    window.pole_table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 5), True)

    window._mark_selected_rows_as_same_pole()

    assert window.same_pole_groups == [frozenset({"6", "7"})]
    assert window.pole_table.item(0, 5).text() == "6 / 7"
    assert window.pole_table.item(1, 5).text() == "6 / 7"


def test_canvas_editor_hides_table_and_restores_workspace(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window._toggle_canvas_editor(True)
    assert window.pole_table.isHidden()
    assert window.heading.isHidden()

    window._toggle_canvas_editor(False)
    assert not window.pole_table.isHidden()
    assert not window.heading.isHidden()


def test_properties_panel_changes_selected_line_and_supports_undo(qtbot) -> None:
    from PySide6.QtCore import QLineF
    from PySide6.QtGui import QPen

    from pole_route.ui.editor_commands import EditableLineItem
    from pole_route.ui.schematic_renderer import EDITABLE_FLAGS

    window = MainWindow()
    qtbot.addWidget(window)
    line = EditableLineItem(QLineF(0, 0, 100, 0), undo_stack=window.undo_stack)
    line.setData(0, "drawing")
    line.setFlags(EDITABLE_FLAGS)
    line.setPen(QPen(Qt.GlobalColor.white, 2.0))
    window.route_scene.addItem(line)
    line.setSelected(True)

    window._change_selected_line_width(4.0)
    assert line.pen().widthF() == 4.0
    window.undo_stack.undo()
    assert line.pen().widthF() == 2.0


def test_canvas_view_zoom_rotation_and_north_up(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    before = window.canvas.transform().m11()

    window.canvas.zoom_in()
    assert window.canvas.transform().m11() > before

    window._set_canvas_rotation(30)
    assert window.canvas.rotation_degrees == 30
    assert window.rotation_angle.value() == 30

    window._set_canvas_rotation(0)
    assert window.canvas.rotation_degrees == 0


def test_numeric_editor_controls_use_arabic_digits(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.rotation_angle.locale().zeroDigit() == "0"
    assert window.properties_panel.rotation.locale().zeroDigit() == "0"
    assert window.properties_panel.line_width.locale().zeroDigit() == "0"
    assert window.properties_panel.font_size.locale().zeroDigit() == "0"


def test_multi_object_rotation_uses_one_undo_command(qtbot) -> None:
    from pole_route.ui.editor_commands import EditableEllipseItem
    from pole_route.ui.schematic_renderer import EDITABLE_FLAGS

    window = MainWindow()
    qtbot.addWidget(window)
    items = []
    for x in (100.0, 300.0):
        item = EditableEllipseItem(-5, -5, 10, 10, undo_stack=window.undo_stack)
        item.setData(0, "drawing")
        item.setFlags(EDITABLE_FLAGS)
        item.setPos(x, 100)
        window.route_scene.addItem(item)
        item.setSelected(True)
        items.append(item)

    window._rotate_selected_objects(90.0)

    assert [item.rotation() for item in items] == [90.0, 90.0]
    assert items[0].pos().x() == pytest.approx(items[1].pos().x())
    assert items[0].pos().y() != pytest.approx(items[1].pos().y())
    window.undo_stack.undo()
    assert [item.rotation() for item in items] == [0.0, 0.0]
    assert [item.pos().x() for item in items] == [100.0, 300.0]


def test_layer_can_lock_and_select_all_items(qtbot) -> None:
    from pole_route.ui.editor_commands import EditableEllipseItem
    from pole_route.ui.schematic_renderer import EDITABLE_FLAGS

    window = MainWindow()
    qtbot.addWidget(window)
    item = EditableEllipseItem(-5, -5, 10, 10, undo_stack=window.undo_stack)
    item.setData(0, "pole")
    item.setFlags(EDITABLE_FLAGS)
    window.route_scene.addItem(item)

    window._set_layer_locked("Poles", True)
    assert not item.flags() & item.GraphicsItemFlag.ItemIsMovable
    window._set_layer_locked("Poles", False)
    window._select_layer("Poles")
    assert item.isSelected()


def test_middle_button_pan_does_not_move_road_object(qtbot) -> None:
    from PySide6.QtCore import QLineF, QPoint
    from PySide6.QtWidgets import QGraphicsLineItem

    from pole_route.ui.editor_commands import EditableItemGroup
    from pole_route.ui.schematic_renderer import EDITABLE_FLAGS

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(700, 500)
    window.show()
    road = EditableItemGroup(window.undo_stack)
    road.setData(0, "road")
    road.setFlags(EDITABLE_FLAGS)
    road.addToGroup(QGraphicsLineItem(QLineF(100, 100, 500, 100)))
    window.route_scene.addItem(road)
    window.route_scene.setSceneRect(0, 0, 1200, 800)
    before = road.pos()
    start = window.canvas.mapFromScene(300, 100)

    qtbot.mousePress(window.canvas.viewport(), Qt.MouseButton.MiddleButton, pos=start)
    qtbot.mouseMove(window.canvas.viewport(), pos=start + QPoint(80, 50))
    qtbot.mouseRelease(
        window.canvas.viewport(), Qt.MouseButton.MiddleButton, pos=start + QPoint(80, 50)
    )

    assert road.pos() == before


def test_middle_button_drag_does_not_change_canvas_scroll(qtbot) -> None:
    from PySide6.QtCore import QPoint

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(700, 500)
    window.show()
    window.route_scene.setSceneRect(0, 0, 2000, 1400)
    window.canvas.centerOn(1000, 700)
    before = (
        window.canvas.horizontalScrollBar().value(),
        window.canvas.verticalScrollBar().value(),
    )
    start = QPoint(250, 200)

    qtbot.mousePress(window.canvas.viewport(), Qt.MouseButton.MiddleButton, pos=start)
    qtbot.mouseMove(window.canvas.viewport(), pos=start + QPoint(100, 80))
    qtbot.mouseRelease(
        window.canvas.viewport(), Qt.MouseButton.MiddleButton, pos=start + QPoint(100, 80)
    )

    assert window.canvas.horizontalScrollBar().value() == before[0]
    assert window.canvas.verticalScrollBar().value() == before[1]


def test_left_click_selects_objects_without_removing_or_moving_them(qtbot) -> None:
    from pole_route.domain.pole import Pole, PoleSide
    from pole_route.domain.route import GeoPoint, Route
    from pole_route.geometry.road_geometry import build_road_geometry
    from pole_route.geometry.schematic_layout import create_schematic_layout
    from pole_route.ui.schematic_renderer import render_schematic

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(900, 650)
    window.show()
    route = Route("Road", "route.kml", (GeoPoint(100, 13), GeoPoint(100.01, 13)))
    pole = Pole("P-1", 13.0001, 100.005, "Test", PoleSide.LEFT)
    layout = create_schematic_layout(build_road_geometry(route, [pole], 6, 2))
    render_schematic(window.route_scene, layout, window.undo_stack)
    window.canvas.fit_scene()

    for item_type in ("road", "pole", "label"):
        item = next(item for item in window.route_scene.items() if item.data(0) == item_type)
        before_position = item.pos()
        click_position = window.canvas.mapFromScene(item.sceneBoundingRect().center())
        qtbot.mouseClick(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=click_position)

        assert item.scene() is window.route_scene
        assert item.isVisible()
        assert item.pos() == before_position


def test_fit_scene_recenters_after_scene_is_replaced(qtbot) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QGraphicsRectItem

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(800, 600)
    window.show()
    window.route_scene.setSceneRect(0, 0, 1600, 850)
    window.route_scene.addItem(QGraphicsRectItem(QRectF(120, 120, 1360, 610)))

    window.canvas.zoom_in()
    window.canvas.horizontalScrollBar().setValue(window.canvas.horizontalScrollBar().maximum())
    window.canvas.verticalScrollBar().setValue(window.canvas.verticalScrollBar().maximum())
    window.canvas.fit_scene()

    scene_center = window.route_scene.sceneRect().center()
    center_in_view = window.canvas.mapFromScene(scene_center)
    assert window.canvas.viewport().rect().contains(center_in_view)
    assert window.canvas.viewport().rect().contains(window.canvas.mapFromScene(120, 120))
    assert window.canvas.viewport().rect().contains(window.canvas.mapFromScene(1480, 730))


def test_refreshed_canvas_exposes_rendered_items_in_viewport(qtbot) -> None:
    from pole_route.domain.pole import Pole, PoleSide
    from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
    from pole_route.geometry.road_geometry import build_road_network_geometry
    from pole_route.geometry.schematic_layout import create_schematic_layout
    from pole_route.ui.schematic_renderer import render_schematic

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    route = ClassifiedRoute(
        Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100.01, 13.005))),
        RouteType.MAIN_ROUTE,
        6.0,
        1.0,
    )
    poles = [Pole("1", 13.001, 100.002, "EP.12", PoleSide.RIGHT)]
    layout = create_schematic_layout(build_road_network_geometry([route], poles))

    render_schematic(window.route_scene, layout, window.undo_stack)
    window.canvas.refresh_scene()
    qtbot.wait(10)

    visible_types = {
        item.data(0)
        for item in window.canvas.items()
        if item.parentItem() is None and item.data(0)
    }
    assert {"road", "pole", "label"} <= visible_types
