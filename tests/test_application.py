from PySide6.QtWidgets import QDialogButtonBox, QGraphicsView

from pole_route.importers.pole_importer import PoleTable
from pole_route.main import create_application
from pole_route.ui.column_mapping_dialog import ColumnMappingDialog
from pole_route.ui.main_window import MainWindow
from pole_route.ui.route_import_dialog import RouteImportDialog


def test_application_metadata(qtbot) -> None:
    application = create_application([])

    assert application.applicationName() == "PoleRoute Schematic"
    assert application.applicationVersion() == "0.1.0"


def test_main_window_contains_canvas(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "PoleRoute Schematic - Sprint 2"
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
    from pole_route.domain.route import GeoPoint, Route

    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.build_geometry_action.isEnabled()

    window.current_route = Route(
        "Road",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )
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
    assert buttons.button(QDialogButtonBox.StandardButton.Ok).text() == "Confirm route"
