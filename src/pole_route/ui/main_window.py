"""Main application window for the Sprint 0 shell."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """Top-level window with a placeholder editable-canvas area."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PoleRoute Schematic — Sprint 0")
        self.resize(1100, 720)
        self._build_toolbar()
        self._build_workspace()
        self.statusBar().showMessage("Ready — import and geometry tools begin in a later sprint")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Project")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        for label in ("New", "Open", "Import route", "Import poles", "Export"):
            action = QAction(label, self)
            action.setEnabled(False)
            toolbar.addAction(action)

    def _build_workspace(self) -> None:
        scene = QGraphicsScene(self)
        scene.setSceneRect(0, 0, 1000, 600)

        canvas = QGraphicsView(scene)
        canvas.setObjectName("schematicCanvas")
        canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        heading = QLabel("Schematic canvas")
        heading.setObjectName("canvasHeading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 20px; font-weight: 600; padding: 6px;")

        note = QLabel(
            "Sprint 0 application shell — drawing, import, and geometry features are not implemented yet."
        )
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addWidget(canvas, 1)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

