"""Application entry point."""

import sys

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from pole_route.ui.main_window import MainWindow


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create or return the Qt application instance."""
    # Keep decimal points and digits predictable regardless of the Windows
    # display language.  Thai text is still supported; only number formatting
    # uses the locale-neutral 0-9 digits.
    QLocale.setDefault(QLocale.c())
    application = QApplication.instance() or QApplication(argv or sys.argv)
    application.setApplicationName("PoleRoute Schematic")
    application.setOrganizationName("PoleRoute Schematic")
    application.setApplicationVersion("0.1.0")
    return application


def main() -> int:
    application = create_application()
    window = MainWindow()
    window.show()
    return application.exec()
