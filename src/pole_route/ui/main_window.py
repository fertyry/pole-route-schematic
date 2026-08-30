"""Main application window."""

from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings, QSize, Qt, QThread
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGraphicsScene,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pole_route.cad import (
    AutoCADConnection,
    AutoCADConnectionError,
    CadReadbackError,
    ComCadGateway,
    build_pole_overlay_plan,
    read_latest_pole_offset,
    read_latest_route,
    read_managed_pole_positions,
    update_managed_poles,
)
from pole_route.diagnostics.fetch_benchmark import (
    FetchRunStart,
    append_fetch_record,
    build_fetch_record,
    start_fetch_run,
)
from pole_route.domain.blocks import BLOCK_CATALOG
from pole_route.domain.context import (
    ContextFeature,
    FetchCoverageStatus,
    OSMContext,
)
from pole_route.domain.pea_asset import PEAAsset, PEAAssetMatch, merge_pea_assets
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import PEAPoleOrdering
from pole_route.domain.physical_pole import build_physical_pole_mapping
from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, Route, RouteType
from pole_route.exporters.dxf_exporter import (
    DxfExportError,
    export_edited_dxf_with_sheet_layouts,
    export_geometry_to_dxf,
)
from pole_route.exporters.excel_exporter import (
    ExcelExportError,
    ExcelExportSettings,
    collect_scene_objects,
    export_pages_to_excel,
)
from pole_route.exporters.kml_qc_exporter import (
    KMLQCExportError,
    KMLQCLaunchError,
    export_pea_qc_kml,
    launch_kml,
    pea_qc_kml_path,
)
from pole_route.exporters.pea_asset_kml_qc_exporter import (
    export_pea_asset_qc_kml,
    pea_asset_qc_kml_path,
)
from pole_route.geometry.pea_asset_matching import match_pea_assets
from pole_route.geometry.pea_linear_reference import reference_pea_poles
from pole_route.geometry.road_geometry import RoadGeometryError, build_road_network_geometry
from pole_route.geometry.schematic_layout import create_schematic_layout
from pole_route.importers.asset_importer import (
    FIELD_LABELS as ASSET_FIELD_LABELS,
)
from pole_route.importers.asset_importer import (
    HEADER_ALIASES as ASSET_HEADER_ALIASES,
)
from pole_route.importers.asset_importer import (
    REQUIRED_FIELDS as ASSET_REQUIRED_FIELDS,
)
from pole_route.importers.asset_importer import (
    AssetImportError,
    assets_from_table,
    inspect_asset_file,
    suggest_asset_mapping,
)
from pole_route.importers.edited_dxf_importer import (
    EditedDxfImportError,
    inspect_edited_dxf,
)
from pole_route.importers.kml_importer import RouteImportError, inspect_route_file
from pole_route.importers.osm_context import prepare_context_features
from pole_route.importers.pea_assets import ASSET_PROFILES, import_pea_assets
from pole_route.importers.pea_gis import (
    DS_POLE_PROFILE,
    PEAGISImportError,
    discover_pea_workbook,
    import_ds_poles,
)
from pole_route.importers.pole_importer import (
    FIELD_LABELS as POLE_FIELD_LABELS,
)
from pole_route.importers.pole_importer import (
    HEADER_ALIASES as POLE_HEADER_ALIASES,
)
from pole_route.importers.pole_importer import (
    OPTIONAL_FIELDS,
    PoleImportError,
    inspect_pole_file,
    poles_from_table,
    suggest_column_mapping,
)
from pole_route.importers.pole_importer import (
    REQUIRED_FIELDS as POLE_REQUIRED_FIELDS,
)
from pole_route.project.storage import (
    ProjectFileError,
    load_project_file,
    osm_context_from_data,
    osm_context_to_data,
    osm_features_from_data,
    osm_features_to_data,
    pea_asset_matches_from_data,
    pea_asset_matches_to_data,
    pea_assets_from_data,
    pea_assets_to_data,
    pea_pole_ordering_from_data,
    pea_pole_ordering_to_data,
    pea_poles_from_data,
    pea_poles_to_data,
    poles_from_data,
    poles_to_data,
    restore_scene,
    routes_from_data,
    routes_to_data,
    save_project_file,
    scene_to_data,
)
from pole_route.project.working_directory import WorkingDirectory
from pole_route.ui.asset_column_mapping_dialog import AssetColumnMappingDialog
from pole_route.ui.column_mapping_dialog import ColumnMappingDialog
from pole_route.ui.drawing_view import DrawingMode, DrawingView
from pole_route.ui.duplicate_pole_dialog import (
    ACCESSORY,
    SAME_POLE,
    TRANSFORMER_RACK,
    DuplicatePoleDialog,
    find_close_pole_groups,
)
from pole_route.ui.edited_dxf_dialog import EditedDxfDialog
from pole_route.ui.editor_commands import (
    DeleteItemsCommand,
    MoveItemCommand,
    ResetLayoutCommand,
    editable_scene_items,
)
from pole_route.ui.excel_export_dialog import ExcelExportDialog
from pole_route.ui.fetch_diagnostics_dialog import FetchDiagnosticsDialog
from pole_route.ui.geometry_renderer import render_road_geometry
from pole_route.ui.osm_context_dialog import OSMContextDialog
from pole_route.ui.osm_context_worker import OSMContextWorker
from pole_route.ui.pea_asset_review_dialog import PEAAssetReviewDialog
from pole_route.ui.pea_pole_review_dialog import PEAPoleReviewDialog
from pole_route.ui.pea_sheet_selection_dialog import PEASheetSelectionDialog
from pole_route.ui.project_info_dialog import ProjectInfoDialog
from pole_route.ui.route_import_dialog import RouteImportDialog, draw_classified_routes_preview
from pole_route.ui.scene_lifecycle import clear_scene
from pole_route.ui.schematic_renderer import render_schematic
from pole_route.ui.schematic_settings_dialog import SchematicSettingsDialog
from pole_route.ui.tabular_source_dialog import TabularSourceDialog


class MainWindow(QMainWindow):
    """Top-level window with a placeholder editable-canvas area."""

    def __init__(self) -> None:
        super().__init__()
        self.current_route: Route | None = None
        self.current_routes: list[ClassifiedRoute] = []
        self.current_context_routes: list[ClassifiedRoute] = []
        self.current_osm_features: list[ContextFeature] = []
        self.surrounding_candidates: OSMContext | None = None
        self.current_road_width = 6.0
        self.current_poles: list[Pole] = []
        self.current_pea_poles: list[PEAPoleRecord] = []
        self.current_pea_ordering: PEAPoleOrdering | None = None
        self.current_pea_assets: list[PEAAsset] = []
        self.current_pea_asset_matches: list[PEAAssetMatch] = []
        self.current_geometry = None
        self.same_pole_groups: list[frozenset[str]] = []
        self.transformer_rack_groups: list[frozenset[str]] = []
        self.transformer_rack_leg_pairs: list[tuple[str, str]] = []
        self.edited_dxf: dict | None = None
        self.export_settings = ExcelExportSettings()
        self.project_path: str | None = None
        self.project_dirty = False
        self._changing_project = False
        self.working_directory = WorkingDirectory()
        self.autocad_connection = AutoCADConnection()
        self._cad_route_points: tuple[tuple[float, float], ...] | None = None
        self._cad_pole_offset: tuple[tuple[float, float], ...] | None = None
        self.undo_stack = QUndoStack(self)
        self._osm_thread: QThread | None = None
        self._osm_worker: OSMContextWorker | None = None
        self._osm_progress: QProgressDialog | None = None
        self._pending_osm_context = None
        self._pending_osm_error: str | None = None
        self._pending_osm_cancelled = False
        self._pending_fetch_benchmark: FetchRunStart | None = None
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

        self.fetch_surroundings_action = QAction("Refresh surroundings", self)
        self.fetch_surroundings_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon)
        )
        self.fetch_surroundings_action.setEnabled(False)
        self.fetch_surroundings_action.triggered.connect(self._fetch_surroundings)
        toolbar.addAction(self.fetch_surroundings_action)

        self.review_surroundings_action = QAction("Review surroundings", self)
        self.review_surroundings_action.setEnabled(False)
        self.review_surroundings_action.triggered.connect(self._review_cached_surroundings)
        toolbar.addAction(self.review_surroundings_action)

        self.retry_surroundings_action = QAction("Retry failed areas", self)
        self.retry_surroundings_action.setEnabled(False)
        self.retry_surroundings_action.triggered.connect(self._retry_failed_surroundings)
        toolbar.addAction(self.retry_surroundings_action)

        self.overture_buildings_action = QAction("Use Overture building supplements", self)
        self.overture_buildings_action.setCheckable(True)
        self.overture_buildings_action.setChecked(
            QSettings().value("surroundings/use_overture_buildings", True, type=bool)
        )
        self.overture_buildings_action.toggled.connect(
            lambda enabled: QSettings().setValue(
                "surroundings/use_overture_buildings", enabled
            )
        )

        self.overture_places_action = QAction("Use Overture Places", self)
        self.overture_places_action.setCheckable(True)
        self.overture_places_action.setChecked(
            QSettings().value("surroundings/use_overture_places", True, type=bool)
        )
        self.overture_places_action.toggled.connect(
            lambda enabled: QSettings().setValue(
                "surroundings/use_overture_places", enabled
            )
        )

        self.view_fetch_diagnostics_action = QAction("View Fetch Diagnostics", self)
        self.view_fetch_diagnostics_action.triggered.connect(self._view_fetch_diagnostics)

        primary_toolbar = QToolBar("Import and QC")
        primary_toolbar.setObjectName("importQcToolbar")
        primary_toolbar.setMovable(False)
        primary_toolbar.setIconSize(QSize(20, 20))
        primary_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBarBreak()
        self.addToolBar(primary_toolbar)

        self.import_poles_action = QAction("Import poles", self)
        self.import_poles_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.import_poles_action.triggered.connect(self._choose_pole_file)
        primary_toolbar.addAction(self.import_poles_action)

        self.import_assets_action = QAction("Import assets", self)
        self.import_assets_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.import_assets_action.triggered.connect(self._choose_asset_file)
        primary_toolbar.addAction(self.import_assets_action)

        self.import_pea_gis_action = QAction("Import PEA GIS Data", self)
        self.import_pea_gis_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.import_pea_gis_action.triggered.connect(self._choose_pea_gis_file)
        primary_toolbar.addAction(self.import_pea_gis_action)

        self.review_pea_order_action = QAction("Review pole order", self)
        self.review_pea_order_action.setToolTip(
            "Review station/order for the current PEA GIS pole dataset"
        )
        self.review_pea_order_action.setEnabled(False)
        self.review_pea_order_action.triggered.connect(self._review_pea_pole_order)
        primary_toolbar.addAction(self.review_pea_order_action)

        self.review_pea_assets_action = QAction("Review Assets", self)
        self.review_pea_assets_action.setEnabled(False)
        self.review_pea_assets_action.triggered.connect(self._review_pea_assets)
        primary_toolbar.addAction(self.review_pea_assets_action)

        self.check_google_earth_action = QAction("Check Pole QC", self)
        self.check_google_earth_action.setEnabled(False)
        self.check_google_earth_action.triggered.connect(
            self._check_pea_qc_in_google_earth
        )
        primary_toolbar.addAction(self.check_google_earth_action)

        self.check_pea_assets_google_earth_action = QAction(
            "Check Asset QC", self
        )
        self.check_pea_assets_google_earth_action.setEnabled(False)
        self.check_pea_assets_google_earth_action.triggered.connect(
            self._check_pea_assets_in_google_earth
        )
        primary_toolbar.addAction(self.check_pea_assets_google_earth_action)

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

        self.export_dxf_action = QAction("Export DXF", self)
        self.export_dxf_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        )
        self.export_dxf_action.setEnabled(False)
        self.export_dxf_action.triggered.connect(self._export_dxf)
        toolbar.addAction(self.export_dxf_action)

        self.import_edited_dxf_action = QAction("Import edited DXF", self)
        self.import_edited_dxf_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.import_edited_dxf_action.setEnabled(False)
        self.import_edited_dxf_action.triggered.connect(self._import_edited_dxf)
        toolbar.addAction(self.import_edited_dxf_action)

        self.create_cad_sheets_action = QAction("Create CAD sheets", self)
        self.create_cad_sheets_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.create_cad_sheets_action.setEnabled(False)
        self.create_cad_sheets_action.triggered.connect(self._create_cad_sheets)
        toolbar.addAction(self.create_cad_sheets_action)

        self.connect_autocad_action = QAction("Connect AutoCAD", self)
        self.connect_autocad_action.triggered.connect(self._connect_autocad)
        self.read_cad_route_action = QAction("Read Route", self)
        self.read_cad_route_action.setEnabled(False)
        self.read_cad_route_action.triggered.connect(self._read_cad_route)
        self.read_cad_offset_action = QAction("Read Pole Offset", self)
        self.read_cad_offset_action.setEnabled(False)
        self.read_cad_offset_action.triggered.connect(self._read_cad_pole_offset)
        self.update_cad_poles_action = QAction("Update Poles", self)
        self.update_cad_poles_action.setEnabled(False)
        self.update_cad_poles_action.triggered.connect(self._update_cad_poles)
        self.read_cad_poles_action = QAction("Read Pole Positions", self)
        self.read_cad_poles_action.setEnabled(False)
        self.read_cad_poles_action.triggered.connect(self._read_cad_pole_positions)
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
                self.retry_surroundings_action,
                self.overture_buildings_action,
                self.overture_places_action,
                self.import_poles_action,
                self.import_pea_gis_action,
                self.review_pea_order_action,
                self.check_google_earth_action,
                self.same_pole_action,
            ]
        )
        diagnostics_menu = data_menu.addMenu("Diagnostics")
        diagnostics_menu.addAction(self.view_fetch_diagnostics_action)

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
        output_menu.addAction(self.export_dxf_action)
        output_menu.addAction(self.import_edited_dxf_action)
        output_menu.addAction(self.create_cad_sheets_action)

        cad_menu = self.menuBar().addMenu("AutoCAD")
        cad_menu.setObjectName("autoCadMenu")
        cad_menu.addAction(self.connect_autocad_action)
        cad_menu.addSeparator()
        cad_menu.addActions(
            [
                self.read_cad_route_action,
                self.read_cad_offset_action,
                self.update_cad_poles_action,
                self.read_cad_poles_action,
            ]
        )

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
            "Import a route, then build the base geometry. Pole data is optional."
        )
        self.workspace_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.workspace_note.setWordWrap(True)

        self.pole_table = QTableWidget(0, 8)
        self.pole_table.setObjectName("poleTable")
        self.pole_table.setHorizontalHeaderLabels(
            [
                "Pole No.",
                "Latitude",
                "Longitude",
                "Detail",
                "Installed Qty.",
                "Side",
                "Physical pole",
                "P Label",
            ]
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
            self.working_directory.initial_path(),
            "Google Earth route (*.kml *.kmz)",
        )
        if path:
            self.working_directory.remember_file(path)
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
        self.surrounding_candidates = None
        self.review_surroundings_action.setEnabled(False)
        self.retry_surroundings_action.setEnabled(False)
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
        self._start_surroundings_fetch(None)

    def _retry_failed_surroundings(self) -> None:
        """Fetch only unresolved intervals in the current candidate snapshot."""
        if self.surrounding_candidates is None:
            return
        self._start_surroundings_fetch(self.surrounding_candidates)

    def _start_surroundings_fetch(self, retry_context: OSMContext | None) -> None:
        if self.current_route is None or self._osm_thread is not None:
            return
        self.fetch_surroundings_action.setEnabled(False)
        self.retry_surroundings_action.setEnabled(False)
        self.statusBar().showMessage(
            "Retrying unresolved surroundings..."
            if retry_context is not None
            else "Fetching nearby roads and places from OpenStreetMap..."
        )

        progress = QProgressDialog(
            "Fetching nearby roads, sois, and places from OpenStreetMap...",
            "Cancel",
            0,
            1,
            self,
        )
        progress.setObjectName("osmFetchProgress")
        progress.setWindowTitle("Fetching surroundings")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        self._osm_progress = progress
        self._pending_osm_context = None
        self._pending_osm_error = None
        self._pending_osm_cancelled = False
        self._pending_fetch_benchmark = start_fetch_run(
            "retry_failed_areas" if retry_context is not None else "refresh"
        )

        thread = QThread(self)
        worker = OSMContextWorker(
            self.current_route,
            include_overture=self.overture_buildings_action.isChecked(),
            include_places=self.overture_places_action.isChecked(),
            retry_context=retry_context,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._surroundings_ready)
        worker.failed.connect(self._surroundings_failed)
        worker.cancelled.connect(self._surroundings_cancelled)
        worker.progress.connect(self._surroundings_progress)
        progress.canceled.connect(self._cancel_surroundings_fetch)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._surroundings_fetch_finished)
        thread.finished.connect(thread.deleteLater)
        self._osm_thread = thread
        self._osm_worker = worker
        progress.show()
        thread.start()

    def _review_cached_surroundings(self) -> None:
        """Review the last complete candidate snapshot without network access."""

        if self.surrounding_candidates is None or self.current_route is None:
            return
        self._review_surroundings(self.surrounding_candidates)

    def _surroundings_failed(self, message: str) -> None:
        self._pending_osm_error = message

    def _surroundings_ready(self, context) -> None:
        self._pending_osm_context = context

    def _surroundings_progress(self, message: str, completed: int, total: int) -> None:
        progress = self._osm_progress
        if progress is None:
            return
        progress.setLabelText(message)
        progress.setRange(0, max(1, total))
        progress.setValue(min(completed, total))

    def _cancel_surroundings_fetch(self) -> None:
        if self._osm_worker is not None:
            # Event.set() is thread-safe; calling directly avoids a queued slot being
            # delayed until the worker's blocking network operation returns.
            self._osm_worker.cancel()
        if self._osm_progress is not None:
            self._osm_progress.setLabelText("Cancelling after the current request...")

    def _surroundings_cancelled(self) -> None:
        self._pending_osm_cancelled = True

    def _review_surroundings(self, context) -> None:
        if context.warnings:
            QMessageBox.warning(
                self, "Some surroundings are unavailable", "\n".join(context.warnings)
            )
        if not context.roads and not context.places and not context.features:
            QMessageBox.information(
                self,
                "No surroundings found",
                "OpenStreetMap returned no nearby surroundings for this route.",
            )
            self.statusBar().showMessage("No OpenStreetMap surroundings found")
            return
        dialog = OSMContextDialog(self.current_route, context, self)
        if dialog.exec() != OSMContextDialog.DialogCode.Accepted:
            self.statusBar().showMessage("OpenStreetMap surroundings cancelled")
            return
        discovered = dialog.selected_routes()
        selected_features = dialog.selected_features()
        # Replace only previously accepted OSM roads. Manually imported context
        # routes remain untouched, and accepting an empty selection clears OSM roads.
        retained = [
            item for item in self.current_routes
            if not item.route.source_path.startswith("OpenStreetMap:")
        ]
        unique_roads = {item.route.source_path: item for item in discovered}
        self.current_routes = retained + list(unique_roads.values())
        self.current_context_routes = [
            item for item in self.current_routes if item.type is not RouteType.MAIN_ROUTE
        ]
        # A confirmed re-fetch replaces the accepted non-road feature snapshot.
        # Category is part of identity because one OSM object may legitimately
        # represent more than one reviewed semantic feature.
        unique_features: dict[str, ContextFeature] = {}
        for feature in selected_features:
            unique_features[feature.feature_key] = feature
        features_changed = self.current_osm_features != list(unique_features.values())
        self.current_osm_features = list(unique_features.values())
        if self.current_routes:
            self.show_routes(self.current_routes)
        self.current_geometry = None
        self.generate_schematic_action.setEnabled(False)
        self._update_geometry_action()
        self.statusBar().showMessage(
            f"Added {len(discovered)} nearby road(s) and "
            f"accepted {len(self.current_osm_features)} OSM feature(s)"
        )
        if discovered or features_changed:
            self._mark_dirty()

    def _surroundings_fetch_finished(self) -> None:
        self._osm_thread = None
        self._osm_worker = None
        self._close_osm_progress()
        self.fetch_surroundings_action.setEnabled(self.current_route is not None)
        error = self._pending_osm_error
        context = self._pending_osm_context
        cancelled = self._pending_osm_cancelled
        benchmark = self._pending_fetch_benchmark
        self._pending_osm_error = None
        self._pending_osm_context = None
        self._pending_osm_cancelled = False
        self._pending_fetch_benchmark = None
        self.retry_surroundings_action.setEnabled(
            self.surrounding_candidates is not None and any(
                item.status is FetchCoverageStatus.FAILED
                for item in getattr(self.surrounding_candidates, "coverage", ())
            )
        )
        self._record_fetch_benchmark(
            benchmark,
            context,
            outcome="CANCELLED" if cancelled else ("FAILED" if error is not None else None),
            error=error or "",
        )
        if cancelled:
            self.statusBar().showMessage("Surroundings fetch cancelled; existing context unchanged")
        elif error is not None:
            QMessageBox.warning(self, "OpenStreetMap fetch failed", error)
            self.statusBar().showMessage("Could not fetch OpenStreetMap surroundings")
        elif context is not None:
            # Publish candidates only after a complete worker result. Failure and
            # cancellation therefore preserve both prior candidates and accepted data.
            self.surrounding_candidates = context
            self.review_surroundings_action.setEnabled(True)
            self.retry_surroundings_action.setEnabled(any(
                item.status is FetchCoverageStatus.FAILED
                for item in getattr(context, "coverage", ())
            ))
            self._mark_dirty()
            self._review_surroundings(context)

    def _record_fetch_benchmark(
        self,
        started: FetchRunStart | None,
        context: OSMContext | None,
        *,
        outcome: str | None = None,
        error: str = "",
    ) -> None:
        """Append diagnostics without changing fetch, candidates, or accepted state."""

        if started is None or self.current_route is None or not self.project_path:
            return
        try:
            record = build_fetch_record(
                started,
                route=self.current_route,
                context=context,
                project_path=self.project_path,
                project_title=self.export_settings.project_title,
                accepted_count=len(self.current_context_routes) + len(self.current_osm_features),
                outcome=outcome,
                error=error,
            )
            append_fetch_record(self.project_path, record)
        except (OSError, TypeError, ValueError) as diagnostic_error:
            self.statusBar().showMessage(
                f"Surroundings finished; diagnostics could not be written: {diagnostic_error}"
            )

    def _view_fetch_diagnostics(self) -> None:
        if not self.project_path:
            QMessageBox.information(
                self,
                "Fetch Diagnostics",
                "Save the project first. Fetch diagnostics begin once the project has a folder.",
            )
            return
        FetchDiagnosticsDialog(self.project_path, self).exec()

    def _close_osm_progress(self) -> None:
        if self._osm_progress is not None:
            self._osm_progress.close()
            self._osm_progress.deleteLater()
            self._osm_progress = None

    def show_routes(self, routes: list[ClassifiedRoute]) -> None:
        """Display every confirmed LineString in one geographic preview."""
        draw_classified_routes_preview(
            self.route_scene,
            [(item.route, item.type) for item in routes],
            960,
            540,
            tuple(self.current_osm_features),
        )

    def _build_geometry(self) -> None:
        try:
            geometry = build_road_network_geometry(self.current_routes, self.current_poles)
        except RoadGeometryError as error:
            QMessageBox.warning(self, "Geometry build failed", str(error))
            self.statusBar().showMessage("Geometry build failed")
            return

        render_road_geometry(
            self.route_scene, geometry, osm_features=tuple(self.current_osm_features)
        )
        self.current_geometry = geometry
        self._set_cad_actions_enabled(self.autocad_connection.connected)
        self.export_dxf_action.setEnabled(True)
        self.import_edited_dxf_action.setEnabled(True)
        self.generate_schematic_action.setEnabled(bool(geometry.roads))
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
        if geometry.skipped_context_routes:
            message += f", {len(geometry.skipped_context_routes)} invalid context road(s) skipped"
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
            tuple(self.transformer_rack_groups),
        )
        self.undo_stack.clear()
        render_schematic(
            self.route_scene,
            layout,
            self.undo_stack,
            tuple(self.current_osm_features),
            self.current_geometry,
        )
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
            self.working_directory.initial_path("PoleRoute-Schematic.xlsx"),
            "Excel workbook (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        self.working_directory.remember_file(path)
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

    def _export_dxf(self) -> None:
        """Export the built UTM geometry for downstream AutoCAD drafting."""
        if self.current_geometry is None:
            QMessageBox.warning(
                self,
                "DXF export failed",
                "Build geometry before exporting a metric CAD drawing.",
            )
            return
        sheet_choice = QMessageBox.question(
            self,
            "CAD export workflow",
            "Create A4 sheet layouts now?\n\n"
            "Yes: export Model Space and ready-to-print A4 sheets.\n"
            "No: export Model Space only, for editing in CAD before sheet cutting.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if sheet_choice is QMessageBox.StandardButton.Cancel:
            return
        include_sheet_layouts = sheet_choice is QMessageBox.StandardButton.Yes
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export metric AutoCAD drawing",
            self.working_directory.initial_path("PoleRoute-Schematic.dxf"),
            "AutoCAD DXF (*.dxf)",
        )
        if not path:
            return
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        self.working_directory.remember_file(path)
        try:
            object_count = export_geometry_to_dxf(
                self.current_geometry,
                path,
                self.export_settings,
                include_sheet_layouts=include_sheet_layouts,
                same_pole_groups=tuple(self.same_pole_groups),
                transformer_rack_groups=tuple(self.transformer_rack_groups),
                transformer_rack_leg_pairs=tuple(
                    self.transformer_rack_leg_pairs
                ),
                osm_features=tuple(self.current_osm_features),
            )
        except DxfExportError as error:
            QMessageBox.warning(self, "DXF export failed", str(error))
            self.statusBar().showMessage("DXF export failed")
            return
        workflow = "with A4 sheets" if include_sheet_layouts else "Model Space only"
        self.statusBar().showMessage(
            f"Exported {object_count} metric CAD object(s) ({workflow}) to {path}"
        )

    def _connect_autocad(self) -> None:
        """Select and lock one already-open AutoCAD drawing."""
        try:
            drawings = self.autocad_connection.drawings()
            if not drawings:
                raise AutoCADConnectionError("AutoCAD has no open drawings.")
            labels = [f"{item.name} - {item.full_name}" for item in drawings]
            selected, accepted = QInputDialog.getItem(
                self, "Connect AutoCAD", "Open drawing", labels, 0, False
            )
            if not accepted:
                return
            identity = self.autocad_connection.select(
                drawings[labels.index(selected)].full_name
            )
        except AutoCADConnectionError as error:
            QMessageBox.warning(self, "AutoCAD connection failed", str(error))
            return
        self._set_cad_actions_enabled(True)
        self.statusBar().showMessage(f"AutoCAD locked to {identity.name}")

    def _cad_gateway(self) -> ComCadGateway:
        return ComCadGateway(self.autocad_connection.target_document)

    def _set_cad_actions_enabled(self, connected: bool) -> None:
        self.read_cad_route_action.setEnabled(connected)
        self.read_cad_offset_action.setEnabled(connected)
        self.read_cad_poles_action.setEnabled(connected)
        self.update_cad_poles_action.setEnabled(
            connected and self.current_geometry is not None and bool(self.current_poles)
        )

    def _read_cad_route(self) -> None:
        try:
            self._cad_route_points = read_latest_route(self._cad_gateway())
        except (AutoCADConnectionError, CadReadbackError) as error:
            self._cad_operation_failed("Read Route", error)
            return
        self.statusBar().showMessage(
            f"Read MAIN_CENTERLINE from locked drawing ({len(self._cad_route_points)} points)"
        )

    def _read_cad_pole_offset(self) -> None:
        try:
            self._cad_pole_offset = read_latest_pole_offset(self._cad_gateway())
        except (AutoCADConnectionError, CadReadbackError) as error:
            self._cad_operation_failed("Read Pole Offset", error)
            return
        self.statusBar().showMessage(
            f"Read POLE_OFFSET from locked drawing ({len(self._cad_pole_offset)} points)"
        )

    def _update_cad_poles(self) -> None:
        """Replace only PoleRoute-managed pole/rack inserts in the locked drawing."""
        if self.current_geometry is None or not self.current_poles:
            QMessageBox.warning(
                self, "Update Poles", "Build geometry and import pole data first."
            )
            return
        try:
            gateway = self._cad_gateway()
            offset = read_latest_pole_offset(gateway)
            plan = build_pole_overlay_plan(
                self.current_geometry, self._physical_pole_mapping(), offset
            )
            updated = update_managed_poles(gateway, plan)
        except (AutoCADConnectionError, CadReadbackError) as error:
            self._cad_operation_failed("Update Poles", error)
            return
        self._cad_pole_offset = offset
        self.statusBar().showMessage(
            f"Updated {len(updated)} managed pole/rack object(s); base CAD unchanged"
        )

    def _read_cad_pole_positions(self) -> None:
        """Apply edited managed-block positions to matching source pole records."""
        if self.current_geometry is None or not self.current_poles:
            QMessageBox.warning(
                self, "Read Pole Positions", "Build geometry and import pole data first."
            )
            return
        try:
            positions = read_managed_pole_positions(self._cad_gateway())
        except (AutoCADConnectionError, CadReadbackError) as error:
            self._cad_operation_failed("Read Pole Positions", error)
            return
        mapping = self._physical_pole_mapping()
        changed = 0
        updated_poles = []
        for pole in self.current_poles:
            physical_id = mapping.assignment_for(pole.number).physical_pole_id
            if physical_id is None or physical_id not in positions:
                updated_poles.append(pole)
                continue
            geographic = self.current_geometry.projection.to_geographic(
                *positions[physical_id]
            )
            updated_poles.append(
                replace(
                    pole,
                    latitude=geographic.latitude,
                    longitude=geographic.longitude,
                )
            )
            changed += 1
        self.current_poles = updated_poles
        self.show_poles(updated_poles)
        self._show_same_pole_groups()
        self._mark_dirty()
        self.statusBar().showMessage(
            f"Read {changed} matched pole record position(s) from locked drawing"
        )

    def _cad_operation_failed(self, operation: str, error: Exception) -> None:
        self._set_cad_actions_enabled(self.autocad_connection.connected)
        QMessageBox.warning(self, f"{operation} failed", str(error))
        self.statusBar().showMessage(f"{operation} failed; project and CAD unchanged")

    def _import_edited_dxf(self) -> None:
        """Validate and retain pole/break identities from an edited CAD Master."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import edited CAD Master",
            self.working_directory.initial_path(),
            "AutoCAD DXF (*.dxf)",
        )
        if not path:
            return
        self.working_directory.remember_file(path)
        try:
            inspection = inspect_edited_dxf(
                path, tuple(pole.number for pole in self.current_poles)
            )
        except EditedDxfImportError as error:
            QMessageBox.warning(self, "Edited DXF import failed", str(error))
            self.statusBar().showMessage("Edited DXF import failed")
            return
        dialog = EditedDxfDialog(inspection, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.edited_dxf = inspection.to_data()
        self.create_cad_sheets_action.setEnabled(True)
        self._mark_dirty()
        self.statusBar().showMessage(
            f"Accepted edited CAD Master: {len(inspection.pole_blocks)} pole block(s), "
            f"{len(inspection.sheet_breaks)} sheet break(s)"
        )

    def _create_cad_sheets(self) -> None:
        """Build plot-ready Paper Space layouts from the accepted edited DXF."""
        if not self.edited_dxf or not self.edited_dxf.get("source_path"):
            QMessageBox.warning(
                self, "CAD sheet creation failed", "Import and confirm an edited DXF first."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CAD drawing with A4 sheets",
            self.working_directory.initial_path("PoleRoute-Schematic-sheets.dxf"),
            "AutoCAD DXF (*.dxf)",
        )
        if not path:
            return
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        self.working_directory.remember_file(path)
        try:
            object_count = export_edited_dxf_with_sheet_layouts(
                self.edited_dxf["source_path"], path, self.export_settings
            )
        except DxfExportError as error:
            QMessageBox.warning(self, "CAD sheet creation failed", str(error))
            self.statusBar().showMessage("CAD sheet creation failed")
            return
        self.statusBar().showMessage(
            f"Created {object_count} Paper Space object(s) in {path}"
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
            any(route.type is RouteType.MAIN_ROUTE for route in self.current_routes)
        )
        self.review_pea_order_action.setEnabled(
            sum(route.type is RouteType.MAIN_ROUTE for route in self.current_routes) == 1
            and bool(self.current_pea_poles)
        )
        self._update_pea_qc_action()
        self.current_geometry = None
        self.undo_stack.clear()
        self.reset_layout_action.setEnabled(False)
        for action in self.drawing_actions.values():
            action.setEnabled(False)
        self.blocks_button.setEnabled(False)
        self.edit_canvas_action.setChecked(False)
        self.edit_canvas_action.setEnabled(False)
        self.export_action.setEnabled(False)
        self.export_dxf_action.setEnabled(False)
        self.import_edited_dxf_action.setEnabled(False)
        self.create_cad_sheets_action.setEnabled(False)
        self._set_cad_actions_enabled(self.autocad_connection.connected)
        self.drawing_actions[DrawingMode.SELECT].setChecked(True)
        self.canvas.set_mode(DrawingMode.SELECT)

    def _update_pea_qc_action(self) -> None:
        has_reviewed_poles = (
            sum(route.type is RouteType.MAIN_ROUTE for route in self.current_routes) == 1
            and bool(self.current_pea_poles)
            and self.current_pea_ordering is not None
        )
        self.check_google_earth_action.setEnabled(has_reviewed_poles)
        has_asset_qc_poles = bool(self._asset_match_poles()[0])
        self.check_pea_assets_google_earth_action.setEnabled(
            sum(route.type is RouteType.MAIN_ROUTE for route in self.current_routes) == 1
            and has_asset_qc_poles
            and bool(self.current_pea_assets)
        )

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
            self.working_directory.initial_path(),
            "Pole data (*.xlsx *.xlsm *.csv)",
        )
        if path:
            self.working_directory.remember_file(path)
            self.load_pole_file(path)

    def _choose_pea_gis_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import PEA GIS data",
            self.working_directory.initial_path(),
            "PEA GIS workbook (*.xlsx *.xlsm)",
        )
        if path:
            self.working_directory.remember_file(path)
            try:
                discovery = discover_pea_workbook(path)
            except PEAGISImportError as error:
                QMessageBox.warning(self, "PEA GIS import failed", str(error))
                return
            selector = PEASheetSelectionDialog(discovery, self)
            if selector.exec() == QDialog.DialogCode.Accepted:
                selected = selector.selected_sheet_names()
                if selected:
                    self.load_pea_gis_file(path, selected_sheets=selected)
                else:
                    self.statusBar().showMessage("PEA GIS import cancelled; no sheets selected")

    def _choose_asset_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import GIS assets",
            self.working_directory.initial_path(),
            "Asset data (*.xlsx *.xlsm *.csv)",
        )
        if path:
            self.working_directory.remember_file(path)
            self.load_asset_file(path)

    def load_asset_file(self, path: str) -> None:
        """Import a normal mapped CSV/XLSX into the canonical asset review pipeline."""
        try:
            source_dialog = TabularSourceDialog(
                path,
                ASSET_HEADER_ALIASES,
                ASSET_REQUIRED_FIELDS,
                ASSET_FIELD_LABELS,
                self,
            )
            if source_dialog.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage("Asset import cancelled")
                return
            table = inspect_asset_file(
                path,
                sheet_name=source_dialog.sheet_name(),
                header_row=source_dialog.header_row_number(),
            )
            dialog = AssetColumnMappingDialog(
                table, suggest_asset_mapping(table.headers), self
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage("Asset import cancelled")
                return
            imported = assets_from_table(table, dialog.mapping())
        except AssetImportError as error:
            QMessageBox.warning(self, "Asset import failed", str(error))
            self.statusBar().showMessage("Asset import failed")
            return

        merge = merge_pea_assets(
            self.current_pea_assets,
            self.current_pea_asset_matches,
            imported,
            imported_sheets={table.source_path.name},
        )
        self.current_pea_assets = list(merge.assets)
        poles, ordering = self._asset_match_poles()
        main_routes = [
            route.route for route in self.current_routes if route.type is RouteType.MAIN_ROUTE
        ]
        main_route = main_routes[0] if len(main_routes) == 1 else None
        self.current_pea_asset_matches = list(match_pea_assets(
            self.current_pea_assets,
            poles,
            ordering,
            merge.matches,
            main_route=main_route,
        ))
        self.review_pea_assets_action.setEnabled(bool(self.current_pea_assets))
        self._update_pea_qc_action()
        self.statusBar().showMessage(
            f"Imported {len(imported)} assets; {merge.added} added, "
            f"{merge.updated} updated, {merge.missing_from_source} missing from source"
        )
        self._mark_dirty()

    def load_pea_gis_file(self, path: str, selected_sheets: set[str] | None = None) -> None:
        """Import supported PEA GIS sheets through one coherent entry point."""
        try:
            discovery = discover_pea_workbook(path)
            selected = selected_sheets or {item.name for item in discovery.supported_sheets}
            pole_sheet = next(
                (item.name for item in discovery.supported_sheets
                 if item.profile == DS_POLE_PROFILE and item.name in selected),
                None,
            )
            records = import_ds_poles(path, pole_sheet) if pole_sheet else None
            asset_profiles = tuple(
                profile for profile in ASSET_PROFILES if profile.sheet_name in selected
            )
            imported_assets = import_pea_assets(path, asset_profiles) if asset_profiles else []
        except PEAGISImportError as error:
            QMessageBox.warning(self, "PEA GIS import failed", str(error))
            self.statusBar().showMessage("PEA GIS import failed")
            return

        if records is not None:
            self.current_pea_poles = records
            self.current_pea_ordering = None
        merge = merge_pea_assets(
            self.current_pea_assets,
            self.current_pea_asset_matches,
            imported_assets,
            imported_sheets={
                sheet.name
                for sheet in discovery.supported_sheets
                if sheet.profile != DS_POLE_PROFILE and sheet.name in selected
            },
        )
        self.current_pea_assets = list(merge.assets)
        analysis_routes = [
            route.route for route in self.current_routes if route.type is RouteType.MAIN_ROUTE
        ]
        analysis_route = analysis_routes[0] if len(analysis_routes) == 1 else None
        self.current_pea_asset_matches = list(
            match_pea_assets(
                self.current_pea_assets,
                self.current_pea_poles,
                self.current_pea_ordering,
                merge.matches,
                main_route=analysis_route,
            )
        )
        self.review_pea_assets_action.setEnabled(bool(self.current_pea_assets))
        self._update_pea_qc_action()
        if records is None:
            QMessageBox.information(
                self, "PEA GIS import summary",
                self._pea_asset_summary() + "\n\nDS_Pole: not present",
            )
            self.statusBar().showMessage(f"Imported {len(imported_assets)} PEA assets")
            self._mark_dirty()
            return
        assert records is not None
        included = [record for record in records if record.included_by_default]
        # Preserve the A1 compatibility view while route-based review is pending.
        # This is only the default subset; confirmed A2 ordering replaces it.
        self.current_poles = [
            Pole(
                number=record.source_id,
                latitude=record.latitude,
                longitude=record.longitude,
                detail="",
                side=PoleSide.UNKNOWN,
            )
            for record in included
        ]
        self.same_pole_groups = []
        self.transformer_rack_groups = []
        self.transformer_rack_leg_pairs = []
        self.show_poles(self.current_poles)
        self._show_same_pole_groups()
        self._update_geometry_action()
        main_routes = [route.route for route in self.current_routes if route.type is RouteType.MAIN_ROUTE]
        self.review_pea_order_action.setEnabled(len(main_routes) == 1)
        warning_count = sum(bool(record.qc_warnings) for record in records)
        unsupported = ", ".join(discovery.unsupported_ds_sheets) or "None"
        excluded = ", ".join(discovery.intentionally_excluded_ds_sheets) or "None"
        summary = (
            f"DS_Pole records: {len(records)}\n"
            f"Included by default: {len(included)}\n"
            f"Retained for review: {len(records) - len(included)}\n"
            f"Rows with QC warnings: {warning_count}\n"
            f"\n{self._pea_asset_summary()}\n"
            f"Intentionally excluded DS_* sheets: {excluded}\n"
            f"Unsupported DS_* sheets: {unsupported}"
        )
        QMessageBox.information(self, "PEA GIS import summary", summary)
        if len(main_routes) == 1:
            self.current_pea_ordering = reference_pea_poles(records, main_routes[0])
            self._update_pea_qc_action()
            self._review_pea_pole_order()
        elif not main_routes:
            QMessageBox.information(
                self,
                "PEA pole review pending",
                "The DS_Pole records were retained. Import or confirm exactly one Main Route "
                "before reviewing station, offset, order, and QC.",
            )
        else:
            QMessageBox.warning(
                self,
                "PEA pole review blocked",
                "More than one Main Route is present. Select exactly one authoritative Main Route; "
                "PoleRoute will not silently concatenate routes.",
            )
        self.statusBar().showMessage(
            f"Imported {len(records)} DS_Pole records; {len(included)} included by default"
        )
        self._mark_dirty()

    def _review_pea_assets(self) -> None:
        if not self.current_pea_assets:
            QMessageBox.warning(self, "Asset review unavailable", "Import GIS asset data first.")
            return
        main_routes = [
            route for route in self.current_routes if route.type is RouteType.MAIN_ROUTE
        ]
        analysis_route = main_routes[0].route if len(main_routes) == 1 else None
        poles, ordering = self._asset_match_poles()
        self.current_pea_asset_matches = list(
            match_pea_assets(
                self.current_pea_assets,
                poles,
                ordering,
                self.current_pea_asset_matches,
                main_route=analysis_route,
            )
        )
        dialog = PEAAssetReviewDialog(
            self.current_pea_assets, self.current_pea_asset_matches,
            poles, ordering, analysis_route, self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.current_pea_asset_matches = list(dialog.matches())
            confirmed = sum(item.state.value == "confirmed" for item in self.current_pea_asset_matches)
            self.statusBar().showMessage(f"Asset review saved; {confirmed} confirmed")
            QMessageBox.information(self, "Asset review summary", self._pea_asset_summary())
            self._mark_dirty()

    def _asset_match_poles(self):
        """Return the active canonical pole set without duplicating source records."""
        active_numbers = {pole.number for pole in self.current_poles}
        pea_ids = {pole.source_id for pole in self.current_pea_poles}
        if (
            self.current_pea_ordering is not None
            and self.current_pea_poles
            and (not active_numbers or active_numbers <= pea_ids)
        ):
            return self.current_pea_poles, self.current_pea_ordering
        return self.current_poles, None

    def _pea_asset_summary(self) -> str:
        matches = {item.asset_id: item for item in self.current_pea_asset_matches}
        lines: list[str] = []
        for asset_type in sorted({asset.asset_type for asset in self.current_pea_assets}, key=str):
            assets = [asset for asset in self.current_pea_assets if asset.asset_type is asset_type]
            states = [matches[asset.stable_id].state.value for asset in assets if asset.stable_id in matches]
            lines.extend((
                asset_type.value.replace("_", " ").title(),
                f"- rows found: {len(assets)}",
                f"- coordinate-valid: {sum(asset.coordinate_valid for asset in assets)}",
                f"- warnings: {sum(bool(asset.qc_warnings) for asset in assets)}",
                f"- suggested: {states.count('suggested')}",
                f"- ambiguous: {states.count('ambiguous')}",
                f"- confirmed: {states.count('confirmed')}",
                f"- unmatched: {states.count('unmatched')}",
            ))
        return "\n".join(lines) if lines else "No supported asset rows found"

    def _review_pea_pole_order(self) -> None:
        main_routes = [route.route for route in self.current_routes if route.type is RouteType.MAIN_ROUTE]
        if not self.current_pea_poles or len(main_routes) != 1:
            QMessageBox.warning(
                self,
                "PEA pole review unavailable",
                "PEA GIS records and exactly one Main Route are required.",
            )
            return
        ordering = self.current_pea_ordering or reference_pea_poles(
            self.current_pea_poles, main_routes[0]
        )
        dialog = PEAPoleReviewDialog(
            self.current_pea_poles, main_routes[0], ordering, self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("PEA pole review cancelled; source records retained")
            return
        self.current_pea_ordering = dialog.ordering()
        records_by_key = {record.source_key: record for record in self.current_pea_poles}
        self.current_poles = [
            Pole(
                number=records_by_key[entry.source_key].source_id,
                latitude=records_by_key[entry.source_key].latitude,
                longitude=records_by_key[entry.source_key].longitude,
                detail="",
                side=PoleSide.UNKNOWN,
            )
            for entry in self.current_pea_ordering.ordered_included()
        ]
        self.same_pole_groups = []
        self.transformer_rack_groups = []
        self.transformer_rack_leg_pairs = []
        self.show_poles(self.current_poles)
        self._show_same_pole_groups()
        self._update_geometry_action()
        self._mark_dirty()
        self.statusBar().showMessage(
            f"Confirmed PEA pole order: {len(self.current_poles)} included records"
        )

    def _check_pea_qc_in_google_earth(self) -> None:
        main_routes = [
            route.route for route in self.current_routes
            if route.type is RouteType.MAIN_ROUTE
        ]
        if len(main_routes) != 1:
            QMessageBox.warning(
                self,
                "Google Earth QC unavailable",
                "Exactly one Main Route is required before checking poles in Google Earth.",
            )
            return
        if not self.current_pea_poles or self.current_pea_ordering is None:
            QMessageBox.warning(
                self,
                "Google Earth QC unavailable",
                "Import PEA GIS data and create a pole review order first.",
            )
            return
        if not self.project_path and not self._save_project_as():
            self.statusBar().showMessage(
                "Google Earth QC cancelled; save the project first"
            )
            return

        try:
            kml_path = pea_qc_kml_path(self.project_path or "")
            export_pea_qc_kml(
                kml_path,
                main_routes[0],
                self.current_pea_poles,
                self.current_pea_ordering,
            )
        except KMLQCExportError as error:
            QMessageBox.warning(self, "Google Earth QC export failed", str(error))
            self.statusBar().showMessage("Google Earth QC export failed")
            return

        try:
            launch_kml(kml_path)
        except KMLQCLaunchError as error:
            QMessageBox.warning(self, "Google Earth launch failed", str(error))
            self.statusBar().showMessage(
                f"QC KML generated; open it manually: {kml_path}"
            )
            return
        self.statusBar().showMessage(f"Opened Google Earth QC: {kml_path}")

    def _check_pea_assets_in_google_earth(self) -> None:
        main_routes = [
            route.route for route in self.current_routes
            if route.type is RouteType.MAIN_ROUTE
        ]
        if len(main_routes) != 1:
            QMessageBox.warning(
                self,
                "Asset Google Earth QC unavailable",
                "Exactly one Main Route is required before checking assets.",
            )
            return
        poles, ordering = self._asset_match_poles()
        if not poles:
            QMessageBox.warning(
                self,
                "Asset Google Earth QC unavailable",
                "Import pole data before checking asset relationships.",
            )
            return
        if not self.current_pea_assets:
            QMessageBox.warning(
                self,
                "Asset Google Earth QC unavailable",
                "Import Transformer or Switch asset data first.",
            )
            return
        if not self.project_path and not self._save_project_as():
            self.statusBar().showMessage(
                "Asset Google Earth QC cancelled; save the project first"
            )
            return

        try:
            kml_path = pea_asset_qc_kml_path(self.project_path or "")
            export_pea_asset_qc_kml(
                kml_path,
                main_routes[0],
                poles,
                ordering,
                self.current_pea_assets,
                self.current_pea_asset_matches,
            )
        except KMLQCExportError as error:
            QMessageBox.warning(self, "Asset Google Earth QC export failed", str(error))
            self.statusBar().showMessage("Asset Google Earth QC export failed")
            return

        try:
            launch_kml(kml_path)
        except KMLQCLaunchError as error:
            QMessageBox.warning(self, "Google Earth launch failed", str(error))
            self.statusBar().showMessage(
                f"Asset QC KML generated; open it manually: {kml_path}"
            )
            return
        self.statusBar().showMessage(f"Opened asset Google Earth QC: {kml_path}")

    def load_pole_file(self, path: str) -> None:
        """Load a pole file and display validation errors to the user."""
        try:
            source_dialog = TabularSourceDialog(
                path,
                POLE_HEADER_ALIASES,
                POLE_REQUIRED_FIELDS,
                POLE_FIELD_LABELS,
                self,
            )
            if source_dialog.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage("Pole import cancelled")
                return
            table = inspect_pole_file(
                path,
                sheet_name=source_dialog.sheet_name(),
                header_row=source_dialog.header_row_number(),
            )
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

        same_pole_groups: list[frozenset[str]] = []
        transformer_rack_groups: list[frozenset[str]] = []
        transformer_rack_leg_pairs: list[tuple[str, str]] = []
        close_groups = find_close_pole_groups(poles)
        if close_groups:
            review = DuplicatePoleDialog(poles, close_groups, self)
            if review.exec() != DuplicatePoleDialog.DialogCode.Accepted:
                self.statusBar().showMessage("Pole import cancelled during duplicate-coordinate review")
                return
            for group, decision, rack_pair in review.decisions():
                if decision in {SAME_POLE, ACCESSORY}:
                    same_pole_groups.append(group)

                elif decision == TRANSFORMER_RACK:
                    transformer_rack_groups.append(group)

                    if rack_pair is not None:
                        transformer_rack_leg_pairs.append(rack_pair)
        self.current_poles = poles
        self.same_pole_groups = same_pole_groups
        self.transformer_rack_groups = transformer_rack_groups
        self.transformer_rack_leg_pairs = transformer_rack_leg_pairs
        self.show_poles(poles)
        self._show_same_pole_groups()
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
                str(pole.installed_quantity),
                pole.side.value,
                "",
                "-",
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
        self._show_same_pole_groups()
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
            self,
            "Open PoleRoute project",
            self.working_directory.initial_path(),
            "PoleRoute project (*.prs)",
        )
        if path:
            self.working_directory.remember_file(path)
            self.open_project(path)

    def _new_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._changing_project = True
        try:
            self.current_route = None
            self.current_routes = []
            self.current_context_routes = []
            self.current_osm_features = []
            self.surrounding_candidates = None
            self.current_road_width = 6.0
            self.current_poles = []
            self.current_pea_poles = []
            self.current_pea_ordering = None
            self.current_pea_assets = []
            self.current_pea_asset_matches = []
            self.current_geometry = None
            self.same_pole_groups = []
            self.transformer_rack_groups = []
            self.transformer_rack_leg_pairs = []
            self.edited_dxf = None
            self.export_settings = ExcelExportSettings()
            self.project_path = None
            clear_scene(self.route_scene)
            self.route_scene.setSceneRect(0, 0, 1000, 600)
            self.pole_table.setRowCount(0)
            self.undo_stack.clear()
            self.fetch_surroundings_action.setEnabled(False)
            self.review_surroundings_action.setEnabled(False)
            self.retry_surroundings_action.setEnabled(False)
            self.review_pea_order_action.setEnabled(False)
            self.review_pea_assets_action.setEnabled(False)
            self.check_google_earth_action.setEnabled(False)
            self.check_pea_assets_google_earth_action.setEnabled(False)
            self._update_geometry_action()
            self.generate_schematic_action.setEnabled(False)
            self.workspace_note.setText(
                "Import a route, then build the base geometry. Pole data is optional."
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
            self.project_path
            or self.working_directory.initial_path("PoleRoute-Schematic.prs"),
            "PoleRoute project (*.prs)",
        )
        if not path:
            return False
        if not path.lower().endswith(".prs"):
            path += ".prs"
        self.working_directory.remember_file(path)
        return self._write_project(path)

    def _write_project(self, path: str | None) -> bool:
        if not path:
            return False
        try:
            save_project_file(
                path,
                {
                    "routes": routes_to_data(self.current_routes),
                    "osm_features": osm_features_to_data(self.current_osm_features),
                    "surrounding_candidates": osm_context_to_data(
                        self.surrounding_candidates
                    ),
                    "poles": poles_to_data(self.current_poles),
                    "pea_poles": pea_poles_to_data(self.current_pea_poles),
                    "pea_pole_ordering": pea_pole_ordering_to_data(
                        self.current_pea_ordering
                    ),
                    "pea_assets": pea_assets_to_data(self.current_pea_assets),
                    "pea_asset_matches": pea_asset_matches_to_data(self.current_pea_asset_matches),
                    "same_pole_groups": [sorted(group) for group in self.same_pole_groups],
                    "transformer_rack_groups": [
                        sorted(group) for group in self.transformer_rack_groups
                    ],
                    "transformer_rack_leg_pairs": [
                        list(pair) for pair in self.transformer_rack_leg_pairs
                    ],
                    "canvas": scene_to_data(self.route_scene),
                    "workspace_note": self.workspace_note.text(),
                    "has_schematic": self.export_action.isEnabled(),
                    "export_settings": asdict(self.export_settings),
                    "edited_dxf": self.edited_dxf,
                },
            )
        except (ProjectFileError, RuntimeError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Project save failed", str(error))
            self.statusBar().showMessage("Project save failed")
            return False
        self.project_path = path
        self.working_directory.remember_file(path)
        self._mark_clean()
        self.statusBar().showMessage(f"Saved project to {path}")
        return True

    def open_project(self, path: str) -> bool:
        try:
            document = load_project_file(path)
            routes = routes_from_data(document.get("routes", []))
            poles = poles_from_data(document.get("poles", []))
            pea_poles = pea_poles_from_data(document.get("pea_poles", []))
            pea_ordering = pea_pole_ordering_from_data(
                document.get("pea_pole_ordering")
            )
            pea_assets = pea_assets_from_data(document.get("pea_assets", []))
            pea_asset_matches = pea_asset_matches_from_data(document.get("pea_asset_matches", []))
            osm_features = osm_features_from_data(document.get("osm_features", []))
            surrounding_candidates = osm_context_from_data(
                document.get("surrounding_candidates")
            )
            geometry = build_road_network_geometry(routes, poles) if routes else None
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
            self.current_osm_features = list(prepare_context_features(
                osm_features, self.current_route
            )) if self.current_route else osm_features
            self.surrounding_candidates = surrounding_candidates
            self.review_surroundings_action.setEnabled(
                self.current_route is not None and surrounding_candidates is not None
            )
            self.retry_surroundings_action.setEnabled(
                surrounding_candidates is not None and any(
                    item.status is FetchCoverageStatus.FAILED
                    for item in surrounding_candidates.coverage
                )
            )
            self.current_road_width = (
                (main_routes[0].width_metres or 6.0) if main_routes else 6.0
            )
            self.current_poles = poles
            self.current_pea_poles = pea_poles
            self.current_pea_ordering = pea_ordering
            self.current_pea_assets = pea_assets
            self.current_pea_asset_matches = pea_asset_matches
            self.current_geometry = geometry
            self.same_pole_groups = [
                frozenset(group) for group in document.get("same_pole_groups", [])
            ]
            self.transformer_rack_groups = [
                frozenset(group) for group in document.get("transformer_rack_groups", [])
            ]
            self.transformer_rack_leg_pairs = [
                tuple(pair)
                for pair in document.get("transformer_rack_leg_pairs", [])
                if len(pair) == 2
            ]
            self.export_settings = ExcelExportSettings(
                **document.get("export_settings", {})
            )
            self.edited_dxf = document.get("edited_dxf")
            self.show_poles(poles)
            self._show_same_pole_groups()
            self.undo_stack.clear()
            restore_scene(self.route_scene, document.get("canvas", {}), self.undo_stack)
            self.project_path = path
            self.working_directory.remember_file(path)
            has_schematic = bool(document.get("has_schematic"))
            self.build_geometry_action.setEnabled(bool(main_routes))
            self.fetch_surroundings_action.setEnabled(bool(main_routes))
            self.review_pea_order_action.setEnabled(
                len(main_routes) == 1 and bool(pea_poles)
            )
            self.review_pea_assets_action.setEnabled(bool(pea_assets))
            self._update_pea_qc_action()
            self.generate_schematic_action.setEnabled(bool(geometry and geometry.roads))
            self.reset_layout_action.setEnabled(has_schematic)
            self.edit_canvas_action.setEnabled(has_schematic)
            self.export_action.setEnabled(has_schematic)
            self.export_dxf_action.setEnabled(geometry is not None)
            self.import_edited_dxf_action.setEnabled(geometry is not None)
            self.create_cad_sheets_action.setEnabled(bool(self.edited_dxf))
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
        mapping = self._physical_pole_mapping()
        for row, pole in enumerate(self.current_poles):
            self.pole_table.setItem(row, 6, QTableWidgetItem(""))
            self.pole_table.setItem(row, 7, QTableWidgetItem(mapping.label_for(pole.number)))
        for group in self.same_pole_groups:
            label = " / ".join(sorted(group))
            for row, pole in enumerate(self.current_poles):
                if pole.number in group:
                    self.pole_table.setItem(row, 6, QTableWidgetItem(label))
        for group in self.transformer_rack_groups:
            label = " / ".join(sorted(group))
            for row, pole in enumerate(self.current_poles):
                if pole.number in group:
                    self.pole_table.setItem(row, 6, QTableWidgetItem(label))

    def _physical_pole_mapping(self):
        ordered = [pole.number for pole in self.current_poles]
        if self.current_geometry is not None and self.current_geometry.roads:
            main = next(
                (road for road in self.current_geometry.roads if road.is_main_route),
                self.current_geometry.roads[0],
            )
            ordered = [
                item.pole.number
                for item in sorted(
                    self.current_geometry.projected_poles,
                    key=lambda item: main.centerline.project(item.original),
                )
            ]
            ordered.extend(
                pole.number for pole in self.current_poles if pole.number not in ordered
            )
        return build_physical_pole_mapping(
            ordered,
            self.same_pole_groups,
            self.transformer_rack_groups,
            self.transformer_rack_leg_pairs,
        )

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
