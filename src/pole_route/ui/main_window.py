"""Main application window."""

from math import atan2, cos, degrees, radians, sin

from PySide6.QtCore import QLocale, QPointF, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QKeySequence, QPen, QUndoStack
from PySide6.QtWidgets import (
    QColorDialog,
    QDockWidget,
    QFileDialog,
    QGraphicsItem,
    QGraphicsScene,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSpinBox,
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
    PropertyChangeCommand,
    ResetLayoutCommand,
    editable_scene_items,
)
from pole_route.ui.geometry_renderer import render_road_geometry
from pole_route.ui.layers_panel import LayersPanel, layer_types
from pole_route.ui.properties_panel import PropertiesPanel
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
        self._build_properties_panel()
        self._build_layers_panel()
        self._build_view_toolbar()
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

        export_action = QAction("Export", self)
        export_action.setEnabled(False)
        toolbar.addAction(export_action)

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

    def _build_properties_panel(self) -> None:
        self.properties_panel = PropertiesPanel(self)
        dock = QDockWidget("Properties", self)
        dock.setObjectName("propertiesDock")
        dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.properties_dock = dock

        self.properties_panel.textCommitted.connect(self._change_selected_text)
        self.properties_panel.colorRequested.connect(self._choose_selected_color)
        self.properties_panel.lineWidthCommitted.connect(self._change_selected_line_width)
        self.properties_panel.lineStyleCommitted.connect(self._change_selected_line_style)
        self.properties_panel.fontSizeCommitted.connect(self._change_selected_font_size)
        self.properties_panel.rotationCommitted.connect(self._rotate_selected_objects)
        self.properties_panel.bringForwardRequested.connect(lambda: self._change_selected_z(1))
        self.properties_panel.sendBackwardRequested.connect(lambda: self._change_selected_z(-1))

    def _build_layers_panel(self) -> None:
        self.layers_panel = LayersPanel(self)
        dock = QDockWidget("Layers", self)
        dock.setObjectName("layersDock")
        dock.setWidget(self.layers_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.tabifyDockWidget(self.properties_dock, dock)
        self.properties_dock.raise_()
        self.layers_panel.visibilityChanged.connect(self._set_layer_visible)
        self.layers_panel.lockChanged.connect(self._set_layer_locked)
        self.layers_panel.selectRequested.connect(self._select_layer)

    def _build_view_toolbar(self) -> None:
        self.addToolBarBreak()
        toolbar = QToolBar("View")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for label, callback in (
            ("Zoom +", self.canvas.zoom_in),
            ("Zoom -", self.canvas.zoom_out),
            ("Fit", self.canvas.fit_scene),
            ("Rotate left", lambda: self._set_canvas_rotation(self.canvas.rotation_degrees - 15)),
            ("Rotate right", lambda: self._set_canvas_rotation(self.canvas.rotation_degrees + 15)),
            ("North up", lambda: self._set_canvas_rotation(0)),
            ("Align selected", self._align_view_to_selected),
        ):
            action = QAction(label, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)
        self.rotation_angle = QSpinBox()
        self.rotation_angle.setLocale(QLocale.c())
        self.rotation_angle.setRange(-180, 180)
        self.rotation_angle.setSuffix(" deg")
        self.rotation_angle.setToolTip("Canvas rotation angle")
        self.rotation_angle.editingFinished.connect(
            lambda: self._set_canvas_rotation(self.rotation_angle.value())
        )
        toolbar.addWidget(self.rotation_angle)

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
        self._set_layer_locked("Roads", True)
        self.canvas.fit_scene()
        QTimer.singleShot(0, self.canvas.fit_scene)
        self.reset_layout_action.setEnabled(True)
        for action in self.drawing_actions.values():
            action.setEnabled(True)
        self.blocks_button.setEnabled(True)
        self.edit_canvas_action.setEnabled(True)
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
        self.properties_panel.show_for_items(self._selected_editor_items())

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

    def _selected_editor_item(self):
        return next(iter(self._selected_editor_items()), None)

    def _selected_editor_items(self):
        return [item for item in self.route_scene.selectedItems() if item.parentItem() is None]

    def _pen_items(self, item):
        if item is None:
            return []
        if hasattr(item, "pen"):
            return [item]
        return [child for child in item.childItems() if hasattr(child, "pen")]

    def _change_selected_text(self, text: str) -> None:
        item = self._selected_editor_item()
        if item is None or not hasattr(item, "text") or item.text() == text:
            return
        self.undo_stack.push(PropertyChangeCommand("Change text", item.setText, item.text(), text))

    def _choose_selected_color(self) -> None:
        item = self._selected_editor_item()
        if item is None:
            return
        initial = item.brush().color() if hasattr(item, "brush") else QColor("#d0d0d0")
        color = QColorDialog.getColor(initial, self, "Choose object color")
        if not color.isValid():
            return
        if hasattr(item, "setBrush") and hasattr(item, "text"):
            before = item.brush().color()
            self.undo_stack.push(
                PropertyChangeCommand(
                    "Change color", lambda value: item.setBrush(QBrush(value)), before, color
                )
            )
            return
        targets = self._pen_items(item)
        before = [QPen(target.pen()) for target in targets]

        def apply(value):
            for target, pen in zip(targets, value, strict=True):
                target.setPen(pen)

        after = []
        for pen in before:
            changed = QPen(pen)
            changed.setColor(color)
            after.append(changed)
        self.undo_stack.push(PropertyChangeCommand("Change color", apply, before, after))

    def _change_selected_line_width(self, width: float) -> None:
        targets = [
            target
            for item in self._selected_editor_items()
            for target in self._pen_items(item)
        ]
        if not targets:
            return
        before = [QPen(target.pen()) for target in targets]
        if all(pen.widthF() == width for pen in before):
            return
        after = []
        for pen in before:
            changed = QPen(pen)
            changed.setWidthF(width)
            after.append(changed)
        self._push_pen_change("Change line width", targets, before, after)

    def _change_selected_line_style(self, style: str) -> None:
        targets = [
            target
            for item in self._selected_editor_items()
            for target in self._pen_items(item)
        ]
        if not targets:
            return
        before = [QPen(target.pen()) for target in targets]
        after = []
        pen_style = Qt.PenStyle.DashLine if style == "dash" else Qt.PenStyle.SolidLine
        for pen in before:
            changed = QPen(pen)
            changed.setStyle(pen_style)
            after.append(changed)
        self._push_pen_change("Change line style", targets, before, after)

    def _push_pen_change(self, description, targets, before, after) -> None:
        def apply(value):
            for target, pen in zip(targets, value, strict=True):
                target.setPen(pen)

        self.undo_stack.push(PropertyChangeCommand(description, apply, before, after))

    def _change_selected_font_size(self, size: int) -> None:
        items = [item for item in self._selected_editor_items() if hasattr(item, "font")]
        if not items:
            return
        before = [(item, item.font()) for item in items]
        after = []
        for item, font in before:
            changed = type(font)(font)
            changed.setPointSize(size)
            after.append((item, changed))

        def apply(values):
            for target, font in values:
                target.setFont(font)

        self.undo_stack.push(PropertyChangeCommand("Change font size", apply, before, after))

    def _change_selected_z(self, delta: float) -> None:
        items = self._selected_editor_items()
        if not items:
            return
        before = [(item, item.zValue()) for item in items]
        after = [(item, value + delta) for item, value in before]

        def apply(values):
            for target, value in values:
                target.setZValue(value)

        self.undo_stack.push(
            PropertyChangeCommand("Change object order", apply, before, after)
        )

    def _rotate_selected_objects(self, angle: float) -> None:
        items = self._selected_editor_items()
        if not items:
            return
        first_angle = items[0].rotation()
        delta = angle - first_angle
        if abs(delta) < 1e-9:
            return
        bounds = items[0].sceneBoundingRect()
        for item in items[1:]:
            bounds = bounds.united(item.sceneBoundingRect())
        pivot = bounds.center()
        before = [
            (item, QPointF(item.pos()), item.rotation(), QPointF(item.transformOriginPoint()))
            for item in items
        ]
        turn = radians(delta)
        after = []
        for item in items:
            scene_center = item.sceneBoundingRect().center()
            offset = scene_center - pivot
            desired_center = QPointF(
                pivot.x() + offset.x() * cos(turn) - offset.y() * sin(turn),
                pivot.y() + offset.x() * sin(turn) + offset.y() * cos(turn),
            )
            origin = item.boundingRect().center()
            item.setTransformOriginPoint(origin)
            item.setRotation(item.rotation() + delta)
            moved_center = item.sceneBoundingRect().center()
            item.setPos(item.pos() + desired_center - moved_center)
            after.append(
                (item, QPointF(item.pos()), item.rotation(), QPointF(item.transformOriginPoint()))
            )

        def apply(states):
            for target, position, rotation, origin in states:
                target.setTransformOriginPoint(origin)
                target.setRotation(rotation)
                target.setPos(position)

        apply(before)
        self.undo_stack.push(PropertyChangeCommand("Rotate objects", apply, before, after))

    def _layer_items(self, name: str):
        types = layer_types(name)
        return [
            item
            for item in self.route_scene.items()
            if item.parentItem() is None and item.data(0) in types
        ]

    def _set_layer_visible(self, name: str, visible: bool) -> None:
        for item in self._layer_items(name):
            item.setVisible(visible)

    def _set_layer_locked(self, name: str, locked: bool) -> None:
        editable_flags = (
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        for item in self._layer_items(name):
            if locked:
                item.setSelected(False)
                item.setFlags(item.flags() & ~editable_flags)
            else:
                item.setFlags(item.flags() | editable_flags)

    def _select_layer(self, name: str) -> None:
        self.route_scene.clearSelection()
        for item in self._layer_items(name):
            if item.isVisible() and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                item.setSelected(True)

    def _set_canvas_rotation(self, angle: float) -> None:
        normalized = int(((angle + 180) % 360) - 180)
        self.canvas.set_rotation(normalized)
        self.rotation_angle.blockSignals(True)
        self.rotation_angle.setValue(normalized)
        self.rotation_angle.blockSignals(False)

    def _align_view_to_selected(self) -> None:
        item = self._selected_editor_item()
        if item is None:
            self.statusBar().showMessage("Select a line, road, or block to align the canvas")
            return
        candidates = [item, *item.childItems()]
        vectors = []
        for candidate in candidates:
            if hasattr(candidate, "line"):
                line = candidate.line()
                start = candidate.mapToScene(line.p1())
                end = candidate.mapToScene(line.p2())
                vectors.append((start, end, line.length()))
            elif hasattr(candidate, "path") and candidate.path().elementCount() >= 2:
                path = candidate.path()
                first = path.elementAt(0)
                last = path.elementAt(path.elementCount() - 1)
                start = candidate.mapToScene(first.x, first.y)
                end = candidate.mapToScene(last.x, last.y)
                vectors.append((start, end, (end - start).manhattanLength()))
        if not vectors:
            self.statusBar().showMessage("The selected object has no direction to align")
            return
        start, end, _length = max(vectors, key=lambda value: value[2])
        angle = degrees(atan2(end.y() - start.y(), end.x() - start.x()))
        self._set_canvas_rotation(-angle)
