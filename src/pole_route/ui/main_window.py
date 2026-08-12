"""Main application window."""

from dataclasses import asdict, replace

from pathlib import Path

from PySide6.QtCore import QLocale, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsScene,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QProgressDialog,
    QApplication,
    QVBoxLayout,
    QWidget,
)

from pole_route.domain.blocks import BLOCK_CATALOG
from pole_route.domain.pole import Pole
from pole_route.domain.route import ClassifiedRoute, Route, RouteType
from pole_route.exporters.excel_exporter import (
    ExcelExportError,
    ExcelExportSettings,
    collect_scene_objects,
    export_pages_to_excel,
)
from pole_route.geometry.road_geometry import RoadGeometryError, build_road_network_geometry
from pole_route.geometry.schematic_layout import create_schematic_layout
from pole_route.importers.kml_importer import RouteImportError, inspect_route_file
from pole_route.importers.osm_context import OSMContextError, fetch_osm_context
from pole_route.importers.pole_importer import (
    OPTIONAL_FIELDS,
    PoleImportError,
    inspect_pole_file,
    poles_from_table,
    suggest_column_mapping,
)
from pole_route.project.storage import (
    ProjectFileError,
    load_project_file,
    poles_from_data,
    poles_to_data,
    restore_scene,
    routes_from_data,
    routes_to_data,
    save_project_file,
    scene_to_data,
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
from pole_route.ui.project_info_dialog import ProjectInfoDialog
from pole_route.ui.route_import_dialog import RouteImportDialog, draw_classified_routes_preview
from pole_route.ui.osm_context_dialog import OSMContextDialog
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
        self.export_settings = ExcelExportSettings()
        self.project_path: str | None = None
        self.project_dirty = False
        self._changing_project = False
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._undo_clean_changed)
        self.setWindowTitle("PoleRoute Schematic - V2 Preview")
        self.resize(1100, 720)
        self._build_toolbar()
        self._build_workspace()
        self.statusBar().showMessage("Ready - import an Excel or CSV pole-data file")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Workflow")
        toolbar.setObjectName("workflowToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        self.new_action = QAction("New", self)
        self.new_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self._new_project)
        toolbar.addAction(self.new_action)

        self.open_action = QAction("Open", self)
        self.open_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._choose_project_file)
        toolbar.addAction(self.open_action)

        self.save_action = QAction("Save", self)
        self.save_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._save_project)
        toolbar.addAction(self.save_action)

        self.save_as_action = QAction("Save as", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self._save_project_as)
        toolbar.addAction(self.save_as_action)

        self.project_info_action = QAction("Project info", self)
        self.project_info_action.triggered.connect(self._edit_project_info)
        toolbar.addAction(self.project_info_action)

        toolbar.addSeparator()

        self.import_route_action = QAction("Import route", self)
        self.import_route_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon))
        self.import_route_action.triggered.connect(self._choose_route_file)
        toolbar.addAction(self.import_route_action)

        self.fetch_surroundings_action = QAction("Fetch surroundings", self)
        self.fetch_surroundings_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon)
        )
        self.fetch_surroundings_action.setEnabled(False)
        self.fetch_surroundings_action.triggered.connect(self._fetch_surroundings)
        toolbar.addAction(self.fetch_surroundings_action)

        self.import_poles_action = QAction("Import poles", self)
        self.import_poles_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.import_poles_action.triggered.connect(self._choose_pole_file)
        toolbar.addAction(self.import_poles_action)

        self.build_geometry_action = QAction("Build geometry", self)
        self.build_geometry_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.build_geometry_action.setEnabled(False)
        self.build_geometry_action.triggered.connect(self._build_geometry)
        toolbar.addAction(self.build_geometry_action)

        self.generate_schematic_action = QAction("Generate schematic", self)
        self.generate_schematic_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.generate_schematic_action.setEnabled(False)
        self.generate_schematic_action.triggered.connect(self._generate_schematic)
        toolbar.addAction(self.generate_schematic_action)

        self.same_pole_action = QAction("Same pole", self)
        self.same_pole_action.setEnabled(False)
        self.same_pole_action.triggered.connect(self._mark_selected_rows_as_same_pole)
        toolbar.addAction(self.same_pole_action)

        self.edit_canvas_action = QAction("Edit canvas", self)
        self.edit_canvas_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.edit_canvas_action.setCheckable(True)
        self.edit_canvas_action.setEnabled(False)
        self.edit_canvas_action.toggled.connect(self._toggle_canvas_editor)
        toolbar.addAction(self.edit_canvas_action)

        toolbar.addSeparator()
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        toolbar.addAction(self.undo_action)

        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        toolbar.addAction(self.redo_action)

        self.delete_action = QAction("Delete", self)
        self.delete_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.setEnabled(False)
        self.delete_action.triggered.connect(self._delete_selected)
        toolbar.addAction(self.delete_action)

        self.reset_layout_action = QAction("Reset layout", self)
        self.reset_layout_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.reset_layout_action.setEnabled(False)
        self.reset_layout_action.triggered.connect(self._reset_layout)
        toolbar.addAction(self.reset_layout_action)

        self.stack_poles_action = QAction("Stack poles", self)
        self.stack_poles_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarShadeButton)
        )
        self.stack_poles_action.setEnabled(False)
        self.stack_poles_action.triggered.connect(self._stack_selected_poles)
        toolbar.addAction(self.stack_poles_action)

        toolbar.addSeparator()
        self.drawing_actions: dict[DrawingMode, QAction] = {}
        drawing_group = QActionGroup(self)
        drawing_group.setExclusive(True)
        drawing_icons = {
            DrawingMode.SELECT: QStyle.StandardPixmap.SP_DialogApplyButton,
            DrawingMode.LINE: QStyle.StandardPixmap.SP_MediaSeekForward,
            DrawingMode.RECTANGLE: QStyle.StandardPixmap.SP_TitleBarMaxButton,
            DrawingMode.ELLIPSE: QStyle.StandardPixmap.SP_DialogYesButton,
            DrawingMode.TEXT: QStyle.StandardPixmap.SP_FileDialogInfoView,
        }
        for mode, label in (
            (DrawingMode.SELECT, "Select"),
            (DrawingMode.LINE, "Line"),
            (DrawingMode.RECTANGLE, "Rectangle"),
            (DrawingMode.ELLIPSE, "Ellipse"),
            (DrawingMode.TEXT, "Text"),
        ):
            action = QAction(label, self)
            action.setIcon(self.style().standardIcon(drawing_icons[mode]))
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
        self.blocks_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.blocks_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.blocks_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.blocks_button.setEnabled(False)
        blocks_menu = QMenu(self.blocks_button)
        self.blocks_menu = blocks_menu
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
        self.blocks_toolbar_action = toolbar.addWidget(self.blocks_button)

        self.export_action = QAction("Export Excel", self)
        self.export_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._export_excel)
        toolbar.addAction(self.export_action)
        self._organize_v2_commands(toolbar)

    def _organize_v2_commands(self, workflow_toolbar: QToolBar) -> None:
        """Group existing commands into a V2 menu bar and focused toolbars."""
        project_menu = self.menuBar().addMenu("Project")
        project_menu.setObjectName("projectMenu")
        project_menu.addActions(
            [
                self.new_action,
                self.open_action,
                self.save_action,
                self.save_as_action,
                self.project_info_action,
            ]
        )

        data_menu = self.menuBar().addMenu("Data")
        data_menu.setObjectName("dataMenu")
        data_menu.addActions(
            [
                self.import_route_action,
                self.fetch_surroundings_action,
                self.import_poles_action,
                self.same_pole_action,
            ]
        )

        geometry_menu = self.menuBar().addMenu("Geometry")
        geometry_menu.setObjectName("geometryMenu")
        geometry_menu.addActions(
            [self.build_geometry_action, self.generate_schematic_action]
        )

        drawing_menu = self.menuBar().addMenu("Drawing")
        drawing_menu.setObjectName("drawingMenu")
        drawing_menu.addAction(self.edit_canvas_action)
        drawing_menu.addSeparator()
        drawing_menu.addActions([self.undo_action, self.redo_action, self.delete_action])
        drawing_menu.addActions([self.reset_layout_action, self.stack_poles_action])
        drawing_menu.addSeparator()
        drawing_menu.addActions(list(self.drawing_actions.values()))
        drawing_menu.addMenu(self.blocks_menu)

        output_menu = self.menuBar().addMenu("Output")
        output_menu.setObjectName("outputMenu")
        output_menu.addAction(self.export_action)

        # The first row shows only the normal end-to-end workflow.
        for action in (
            self.save_as_action,
            self.project_info_action,
            self.same_pole_action,
            self.edit_canvas_action,
            self.undo_action,
            self.redo_action,
            self.delete_action,
            self.reset_layout_action,
            self.stack_poles_action,
            *self.drawing_actions.values(),
            self.blocks_toolbar_action,
        ):
            workflow_toolbar.removeAction(action)

        drawing_toolbar = QToolBar("Drawing tools")
        drawing_toolbar.setObjectName("drawingToolbar")
        drawing_toolbar.setMovable(False)
        drawing_toolbar.setIconSize(QSize(18, 18))
        drawing_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        drawing_toolbar.addAction(self.edit_canvas_action)
        drawing_toolbar.addSeparator()
        drawing_toolbar.addActions([self.undo_action, self.redo_action, self.delete_action])
        drawing_toolbar.addActions([self.reset_layout_action, self.stack_poles_action])
        drawing_toolbar.addSeparator()
        drawing_toolbar.addActions(list(self.drawing_actions.values()))
        drawing_toolbar.addWidget(self.blocks_button)
        self.addToolBarBreak()
        self.addToolBar(drawing_toolbar)

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

    def _edit_project_info(self) -> None:
        dialog = ProjectInfoDialog(self.export_settings, self)
        if dialog.exec() != ProjectInfoDialog.DialogCode.Accepted:
            return
        project_title, location, work_description = dialog.values()
        self.export_settings = replace(
            self.export_settings,
            project_title=project_title,
            location=location,
            work_description=work_description,
        )
        self._mark_dirty()

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
        self.fetch_surroundings_action.setEnabled(True)
        self._update_geometry_action()
        self.statusBar().showMessage(
            f"Imported {len(main_routes)} main route(s) and "
            f"{len(self.current_context_routes)} context line(s)"
        )
        self._mark_dirty()

    def _fetch_surroundings(self) -> None:
        """Download and explicitly review OSM context around the main route."""
        if self.current_route is None:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage("Fetching nearby roads and places from OpenStreetMap...")
        try:
            context = fetch_osm_context(self.current_route)
        except OSMContextError as error:
            QMessageBox.warning(self, "OpenStreetMap fetch failed", str(error))
            self.statusBar().showMessage("Could not fetch OpenStreetMap surroundings")
            return
        finally:
            QApplication.restoreOverrideCursor()

        if not context.roads and not context.places:
            QMessageBox.information(
                self,
                "No surroundings found",
                "OpenStreetMap returned no nearby roads or named places for this route.",
            )
            self.statusBar().showMessage("No OpenStreetMap surroundings found")
            return
        dialog = OSMContextDialog(self.current_route, context, self)
        if dialog.exec() != OSMContextDialog.DialogCode.Accepted:
            self.statusBar().showMessage("OpenStreetMap surroundings cancelled")
            return
        discovered = dialog.selected_routes()
        existing_osm_ids = {
            item.route.source_path
            for item in self.current_routes
            if item.route.source_path.startswith("OpenStreetMap:")
        }
        discovered = [
            item for item in discovered if item.route.source_path not in existing_osm_ids
        ]
        self.current_routes.extend(discovered)
        self.current_context_routes.extend(discovered)
        self.show_routes(self.current_routes)
        self.current_geometry = None
        self.generate_schematic_action.setEnabled(False)
        self._update_geometry_action()
        self.statusBar().showMessage(
            f"Added {len(discovered)} nearby road(s); "
            f"reviewed {len(context.places)} named place(s)"
        )
        if discovered:
            self._mark_dirty()

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
        self._mark_dirty()

    def _export_excel(self) -> None:
        source_objects = collect_scene_objects(self.route_scene)
        if not source_objects:
            QMessageBox.warning(self, "Excel export failed", "The canvas has no objects to export.")
            return
        dialog = ExcelExportDialog(
            source_objects, self, initial_settings=self.export_settings
        )
        if dialog.exec() != ExcelExportDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Excel export cancelled")
            return
        self.export_settings = dialog.settings()
        self._mark_dirty()
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
        pages = dialog.export_pages()
        progress = QProgressDialog(
            "Starting Microsoft Excel...", "", 0, len(pages) + 1, self
        )
        progress.setWindowTitle("Exporting Excel")
        progress.setLocale(QLocale.c())
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        def update_progress(current: int, total: int, message: str) -> None:
            progress.setMaximum(total)
            progress.setLabelText(message)
            progress.setValue(current)
            QApplication.processEvents()

        try:
            object_count = export_pages_to_excel(
                pages, path, dialog.settings(), progress_callback=update_progress
            )
        except ExcelExportError as error:
            QMessageBox.warning(self, "Excel export failed", str(error))
            self.statusBar().showMessage("Excel export failed")
            return
        finally:
            progress.close()
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
        self._mark_dirty()

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
        self._mark_dirty()

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

    def _undo_clean_changed(self, clean: bool) -> None:
        if not clean and not self._changing_project:
            self._mark_dirty()

    def _mark_dirty(self) -> None:
        if not self._changing_project:
            self.project_dirty = True
            self._update_window_title()

    def _mark_clean(self) -> None:
        self.project_dirty = False
        self.undo_stack.setClean()
        self._update_window_title()

    def _update_window_title(self) -> None:
        name = Path(self.project_path).stem if self.project_path else "Untitled"
        marker = " *" if self.project_dirty else ""
        self.setWindowTitle(f"PoleRoute Schematic - {name}{marker}")

    def _choose_project_file(self) -> None:
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PoleRoute project", "", "PoleRoute project (*.prs)"
        )
        if path:
            self.open_project(path)

    def _new_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._changing_project = True
        try:
            self.current_route = None
            self.current_routes = []
            self.current_context_routes = []
            self.current_road_width = 6.0
            self.current_poles = []
            self.current_geometry = None
            self.same_pole_groups = []
            self.export_settings = ExcelExportSettings()
            self.project_path = None
            self.route_scene.clear()
            self.route_scene.setSceneRect(0, 0, 1000, 600)
            self.pole_table.setRowCount(0)
            self.undo_stack.clear()
            self.fetch_surroundings_action.setEnabled(False)
            self._update_geometry_action()
            self.generate_schematic_action.setEnabled(False)
            self.workspace_note.setText(
                "Import a route and pole data, then build the metric road-geometry preview."
            )
        finally:
            self._changing_project = False
        self._mark_clean()
        self.statusBar().showMessage("New project")

    def _save_project(self) -> bool:
        return self._write_project(self.project_path) if self.project_path else self._save_project_as()

    def _save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PoleRoute project",
            self.project_path or "PoleRoute-Schematic.prs",
            "PoleRoute project (*.prs)",
        )
        if not path:
            return False
        if not path.lower().endswith(".prs"):
            path += ".prs"
        return self._write_project(path)

    def _write_project(self, path: str | None) -> bool:
        if not path:
            return False
        try:
            save_project_file(
                path,
                {
                    "routes": routes_to_data(self.current_routes),
                    "poles": poles_to_data(self.current_poles),
                    "same_pole_groups": [sorted(group) for group in self.same_pole_groups],
                    "canvas": scene_to_data(self.route_scene),
                    "workspace_note": self.workspace_note.text(),
                    "has_schematic": self.export_action.isEnabled(),
                    "export_settings": asdict(self.export_settings),
                },
            )
        except ProjectFileError as error:
            QMessageBox.warning(self, "Project save failed", str(error))
            return False
        self.project_path = path
        self._mark_clean()
        self.statusBar().showMessage(f"Saved project to {path}")
        return True

    def open_project(self, path: str) -> bool:
        try:
            document = load_project_file(path)
            routes = routes_from_data(document.get("routes", []))
            poles = poles_from_data(document.get("poles", []))
            geometry = build_road_network_geometry(routes, poles) if routes and poles else None
        except (ProjectFileError, RoadGeometryError, KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Project open failed", str(error))
            return False

        self._changing_project = True
        try:
            self.current_routes = routes
            main_routes = [item for item in routes if item.type is RouteType.MAIN_ROUTE]
            self.current_route = main_routes[0].route if main_routes else None
            self.current_context_routes = [
                item for item in routes if item.type is not RouteType.MAIN_ROUTE
            ]
            self.current_road_width = (
                (main_routes[0].width_metres or 6.0) if main_routes else 6.0
            )
            self.current_poles = poles
            self.current_geometry = geometry
            self.same_pole_groups = [
                frozenset(group) for group in document.get("same_pole_groups", [])
            ]
            self.export_settings = ExcelExportSettings(
                **document.get("export_settings", {})
            )
            self.show_poles(poles)
            self._show_same_pole_groups()
            self.undo_stack.clear()
            restore_scene(self.route_scene, document.get("canvas", {}), self.undo_stack)
            self.project_path = path
            has_schematic = bool(document.get("has_schematic"))
            self.build_geometry_action.setEnabled(bool(routes) and bool(poles))
            self.fetch_surroundings_action.setEnabled(bool(main_routes))
            self.generate_schematic_action.setEnabled(bool(geometry and geometry.projected_poles))
            self.reset_layout_action.setEnabled(has_schematic)
            self.edit_canvas_action.setEnabled(has_schematic)
            self.export_action.setEnabled(has_schematic)
            for action in self.drawing_actions.values():
                action.setEnabled(has_schematic)
            self.blocks_button.setEnabled(has_schematic)
            self.workspace_note.setText(document.get("workspace_note", "Project opened"))
            self.canvas.fitInView(
                self.route_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
            )
        finally:
            self._changing_project = False
        self._mark_clean()
        self.statusBar().showMessage(f"Opened project {path}")
        return True

    def _show_same_pole_groups(self) -> None:
        for group in self.same_pole_groups:
            label = " / ".join(sorted(group))
            for row, pole in enumerate(self.current_poles):
                if pole.number in group:
                    self.pole_table.setItem(row, 5, QTableWidgetItem(label))

    def _confirm_discard_changes(self) -> bool:
        if not self.project_dirty:
            return True
        answer = QMessageBox.warning(
            self,
            "Unsaved project",
            "Save changes to the current project before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer is QMessageBox.StandardButton.Cancel:
            return False
        if answer is QMessageBox.StandardButton.Save:
            return self._save_project()
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.isVisible():
            event.accept()
            return
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()
