from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QGraphicsPathItem,
    QGraphicsTextItem,
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
    assert QLocale().zeroDigit() == "0"


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


def test_route_dialog_reverses_selected_linestring_and_preview_direction(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route

    source = Route(
        "Main",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.1, 13.1), GeoPoint(100.2, 13.2)),
    )
    dialog = RouteImportDialog([source])
    qtbot.addWidget(dialog)

    dialog.table.item(0, 6).setCheckState(Qt.CheckState.Checked)
    imported = dialog.selected_route()

    assert imported.points == tuple(reversed(source.points))
    assert source.points[0].longitude == 100.0
    assert "Start 13.200000, 100.200000" in dialog.details.text()
    labels = [
        item.toPlainText()
        for item in dialog.scene.items()
        if isinstance(item, QGraphicsTextItem)
    ]
    assert set(labels) == {"START", "END"}


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
