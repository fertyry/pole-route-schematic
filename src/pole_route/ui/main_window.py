"""Main application window."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QUndoStack
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
from pole_route.domain.route import Route
from pole_route.geometry.road_geometry import RoadGeometryError, build_road_geometry
from pole_route.geometry.schematic_layout import create_schematic_layout
from pole_route.importers.kml_importer import RouteImportError, inspect_route_file
from pole_route.importers.pole_importer import (
    OPTIONAL_FIELDS,
    PoleImportError,
    inspect_pole_file,
    poles_from_table,
    suggest_column_mapping,
)
from pole_route.ui.column_mapping_dialog import ColumnMappingDialog
from pole_route.ui.editor_commands import (
    DeleteItemsCommand,
    ResetLayoutCommand,
    editable_scene_items,
)
from pole_route.ui.geometry_renderer import render_road_geometry
from pole_route.ui.geometry_settings_dialog import GeometrySettingsDialog
from pole_route.ui.route_import_dialog import RouteImportDialog, draw_route_preview
from pole_route.ui.schematic_renderer import render_schematic


class MainWindow(QMainWindow):
    """Top-level window with a placeholder editable-canvas area."""

    def __init__(self) -> None:
        super().__init__()
        self.current_route: Route | None = None
        self.current_poles: list[Pole] = []
        self.current_geometry = None
        self.undo_stack = QUndoStack(self)
        self.setWindowTitle("PoleRoute Schematic - Sprint 3")
        self.resize(1100, 720)
        self._build_toolbar()
        self._build_workspace()
        self.statusBar().showMessage("Ready - import an Excel or CSV pole-data file")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Project")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        for label in ("New", "Open"):
            action = QAction(label, self)
            action.setEnabled(False)
            toolbar.addAction(action)

        import_route_action = QAction("Import route", self)
        import_route_action.triggered.connect(self._choose_route_file)
        toolbar.addAction(import_route_action)

        import_poles_action = QAction("Import poles", self)
        import_poles_action.triggered.connect(self._choose_pole_file)
        toolbar.addAction(import_poles_action)

        self.build_geometry_action = QAction("Build geometry", self)
        self.build_geometry_action.setEnabled(False)
        self.build_geometry_action.triggered.connect(self._build_geometry)
        toolbar.addAction(self.build_geometry_action)

        self.generate_schematic_action = QAction("Generate schematic", self)
        self.generate_schematic_action.setEnabled(False)
        self.generate_schematic_action.triggered.connect(self._generate_schematic)
        toolbar.addAction(self.generate_schematic_action)

        toolbar.addSeparator()
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        toolbar.addAction(self.undo_action)

        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        toolbar.addAction(self.redo_action)

        self.delete_action = QAction("Delete", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.setEnabled(False)
        self.delete_action.triggered.connect(self._delete_selected)
        toolbar.addAction(self.delete_action)

        self.reset_layout_action = QAction("Reset layout", self)
        self.reset_layout_action.setEnabled(False)
        self.reset_layout_action.triggered.connect(self._reset_layout)
        toolbar.addAction(self.reset_layout_action)

        export_action = QAction("Export", self)
        export_action.setEnabled(False)
        toolbar.addAction(export_action)

    def _build_workspace(self) -> None:
        self.route_scene = QGraphicsScene(self)
        self.route_scene.selectionChanged.connect(self._update_editor_actions)
        self.route_scene.setSceneRect(0, 0, 1000, 600)

        canvas = QGraphicsView(self.route_scene)
        canvas.setObjectName("schematicCanvas")
        canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        heading = QLabel("Schematic canvas")
        heading.setObjectName("canvasHeading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 20px; font-weight: 600; padding: 6px;")

        self.workspace_note = QLabel(
            "Import a route and pole data, then build the metric road-geometry preview."
        )
        self.workspace_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.workspace_note.setWordWrap(True)

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
        layout.addWidget(self.workspace_note)
        layout.addWidget(splitter, 1)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def _choose_route_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import road centerline",
            "",
            "Google Earth route (*.kml *.kmz)",
        )
        if path:
            self.load_route_file(path)

    def load_route_file(self, path: str) -> None:
        """Inspect a route file and require confirmation before importing."""
        try:
            routes = inspect_route_file(path)
            dialog = RouteImportDialog(routes, self)
            if dialog.exec() != RouteImportDialog.DialogCode.Accepted:
                self.statusBar().showMessage("Route import cancelled")
                return
            route = dialog.selected_route()
        except RouteImportError as error:
            QMessageBox.warning(self, "Route import failed", str(error))
            self.statusBar().showMessage("Route import failed")
            return

        self.show_route(route)
        self.current_route = route
        self._update_geometry_action()
        self.statusBar().showMessage(f"Imported route '{route.name}' ({len(route.points)} points)")

    def show_route(self, route: Route) -> None:
        """Display the confirmed centerline as a geographic-shape preview."""
        draw_route_preview(self.route_scene, route, 960, 540)

    def _build_geometry(self) -> None:
        dialog = GeometrySettingsDialog(self)
        if dialog.exec() != GeometrySettingsDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Geometry build cancelled")
            return
        try:
            geometry = build_road_geometry(
                self.current_route,
                self.current_poles,
                dialog.road_width.value(),
                dialog.pole_offset.value(),
            )
        except RoadGeometryError as error:
            QMessageBox.warning(self, "Geometry build failed", str(error))
            self.statusBar().showMessage("Geometry build failed")
            return

        render_road_geometry(self.route_scene, geometry)
        self.current_geometry = geometry
        self.generate_schematic_action.setEnabled(bool(geometry.projected_poles))
        self.workspace_note.setText(
            "Metric preview: blue centerline, grey road edges, yellow pole lines, "
            "green/red projected poles. This is not the final schematic."
        )
        message = (
            f"Built geometry in {geometry.projection.name}: "
            f"{len(geometry.projected_poles)} poles projected"
        )
        if geometry.unplaced_poles:
            message += f", {len(geometry.unplaced_poles)} without Side not placed"
        self.statusBar().showMessage(message)

    def _generate_schematic(self) -> None:
        layout = create_schematic_layout(self.current_geometry)
        self.undo_stack.clear()
        render_schematic(self.route_scene, layout, self.undo_stack)
        self.reset_layout_action.setEnabled(True)
        self.workspace_note.setText(
            "Non-scale schematic: poles use equal visual spacing. Select and drag the road, "
            "individual poles, or labels to edit the drawing."
        )
        self.statusBar().showMessage(
            f"Generated editable schematic with {len(layout.poles)} uniformly spaced poles"
        )

    def _delete_selected(self) -> None:
        selected = [item for item in self.route_scene.selectedItems() if item.parentItem() is None]
        if selected:
            self.undo_stack.push(DeleteItemsCommand(self.route_scene, selected))
            self.statusBar().showMessage(f"Deleted {len(selected)} object(s) - Undo is available")

    def _reset_layout(self) -> None:
        items = editable_scene_items(self.route_scene)
        if not items:
            return
        answer = QMessageBox.question(
            self,
            "Reset schematic layout",
            "Return all schematic objects to their generated positions?\n\n"
            "You can use Undo after resetting.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.undo_stack.push(ResetLayoutCommand(items))
        self.statusBar().showMessage("Schematic layout reset - Undo is available")

    def _update_editor_actions(self) -> None:
        self.delete_action.setEnabled(bool(self.route_scene.selectedItems()))

    def _update_geometry_action(self) -> None:
        self.build_geometry_action.setEnabled(
            self.current_route is not None and bool(self.current_poles)
        )
        self.current_geometry = None
        self.undo_stack.clear()
        self.reset_layout_action.setEnabled(False)
        self.generate_schematic_action.setEnabled(False)

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
        self.current_poles = poles
        self._update_geometry_action()
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
