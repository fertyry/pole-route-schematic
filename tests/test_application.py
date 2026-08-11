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

    assert window.windowTitle() == "PoleRoute Schematic — Sprint 0"
    assert window.findChild(QGraphicsView, "schematicCanvas") is not None
