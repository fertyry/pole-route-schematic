"""Main application window."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsScene,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pole_route.domain.blocks import BLOCK_CATALOG
from pole_route.domain.pole import Pole
from pole_route.domain.route import ClassifiedRoute, Route, RouteType
from pole_route.exporters.excel_exporter import ExcelExportError, export_scene_to_excel
from pole_route.geometry.road_geometry import RoadGeometryError, build_road_network_geometry
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
from pole_route.ui.drawing_view import DrawingMode, DrawingView
from pole_route.ui.editor_commands import (
    DeleteItemsCommand,
    MoveItemCommand,
    ResetLayoutCommand,
    editable_scene_items,
)
from pole_route.ui.excel_export_dialog import ExcelExportDialog
from pole_route.ui.geometry_renderer import render_road_geometry
from pole_route.ui.route_import_dialog import RouteImportDialog, draw_classified_routes_preview
from pole_route.ui.schematic_renderer import render_schematic
from pole_route.ui.schematic_settings_dialog import SchematicSettingsDialog


class MainWindow(QMainWindow):
    """Top-level window with a placeholder editable-canvas area."""

    def __init__(self) -> None:
        super().__init__()
        self.current_route: Route | None = None
        self.current_routes: list[ClassifiedRoute] = []
        self.current_context_routes: list[ClassifiedRoute] = []
        self.current_road_width = 6.0
        self.current_poles: list[Pole] = []
        self.current_geometry = None
        self.same_pole_groups: list[frozenset[str]] = []
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

        self.same_pole_action = QAction("Same pole", self)
        self.same_pole_action.setEnabled(False)
        self.same_pole_action.triggered.connect(self._mark_selected_rows_as_same_pole)
        toolbar.addAction(self.same_pole_action)

        self.edit_canvas_action = QAction("Edit canvas", self)
        self.edit_canvas_action.setCheckable(True)
        self.edit_canvas_action.setEnabled(False)
        self.edit_canvas_action.toggled.connect(self._toggle_canvas_editor)
        toolbar.addAction(self.edit_canvas_action)

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

        self.stack_poles_action = QAction("Stack poles", self)
        self.stack_poles_action.setEnabled(False)
        self.stack_poles_action.triggered.connect(self._stack_selected_poles)
        toolbar.addAction(self.stack_poles_action)

        toolbar.addSeparator()
        self.drawing_actions: dict[DrawingMode, QAction] = {}
        drawing_group = QActionGroup(self)
        drawing_group.setExclusive(True)
        for mode, label in (
            (DrawingMode.SELECT, "Select"),
            (DrawingMode.LINE, "Line"),
            (DrawingMode.RECTANGLE, "Rectangle"),
            (DrawingMode.ELLIPSE, "Ellipse"),
            (DrawingMode.TEXT, "Text"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setEnabled(False)
            action.triggered.connect(
                lambda _checked, selected_mode=mode: self.canvas.set_mode(selected_mode)
            )
            drawing_group.addAction(action)
            toolbar.addAction(action)
            self.drawing_actions[mode] = action
        self.drawing_actions[DrawingMode.SELECT].setChecked(True)

        self.blocks_button = QToolButton()
        self.blocks_button.setText("Blocks")
        self.blocks_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.blocks_button.setEnabled(False)
        blocks_menu = QMenu(self.blocks_button)
        current_category = None
        for definition in BLOCK_CATALOG:
            if current_category is not None and definition.category != current_category:
                blocks_menu.addSeparator()
            action = blocks_menu.addAction(definition.label)
            action.triggered.connect(
                lambda _checked=False, block_type=definition.type: self._select_block(block_type)
            )
            current_category = definition.category
        self.blocks_button.setMenu(blocks_menu)
        toolbar.addWidget(self.blocks_button)

        self.export_action = QAction("Export Excel", self)
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._export_excel)
        toolbar.addAction(self.export_action)

    def _build_workspace(self) -> None:
        self.route_scene = QGraphicsScene(self)
        self.route_scene.selectionChanged.connect(self._update_editor_actions)
        self.route_scene.setSceneRect(0, 0, 1000, 600)

        self.canvas = DrawingView(self.route_scene, self.undo_stack)
        self.canvas.setObjectName("schematicCanvas")
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.heading = QLabel("Schematic canvas")
        self.heading.setObjectName("canvasHeading")
        self.heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heading.setStyleSheet("font-size: 20px; font-weight: 600; padding: 6px;")

        self.workspace_note = QLabel(
            "Import a route and pole data, then build the metric road-geometry preview."
        )
        self.workspace_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.workspace_note.setWordWrap(True)

        self.pole_table = QTableWidget(0, 6)
        self.pole_table.setObjectName("poleTable")
        self.pole_table.setHorizontalHeaderLabels(
            ["Pole No.", "Latitude", "Longitude", "Detail", "Side", "Physical pole"]
        )
        self.pole_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pole_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pole_table.itemSelectionChanged.connect(self._update_same_pole_action)
        self.pole_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.pole_table)
        self.splitter.addWidget(self.canvas)
        self.splitter.setSizes([240, 360])

        layout = QVBoxLayout()
        layout.addWidget(self.heading)
        layout.addWidget(self.workspace_note)
        layout.addWidget(self.splitter, 1)

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
            classified = dialog.classified_routes()
            main_routes = [item for item in classified if item.type is RouteType.MAIN_ROUTE]
            route = main_routes[0].route
        except RouteImportError as error:
            QMessageBox.warning(self, "Route import failed", str(error))
            self.statusBar().showMessage("Route import failed")
            return

        self.show_routes(classified)
        self.current_route = route
        self.current_routes = classified
        self.current_context_routes = [item for item in classified if item.type is not RouteType.MAIN_ROUTE]
        self.current_road_width = main_routes[0].width_metres or 6.0
        self._update_geometry_action()
        self.statusBar().showMessage(
            f"Imported {len(main_routes)} main route(s) and "
            f"{len(self.current_context_routes)} context line(s)"
        )

    def show_routes(self, routes: list[ClassifiedRoute]) -> None:
        """Display every confirmed LineString in one geographic preview."""
        draw_classified_routes_preview(
            self.route_scene,
            [(item.route, item.type) for item in routes],
            960,
            540,
        )

    def _build_geometry(self) -> None:
        try:
            geometry = build_road_network_geometry(self.current_routes, self.current_poles)
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
            f"Built {len(geometry.roads)} road geometries in {geometry.projection.name}: "
            f"{len(geometry.projected_poles)} poles projected"
        )
        if geometry.unplaced_poles:
            message += f", {len(geometry.unplaced_poles)} without Side not placed"
        self.statusBar().showMessage(message)

    def _generate_schematic(self) -> None:
        dialog = SchematicSettingsDialog(self)
        if dialog.exec() != SchematicSettingsDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Schematic generation cancelled")
            return
        layout_mode = dialog.layout_mode()
        spacing_mode = dialog.spacing_mode()
        layout = create_schematic_layout(
            self.current_geometry,
            spacing_mode,
            layout_mode,
            tuple(self.same_pole_groups),
        )
        self.undo_stack.clear()
        render_schematic(self.route_scene, layout, self.undo_stack)
        self.reset_layout_action.setEnabled(True)
        for action in self.drawing_actions.values():
            action.setEnabled(True)
        self.blocks_button.setEnabled(True)
        self.edit_canvas_action.setEnabled(True)
        self.export_action.setEnabled(True)
        self.drawing_actions[DrawingMode.SELECT].setChecked(True)
        self.canvas.set_mode(DrawingMode.SELECT)
        spacing_description = layout_mode.value.replace("_", " ")
        self.workspace_note.setText(
            f"Non-scale schematic using {spacing_description}. Select and drag the road, "
            "individual poles, labels, or drawing objects to edit."
        )
        self.statusBar().showMessage(
            f"Generated editable schematic with {len(layout.poles)} poles ({spacing_description})"
        )

    def _export_excel(self) -> None:
        dialog = ExcelExportDialog(self.route_scene, self)
        if dialog.exec() != ExcelExportDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Excel export cancelled")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export editable Excel drawing",
            "PoleRoute-Schematic.xlsx",
            "Excel workbook (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            object_count = export_scene_to_excel(self.route_scene, path, dialog.settings())
        except ExcelExportError as error:
            QMessageBox.warning(self, "Excel export failed", str(error))
            self.statusBar().showMessage("Excel export failed")
            return
        self.statusBar().showMessage(
            f"Exported {object_count} editable object(s) to {path}"
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
        selected_poles = [
            item for item in self.route_scene.selectedItems() if item.data(0) == "pole"
        ]
        self.stack_poles_action.setEnabled(len(selected_poles) >= 2)

    def _stack_selected_poles(self) -> None:
        poles = [item for item in self.route_scene.selectedItems() if item.data(0) == "pole"]
        if len(poles) < 2:
            return
        target = poles[0].pos()
        moved = 0
        for pole in poles[1:]:
            before = pole.pos()
            if before == target:
                continue
            pole.setPos(target)
            self.undo_stack.push(MoveItemCommand(pole, before, target))
            moved += 1
        self.statusBar().showMessage(
            f"Stacked {moved + 1} selected poles - labels remain separately editable"
        )

    def _update_geometry_action(self) -> None:
        self.build_geometry_action.setEnabled(
            bool(self.current_routes) and bool(self.current_poles)
        )
        self.current_geometry = None
        self.undo_stack.clear()
        self.reset_layout_action.setEnabled(False)
        for action in self.drawing_actions.values():
            action.setEnabled(False)
        self.blocks_button.setEnabled(False)
        self.edit_canvas_action.setChecked(False)
        self.edit_canvas_action.setEnabled(False)
        self.export_action.setEnabled(False)
        self.drawing_actions[DrawingMode.SELECT].setChecked(True)
        self.canvas.set_mode(DrawingMode.SELECT)

    def _select_block(self, block_type) -> None:
        for action in self.drawing_actions.values():
            action.setChecked(False)
        self.canvas.set_block_mode(block_type)
        self.statusBar().showMessage(
            f"{block_type.value.replace('_', ' ').title()}: drag from the start/connection "
            "point to the end; hold Alt to disable road snapping"
        )
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
        self.same_pole_groups = []
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
                "",
            )
            for column_index, value in enumerate(values):
                self.pole_table.setItem(row_index, column_index, QTableWidgetItem(value))

    def _update_same_pole_action(self) -> None:
        rows = {index.row() for index in self.pole_table.selectedIndexes()}
        self.same_pole_action.setEnabled(len(rows) >= 2)

    def _mark_selected_rows_as_same_pole(self) -> None:
        rows = sorted({index.row() for index in self.pole_table.selectedIndexes()})
        if len(rows) < 2:
            return
        numbers = frozenset(self.current_poles[row].number for row in rows)
        merged = set(numbers)
        remaining = []
        for group in self.same_pole_groups:
            if group & numbers:
                merged.update(group)
            else:
                remaining.append(group)
        group = frozenset(merged)
        self.same_pole_groups = [*remaining, group]
        label = " / ".join(sorted(group))
        for row, pole in enumerate(self.current_poles):
            if pole.number in group:
                self.pole_table.setItem(row, 5, QTableWidgetItem(label))
        self.statusBar().showMessage(
            f"Marked {len(group)} records as one physical pole; regenerate the schematic"
        )

    def _toggle_canvas_editor(self, enabled: bool) -> None:
        self.heading.setVisible(not enabled)
        self.workspace_note.setVisible(not enabled)
        self.pole_table.setVisible(not enabled)
        self.edit_canvas_action.setText("Exit canvas" if enabled else "Edit canvas")
        if enabled:
            self.splitter.setSizes([0, max(self.height(), 700)])
            self.canvas.fitInView(self.route_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.splitter.setSizes([240, 600])
