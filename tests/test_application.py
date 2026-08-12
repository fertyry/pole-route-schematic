from PySide6.QtWidgets import QGraphicsView

from pole_route.main import create_application
from pole_route.ui.main_window import MainWindow


def test_application_metadata(qtbot) -> None:
    application = create_application([])

    assert application.applicationName() == "PoleRoute Schematic"
    assert application.applicationVersion() == "0.1.0"


def test_main_window_contains_canvas(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "PoleRoute Schematic - Sprint 1"
    assert window.findChild(QGraphicsView, "schematicCanvas") is not None


def test_main_window_can_show_poles(qtbot) -> None:
    from pole_route.domain.pole import Pole, PoleSide

    window = MainWindow()
    qtbot.addWidget(window)
    window.show_poles([Pole("P-001", 13.7563, 100.5018, "Transformer", PoleSide.LEFT)])

    assert window.pole_table.rowCount() == 1
    assert window.pole_table.item(0, 0).text() == "P-001"
    assert window.pole_table.item(0, 4).text() == "Left"
