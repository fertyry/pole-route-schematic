from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QGraphicsPathItem,
    QGraphicsTextItem,
    QGraphicsView,
    QMenu,
    QTableWidgetSelectionRange,
    QToolBar,
)

from pole_route.importers.pole_importer import PoleTable
from pole_route.main import create_application
from pole_route.ui.column_mapping_dialog import ColumnMappingDialog
from pole_route.ui.geometry_settings_dialog import GeometrySettingsDialog
from pole_route.ui.main_window import MainWindow
from pole_route.ui.osm_context_dialog import OSMContextDialog
from pole_route.ui.route_import_dialog import RouteImportDialog
from pole_route.ui.schematic_settings_dialog import SchematicSettingsDialog


def test_application_metadata(qtbot) -> None:
    application = create_application([])

    assert application.applicationName() == "PoleRoute Schematic"
    assert application.applicationVersion() == "0.1.0"
    assert QLocale().zeroDigit() == "0"


def test_main_window_contains_canvas(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "PoleRoute Schematic - V2 Preview"
    assert window.findChild(QGraphicsView, "schematicCanvas") is not None


def test_v2_ui_groups_commands_by_work_stage(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.findChild(QToolBar, "workflowToolbar") is not None
    assert window.findChild(QToolBar, "drawingToolbar") is not None
    assert window.findChild(QMenu, "projectMenu").title() == "Project"
    assert window.findChild(QMenu, "dataMenu").title() == "Data"
    assert window.findChild(QMenu, "geometryMenu").title() == "Geometry"
    assert window.findChild(QMenu, "drawingMenu").title() == "Drawing"
    assert window.findChild(QMenu, "outputMenu").title() == "Output"
    drawing_actions = [
        window.edit_canvas_action,
        window.undo_action,
        window.redo_action,
        window.delete_action,
        window.reset_layout_action,
        window.stack_poles_action,
        *window.drawing_actions.values(),
    ]
    assert all(not action.icon().isNull() for action in drawing_actions)
    assert not window.blocks_button.icon().isNull()


def test_main_window_can_show_poles(qtbot) -> None:
    from pole_route.domain.pole import Pole, PoleSide

    window = MainWindow()
    qtbot.addWidget(window)
    window.show_poles([Pole("P-001", 13.7563, 100.5018, "Transformer", PoleSide.LEFT)])

    assert window.pole_table.rowCount() == 1
    assert window.pole_table.item(0, 0).text() == "P-001"
    assert window.pole_table.item(0, 4).text() == "1"
    assert window.pole_table.item(0, 5).text() == "Left"


def test_geometry_action_requires_route_and_poles(qtbot) -> None:
    from pole_route.domain.pole import Pole
    from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType

    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.build_geometry_action.isEnabled()

    window.current_route = Route(
        "Road",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )
    window.current_routes = [
        ClassifiedRoute(window.current_route, RouteType.MAIN_ROUTE, 6.0, 2.0)
    ]
    window._update_geometry_action()
    assert not window.build_geometry_action.isEnabled()

    window.current_poles = [Pole("1", 13.0, 100.001)]
    window._update_geometry_action()
    assert window.build_geometry_action.isEnabled()


def test_fetch_surroundings_requires_a_main_route(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert not window.fetch_surroundings_action.isEnabled()
    assert not window.export_dxf_action.isEnabled()
    assert not window.import_edited_dxf_action.isEnabled()
    assert not window.create_cad_sheets_action.isEnabled()


def test_osm_review_waits_until_worker_thread_cleanup(qtbot, monkeypatch) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    reviewed = []
    context = object()
    monkeypatch.setattr(window, "_review_surroundings", reviewed.append)

    window._surroundings_ready(context)
    assert reviewed == []

    window._surroundings_fetch_finished()
    assert reviewed == [context]


def test_cancelled_surround_fetch_does_not_review_or_replace_state(qtbot, monkeypatch) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    existing = object()
    window.current_osm_features = [existing]
    reviewed = []
    monkeypatch.setattr(window, "_review_surroundings", reviewed.append)

    window._surroundings_cancelled()
    window._surroundings_fetch_finished()

    assert reviewed == []
    assert window.current_osm_features == [existing]
    assert "unchanged" in window.statusBar().currentMessage()


def test_save_after_accepted_osm_context_round_trips_routes(qtbot, tmp_path) -> None:
    from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType

    main_route = ClassifiedRoute(
        Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100.01, 13.01))),
        RouteType.MAIN_ROUTE,
        6.0,
        2.0,
    )
    context_route = ClassifiedRoute(
        Route(
            "Soi Test",
            "OpenStreetMap:way/1",
            (GeoPoint(100.004, 13.004), GeoPoint(100.006, 13.006)),
        ),
        RouteType.ROAD,
        4.0,
        None,
        False,
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_route = main_route.route
    window.current_routes = [main_route, context_route]
    window.current_context_routes = [context_route]
    window.show_routes(window.current_routes)
    path = tmp_path / "after-fetch.prs"

    assert window._write_project(str(path))

    reopened = MainWindow()
    qtbot.addWidget(reopened)
    assert reopened.open_project(str(path))
    assert reopened.current_routes == [main_route, context_route]
    assert reopened.current_context_routes == [context_route]
    assert reopened.route_scene.items()


def test_save_after_build_geometry_round_trips_project_state(qtbot, tmp_path) -> None:
    from pole_route.domain.pole import Pole, PoleSide
    from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType

    route = ClassifiedRoute(
        Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100.01, 13.01))),
        RouteType.MAIN_ROUTE,
        6.0,
        2.0,
    )
    poles = [Pole("P-1", 13.005, 100.005, "Transformer", PoleSide.RIGHT, 2)]
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_route = route.route
    window.current_routes = [route]
    window.current_poles = poles
    window.show_poles(poles)
    window.show_routes([route])
    window._build_geometry()
    path = tmp_path / "after-build.prs"

    assert window.current_geometry is not None
    assert window._write_project(str(path))

    reopened = MainWindow()
    qtbot.addWidget(reopened)
    assert reopened.open_project(str(path))
    assert reopened.current_routes == [route]
    assert reopened.current_poles == poles
    assert reopened.current_geometry is not None
    assert reopened.route_scene.items()


def test_osm_context_dialog_requires_confirmation_and_returns_checked_roads(qtbot) -> None:
    from pole_route.domain.context import ContextRoad, OSMContext
    from pole_route.domain.route import GeoPoint, Route

    main = Route("Main", "A003.kml", (GeoPoint(100, 13), GeoPoint(100, 13.01)))
    soi = Route("Soi Test", "OpenStreetMap:way/1", (GeoPoint(99.999, 13.005), GeoPoint(100.001, 13.005)))
    context = OSMContext((ContextRoad(soi, "residential", 6.0),), ())
    dialog = OSMContextDialog(main, context)
    qtbot.addWidget(dialog)

    buttons = dialog.findChild(QDialogButtonBox)
    selected = dialog.selected_routes()

    assert buttons.button(QDialogButtonBox.StandardButton.Ok).text() == "Add selected surroundings"
    assert len(selected) == 1
    assert selected[0].route.name == "Soi Test"
    assert selected[0].create_pole_line is False
    qtbot.mouseClick(dialog.clear_all_button, Qt.MouseButton.LeftButton)
    assert dialog.selected_routes() == []
    qtbot.mouseClick(dialog.select_all_button, Qt.MouseButton.LeftButton)
    assert len(dialog.selected_routes()) == 1


def test_osm_review_v2_groups_selects_and_previews_feature_geometry(qtbot) -> None:
    from pole_route.domain.context import (
        ContextFeature,
        ContextGeometryPart,
        OSMContext,
        OSMFeatureCategory,
        OSMGeometryKind,
    )
    from pole_route.domain.route import GeoPoint, Route

    main = Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100, 13.01)))
    features = (
        ContextFeature(
            "node", 1, OSMFeatureCategory.FUEL, OSMGeometryKind.POINT,
            (ContextGeometryPart((GeoPoint(100.0001, 13.002),)),),
            name="ปั๊มทดสอบ", recommended=True,
        ),
        ContextFeature(
            "way", 2, OSMFeatureCategory.FUEL, OSMGeometryKind.LINESTRING,
            (ContextGeometryPart((GeoPoint(100.0, 13.003), GeoPoint(100.001, 13.003))),),
            recommended=False,
        ),
        ContextFeature(
            "relation", 3, OSMFeatureCategory.BUILDING,
            OSMGeometryKind.MULTIPOLYGON,
            (ContextGeometryPart(
                (GeoPoint(99.999, 13.004), GeoPoint(100.001, 13.004),
                 GeoPoint(99.999, 13.004)),
                ((GeoPoint(99.9995, 13.004), GeoPoint(100.0005, 13.004),
                  GeoPoint(99.9995, 13.004)),),
            ),),
            recommended=True,
        ),
    )
    dialog = OSMContextDialog(main, OSMContext((), (), features))
    qtbot.addWidget(dialog)

    fuel_table = dialog.feature_tables[OSMFeatureCategory.FUEL]
    building_table = dialog.feature_tables[OSMFeatureCategory.BUILDING]
    assert fuel_table.rowCount() == 2
    assert building_table.rowCount() == 1
    assert fuel_table.item(0, 1).text() == "ปั๊มทดสอบ"
    assert fuel_table.item(1, 1).text() == "Fuel — way/2"
    assert dialog.scene.items()  # POINT, LINESTRING and polygon-with-hole previewed

    dialog._select_recommended(OSMFeatureCategory.FUEL)
    assert dialog.selected_features() == [features[0]]
    dialog.category_toggles[OSMFeatureCategory.BUILDING].setChecked(True)
    assert dialog.selected_features() == [features[0], features[2]]
    assert fuel_table.item(1, 0).checkState() == Qt.CheckState.Unchecked
    dialog._set_feature_category(OSMFeatureCategory.FUEL, False)
    assert dialog.selected_features() == [features[2]]


def test_osm_review_shows_one_identity_in_each_semantic_category_tab(qtbot) -> None:
    from pole_route.domain.context import (
        ContextFeature,
        ContextGeometryPart,
        OSMContext,
        OSMFeatureCategory,
        OSMGeometryKind,
    )
    from pole_route.domain.route import GeoPoint, Route

    main = Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100, 13.01)))
    part = ContextGeometryPart((
        GeoPoint(99.9999, 13.004),
        GeoPoint(100.0001, 13.004),
        GeoPoint(100.0001, 13.006),
        GeoPoint(99.9999, 13.004),
    ))
    features = (
        ContextFeature(
            "way", 998986400, OSMFeatureCategory.BUILDING,
            OSMGeometryKind.POLYGON, (part,), name="วัดไท่ฮัว ฝอกวงซัน",
        ),
        ContextFeature(
            "way", 998986400, OSMFeatureCategory.POI,
            OSMGeometryKind.POLYGON, (part,), name="วัดไท่ฮัว ฝอกวงซัน",
        ),
    )
    dialog = OSMContextDialog(main, OSMContext((), (), features))
    qtbot.addWidget(dialog)

    assert dialog.feature_tables[OSMFeatureCategory.BUILDING].rowCount() == 1
    assert dialog.feature_tables[OSMFeatureCategory.POI].rowCount() == 1
    dialog._set_feature_category(OSMFeatureCategory.BUILDING, True)
    dialog._set_feature_category(OSMFeatureCategory.POI, True)
    assert dialog.selected_features() == list(features)


def test_accepted_osm_features_replace_deduplicate_and_round_trip(qtbot, tmp_path, monkeypatch) -> None:
    from pole_route.domain.context import (
        ContextFeature, ContextGeometryPart, OSMContext,
        OSMFeatureCategory, OSMGeometryKind,
    )
    from pole_route.domain.route import GeoPoint, Route
    import pole_route.ui.main_window as main_window_module

    main = Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100, 13.01)))
    feature = ContextFeature(
        "node", 25, OSMFeatureCategory.POI, OSMGeometryKind.POINT,
        (ContextGeometryPart((GeoPoint(100, 13.005),)),), name="โรงเรียน",
    )

    class AcceptedDialog:
        DialogCode = OSMContextDialog.DialogCode
        def __init__(self, *_args): pass
        def exec(self): return self.DialogCode.Accepted
        def selected_routes(self): return []
        def selected_features(self): return [feature, feature]

    window = MainWindow()
    qtbot.addWidget(window)
    window.current_route = main
    window.current_osm_features = [ContextFeature(
        "node", 99, OSMFeatureCategory.POI, OSMGeometryKind.POINT,
        (ContextGeometryPart((GeoPoint(100, 13.006),)),),
    )]
    monkeypatch.setattr(main_window_module, "OSMContextDialog", AcceptedDialog)
    window._review_surroundings(OSMContext((), (), (feature,)))
    assert window.current_osm_features == [feature]

    path = tmp_path / "accepted-features.prs"
    assert window._write_project(str(path))
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    assert reopened.open_project(str(path))
    assert reopened.current_osm_features == [feature]
    reopened._new_project()
    assert reopened.current_osm_features == []


def test_cancelled_osm_review_does_not_change_accepted_features(qtbot, monkeypatch) -> None:
    from pole_route.domain.context import (
        ContextFeature, ContextGeometryPart, OSMContext,
        OSMFeatureCategory, OSMGeometryKind,
    )
    from pole_route.domain.route import GeoPoint, Route
    import pole_route.ui.main_window as main_window_module

    feature = ContextFeature(
        "node", 30, OSMFeatureCategory.SHOP, OSMGeometryKind.POINT,
        (ContextGeometryPart((GeoPoint(100, 13.005),)),),
    )

    class CancelledDialog:
        DialogCode = OSMContextDialog.DialogCode
        def __init__(self, *_args): pass
        def exec(self): return self.DialogCode.Rejected

    window = MainWindow()
    qtbot.addWidget(window)
    window.current_route = Route(
        "Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100, 13.01))
    )
    window.current_osm_features = [feature]
    monkeypatch.setattr(main_window_module, "OSMContextDialog", CancelledDialog)
    window._review_surroundings(OSMContext((), (), (feature,)))
    assert window.current_osm_features == [feature]


def test_mapping_dialog_uses_explicit_confirmation(qtbot) -> None:
    table = PoleTable(
        ("No", "Latitude", "Longitude"),
        (("1", 13.7, 100.5),),
        header_row=1,
    )
    dialog = ColumnMappingDialog(
        table,
        {"number": "No", "latitude": "Latitude", "longitude": "Longitude", "detail": None, "side": None},
    )
    qtbot.addWidget(dialog)
    buttons = dialog.findChild(QDialogButtonBox)

    assert buttons.button(QDialogButtonBox.StandardButton.Ok).text() == "Confirm import"


def test_route_dialog_uses_explicit_confirmation(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route

    route = Route("Road", "route.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.1, 13.1)))
    dialog = RouteImportDialog([route])
    qtbot.addWidget(dialog)
    buttons = dialog.findChild(QDialogButtonBox)

    assert dialog.selected_route() is route
    assert buttons.button(QDialogButtonBox.StandardButton.Ok).text() == "Confirm routes"


def test_route_dialog_classifies_multiple_lines(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route, RouteType

    routes = [
        Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100.1, 13.1))),
        Route("Soi", "route.kml", (GeoPoint(100.05, 13.05), GeoPoint(100.06, 13.06))),
    ]
    dialog = RouteImportDialog(routes)
    qtbot.addWidget(dialog)
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    dialog.table.cellWidget(1, 2).setCurrentText(RouteType.ROAD.value)
    dialog.table.cellWidget(1, 3).setValue(4.0)
    dialog.table.item(1, 4).setCheckState(Qt.CheckState.Checked)

    classified = dialog.classified_routes()

    assert [item.type for item in classified] == [RouteType.MAIN_ROUTE, RouteType.ROAD]
    assert classified[0].width_metres == 6.0
    assert classified[1].width_metres == 4.0
    assert classified[0].pole_offset_metres == 2.0


def test_route_dialog_uses_arabic_digits_and_previews_checked_routes(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route

    routes = [
        Route("Main", "route.kml", (GeoPoint(100, 13), GeoPoint(100.1, 13.1))),
        Route("Soi", "route.kml", (GeoPoint(100.05, 13.05), GeoPoint(100.06, 13.06))),
    ]
    dialog = RouteImportDialog(routes)
    qtbot.addWidget(dialog)

    assert dialog.table.cellWidget(0, 3).locale().zeroDigit() == "0"
    assert dialog.table.cellWidget(0, 5).locale().zeroDigit() == "0"
    assert dialog.preview_all_button.text() == "Preview selected routes"

    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    qtbot.mouseClick(dialog.preview_all_button, Qt.MouseButton.LeftButton)

    paths = [item for item in dialog.scene.items() if isinstance(item, QGraphicsPathItem)]
    assert len(paths) == 2
    assert dialog.details.text().startswith("Previewing 2 selected routes")


def test_route_dialog_allows_multiple_main_routes(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route, RouteType

    routes = [
        Route("Main 1", "route.kml", (GeoPoint(100, 13), GeoPoint(100.1, 13.1))),
        Route("Main 2", "route.kml", (GeoPoint(100.1, 13.1), GeoPoint(100.2, 13.2))),
    ]
    dialog = RouteImportDialog(routes)
    qtbot.addWidget(dialog)
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    dialog.table.cellWidget(1, 2).setCurrentText(RouteType.MAIN_ROUTE.value)
    dialog.table.cellWidget(1, 3).setValue(8.0)
    dialog.table.item(1, 4).setCheckState(Qt.CheckState.Checked)
    dialog.table.cellWidget(1, 5).setValue(3.0)

    classified = dialog.classified_routes()

    assert [item.type for item in classified] == [RouteType.MAIN_ROUTE, RouteType.MAIN_ROUTE]
    assert [item.width_metres for item in classified] == [6.0, 8.0]
    assert [item.pole_offset_metres for item in classified] == [2.0, 3.0]


def test_route_dialog_reverses_selected_linestring_and_preview_direction(qtbot) -> None:
    from pole_route.domain.route import GeoPoint, Route

    source = Route(
        "Main",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.1, 13.1), GeoPoint(100.2, 13.2)),
    )
    dialog = RouteImportDialog([source])
    qtbot.addWidget(dialog)

    dialog.table.item(0, 6).setCheckState(Qt.CheckState.Checked)
    imported = dialog.selected_route()

    assert imported.points == tuple(reversed(source.points))
    assert source.points[0].longitude == 100.0
    assert "Start 13.200000, 100.200000" in dialog.details.text()
    labels = [
        item.toPlainText()
        for item in dialog.scene.items()
        if isinstance(item, QGraphicsTextItem)
    ]
    assert set(labels) == {"START", "END"}


def test_geometry_settings_use_arabic_digits(qtbot) -> None:
    dialog = GeometrySettingsDialog()
    qtbot.addWidget(dialog)

    assert dialog.road_width.locale().zeroDigit() == "0"
    assert dialog.pole_offset.locale().zeroDigit() == "0"


def test_schematic_spacing_dialog_returns_spacing_enum(qtbot) -> None:
    from pole_route.geometry.schematic_layout import PoleSpacingMode, SchematicLayoutMode

    dialog = SchematicSettingsDialog()
    qtbot.addWidget(dialog)

    assert dialog.layout_mode() is SchematicLayoutMode.NETWORK
    assert dialog.spacing_mode() is PoleSpacingMode.PROJECTED_STATION
    dialog.spacing.setCurrentIndex(1)
    assert dialog.layout_mode() is SchematicLayoutMode.STRAIGHT_EQUAL
    assert dialog.spacing_mode() is PoleSpacingMode.EQUAL


def test_main_window_marks_selected_rows_as_one_physical_pole(qtbot) -> None:
    from pole_route.domain.pole import Pole

    window = MainWindow()
    qtbot.addWidget(window)
    poles = [Pole("6", 13.0, 100.0), Pole("7", 13.1, 100.1)]
    window.current_poles = poles
    window.show_poles(poles)
    window.pole_table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 6), True)

    window._mark_selected_rows_as_same_pole()

    assert window.same_pole_groups == [frozenset({"6", "7"})]
    assert window.pole_table.item(0, 6).text() == "6 / 7"
    assert window.pole_table.item(1, 6).text() == "6 / 7"


def test_canvas_editor_hides_table_and_restores_workspace(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window._toggle_canvas_editor(True)
    assert window.pole_table.isHidden()
    assert window.heading.isHidden()

    window._toggle_canvas_editor(False)
    assert not window.pole_table.isHidden()
    assert not window.heading.isHidden()
