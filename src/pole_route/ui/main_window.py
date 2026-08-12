"""Main application window."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsScene,
    QGraphicsView,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from pole_route.domain.pole import Pole
from pole_route.importers.pole_importer import (
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    PoleImportError,
    inspect_pole_file,
    poles_from_table,
    suggest_column_mapping,
)
from pole_route.ui.column_mapping_dialog import ColumnMappingDialog


class MainWindow(QMainWindow):
    """Top-level window with a placeholder editable-canvas area."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PoleRoute Schematic - Sprint 1")
        self.resize(1100, 720)
        self._build_toolbar()
        self._build_workspace()
        self.statusBar().showMessage("Ready - import an Excel or CSV pole-data file")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Project")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        for label in ("New", "Open", "Import route"):
            action = QAction(label, self)
            action.setEnabled(False)
            toolbar.addAction(action)

        import_poles_action = QAction("Import poles", self)
        import_poles_action.triggered.connect(self._choose_pole_file)
        toolbar.addAction(import_poles_action)

        export_action = QAction("Export", self)
        export_action.setEnabled(False)
        toolbar.addAction(export_action)

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

        note = QLabel("Pole data can now be imported. Drawing and geometry begin in a later sprint.")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)

        self.pole_table = QTableWidget(0, 5)
        self.pole_table.setObjectName("poleTable")
        self.pole_table.setHorizontalHeaderLabels(
            ["Pole No.", "Latitude", "Longitude", "Detail", "Side"]
        )
        self.pole_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pole_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pole_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.pole_table)
        splitter.addWidget(canvas)
        splitter.setSizes([240, 360])

        layout = QVBoxLayout()
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addWidget(splitter, 1)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def _choose_pole_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import pole data",
            "",
            "Pole data (*.xlsx *.csv)",
        )
        if path:
            self.load_pole_file(path)

    def load_pole_file(self, path: str) -> None:
        """Load a pole file and display validation errors to the user."""
        try:
            table = inspect_pole_file(path)
            mapping = suggest_column_mapping(table.headers)
            if any(not mapping[field] for field in REQUIRED_FIELDS):
                dialog = ColumnMappingDialog(table, mapping, self)
                if dialog.exec() != ColumnMappingDialog.DialogCode.Accepted:
                    self.statusBar().showMessage("Pole import cancelled")
                    return
                mapping = dialog.mapping()
            poles = poles_from_table(table, mapping)
        except PoleImportError as error:
            QMessageBox.warning(self, "Pole import failed", str(error))
            self.statusBar().showMessage("Pole import failed")
            return

        self.show_poles(poles)
        optional_missing = [field for field in OPTIONAL_FIELDS if not mapping[field]]
        suffix = " (optional fields omitted)" if optional_missing else ""
        self.statusBar().showMessage(f"Imported {len(poles)} poles{suffix}")

    def show_poles(self, poles: list[Pole]) -> None:
        """Replace the table contents with imported pole records."""
        self.pole_table.setRowCount(len(poles))
        for row_index, pole in enumerate(poles):
            values = (
                pole.number,
                f"{pole.latitude:.7f}",
                f"{pole.longitude:.7f}",
                pole.detail,
                pole.side.value,
            )
            for column_index, value in enumerate(values):
                self.pole_table.setItem(row_index, column_index, QTableWidgetItem(value))
