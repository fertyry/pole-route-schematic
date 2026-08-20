import gc

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from pole_route.domain.context import (
    ContextFeature,
    ContextGeometryPart,
    OSMFeatureCategory,
    OSMGeometryKind,
    osm_feature_name,
)
from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.geometry.road_geometry import build_road_network_geometry
from pole_route.geometry.schematic_layout import create_schematic_layout
from pole_route.project.storage import (
    load_project_file,
    osm_features_from_data,
    osm_features_to_data,
    poles_from_data,
    poles_to_data,
    restore_scene,
    routes_from_data,
    ProjectFileError,
    routes_to_data,
    save_project_file,
    scene_to_data,
)
from pole_route.ui.editor_commands import EditableTextItem
from pole_route.ui.geometry_renderer import render_road_geometry
from pole_route.ui.route_import_dialog import draw_classified_routes_preview
from pole_route.ui.schematic_renderer import EDITABLE_FLAGS, render_schematic


def _project_inputs():
    routes = [
        ClassifiedRoute(
            Route(
                "Main",
                "original.kml",
                (GeoPoint(100, 13), GeoPoint(100.01, 13.01)),
            ),
            RouteType.MAIN_ROUTE,
            6.0,
            2.0,
        )
    ]
    poles = [Pole("P-1", 13.005, 100.005, "Transformer", PoleSide.RIGHT, 2)]
    return routes, poles


def test_project_inputs_round_trip_without_source_files(tmp_path) -> None:
    routes, poles = _project_inputs()
    path = tmp_path / "portable.prs"

    save_project_file(
        path,
        {"routes": routes_to_data(routes), "poles": poles_to_data(poles)},
    )
    document = load_project_file(path)

    assert routes_from_data(document["routes"]) == routes
    assert poles_from_data(document["poles"]) == poles


def _feature(
    osm_id: int,
    category: OSMFeatureCategory,
    geometry_kind: OSMGeometryKind,
    parts: tuple[ContextGeometryPart, ...],
    *,
    name: str | None = None,
) -> ContextFeature:
    return ContextFeature(
        "way",
        osm_id,
        category,
        geometry_kind,
        parts,
        name,
        (("bridge", "yes"), ("source", "survey")),
        False,
        "Review manually",
    )


def test_osm_feature_geometry_kinds_round_trip() -> None:
    point = _feature(
        1,
        OSMFeatureCategory.FUEL,
        OSMGeometryKind.POINT,
        (ContextGeometryPart((GeoPoint(100.1, 13.1),)),),
    )
    line = _feature(
        2,
        OSMFeatureCategory.ROAD_BRIDGE,
        OSMGeometryKind.LINESTRING,
        (ContextGeometryPart((GeoPoint(100.1, 13.1), GeoPoint(100.2, 13.2))),),
        name="สะพานทดสอบ",
    )
    polygon = _feature(
        3,
        OSMFeatureCategory.BUILDING,
        OSMGeometryKind.POLYGON,
        (
            ContextGeometryPart(
                (
                    GeoPoint(100.0, 13.0),
                    GeoPoint(100.1, 13.0),
                    GeoPoint(100.1, 13.1),
                    GeoPoint(100.0, 13.0),
                ),
                (
                    (
                        GeoPoint(100.02, 13.02),
                        GeoPoint(100.03, 13.02),
                        GeoPoint(100.02, 13.02),
                    ),
                ),
            ),
        ),
    )
    multiline = _feature(
        4,
        OSMFeatureCategory.RIVER,
        OSMGeometryKind.MULTILINESTRING,
        (
            ContextGeometryPart((GeoPoint(100.0, 13.0), GeoPoint(100.1, 13.1))),
            ContextGeometryPart((GeoPoint(100.2, 13.2), GeoPoint(100.3, 13.3))),
        ),
    )

    restored = osm_features_from_data(
        osm_features_to_data([point, line, polygon, multiline])
    )

    assert restored == [point, line, polygon, multiline]
    assert restored[0].identity == ("way", 1)
    assert restored[0].name is None
    assert restored[1].name == "สะพานทดสอบ"
    assert restored[2].parts[0].holes == polygon.parts[0].holes
    assert restored[3].geometry_kind is OSMGeometryKind.MULTILINESTRING
    assert restored[1].tags == (("bridge", "yes"), ("source", "survey"))
    assert restored[1].source_path == "OpenStreetMap:way/2"


def test_osm_multipolygon_round_trip_preserves_parts_and_holes() -> None:
    feature = ContextFeature(
        "relation",
        99,
        OSMFeatureCategory.CANAL,
        OSMGeometryKind.MULTIPOLYGON,
        (
            ContextGeometryPart(
                (GeoPoint(100.0, 13.0), GeoPoint(100.1, 13.0), GeoPoint(100.0, 13.0)),
                ((GeoPoint(100.02, 13.0), GeoPoint(100.03, 13.0), GeoPoint(100.02, 13.0)),),
            ),
            ContextGeometryPart(
                (GeoPoint(100.2, 13.0), GeoPoint(100.3, 13.0), GeoPoint(100.2, 13.0)),
            ),
        ),
        tags=(("waterway", "canal"),),
        source_path="OpenStreetMap:relation/99",
    )

    assert osm_features_from_data(osm_features_to_data((feature,))) == [feature]


def test_osm_feature_name_prefers_real_thai_name_and_never_invents_one() -> None:
    assert (
        osm_feature_name({"name": "Canal", "name:th": "คลองทดสอบ"})
        == "คลองทดสอบ"
    )
    assert osm_feature_name({"name": "Canal"}) == "Canal"
    assert osm_feature_name({"waterway": "canal"}) is None


def test_old_project_without_osm_features_loads_empty_collection(tmp_path) -> None:
    routes, poles = _project_inputs()
    path = tmp_path / "old-project.prs"
    save_project_file(
        path,
        {"routes": routes_to_data(routes), "poles": poles_to_data(poles)},
    )

    document = load_project_file(path)

    assert document["osm_features"] == []
    assert osm_features_from_data(document["osm_features"]) == []
    assert routes_from_data(document["routes"]) == routes


def test_project_round_trip_preserves_osm_features_and_legacy_roads(tmp_path) -> None:
    routes, poles = _project_inputs()
    feature = _feature(
        123,
        OSMFeatureCategory.FOOTBRIDGE,
        OSMGeometryKind.LINESTRING,
        (ContextGeometryPart((GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.01))),),
        name="สะพานลอย",
    )
    path = tmp_path / "osm-v2.prs"

    save_project_file(
        path,
        {
            "routes": routes_to_data(routes),
            "poles": poles_to_data(poles),
            "osm_features": osm_features_to_data([feature]),
        },
    )
    document = load_project_file(path)

    assert routes_from_data(document["routes"]) == routes
    assert poles_from_data(document["poles"]) == poles
    assert osm_features_from_data(document["osm_features"]) == [feature]


def test_editable_canvas_round_trip_preserves_objects_and_positions(qapp) -> None:
    routes, poles = _project_inputs()
    source = QGraphicsScene()
    source_stack = QUndoStack()
    layout = create_schematic_layout(build_road_network_geometry(routes, poles))
    render_schematic(source, layout, source_stack)
    pole = next(item for item in source.items() if item.data(0) == "pole")
    pole.setPos(pole.pos() + QPointF(25, -10))
    note = EditableTextItem("Site note", source_stack)
    note.setData(0, "drawing")
    note.setData(2, QPointF(300, 200))
    note.setPos(300, 200)
    note.setFlags(EDITABLE_FLAGS)
    source.addItem(note)

    saved = scene_to_data(source)
    restored = QGraphicsScene()
    restore_scene(restored, saved, QUndoStack())

    roles = [item.data(0) for item in restored.items() if item.parentItem() is None]
    restored_pole = next(item for item in restored.items() if item.data(0) == "pole")
    restored_note = next(item for item in restored.items() if item.data(0) == "drawing")
    assert set(roles) >= {"road", "pole", "label", "drawing"}
    assert restored_pole.pos() == pole.pos()
    assert restored_note.pos() == QPointF(300, 200)
    assert restored.sceneRect() == source.sceneRect()


def test_metric_preview_text_can_be_saved_and_restored(qapp) -> None:
    routes, poles = _project_inputs()
    geometry = build_road_network_geometry(routes, poles)
    source = QGraphicsScene()
    render_road_geometry(source, geometry)

    saved = scene_to_data(source)
    restored = QGraphicsScene()
    restore_scene(restored, saved, QUndoStack())

    labels = [
        item.toPlainText()
        for item in restored.items()
        if hasattr(item, "toPlainText")
    ]
    assert labels == ["P-1"]


def test_route_preview_can_be_serialized_repeatedly_without_losing_items(qapp) -> None:
    routes, _poles = _project_inputs()
    source = QGraphicsScene()
    draw_classified_routes_preview(
        source, [(routes[0].route, routes[0].type)], 960, 540
    )

    expected_count = len(source.items())
    expected_rect = source.sceneRect()

    for _ in range(3):
        assert scene_to_data(source)["items"]
        gc.collect()
        qapp.processEvents()
        assert len(source.items()) == expected_count
        assert source.sceneRect() == expected_rect


def test_repeated_project_save_is_read_only_to_live_canvas_and_reopens(qapp, tmp_path) -> None:
    routes, poles = _project_inputs()
    source = QGraphicsScene()
    render_schematic(
        source,
        create_schematic_layout(build_road_network_geometry(routes, poles)),
        QUndoStack(),
    )
    expected_count = len(source.items())
    expected_rect = source.sceneRect()
    expected_visible = sum(item.isVisible() for item in source.items())
    path = tmp_path / "repeat-save.prs"

    for _ in range(3):
        save_project_file(path, {"canvas": scene_to_data(source)})
        gc.collect()
        qapp.processEvents()
        assert len(source.items()) == expected_count
        assert source.sceneRect() == expected_rect
        assert sum(item.isVisible() for item in source.items()) == expected_visible

    restored = QGraphicsScene()
    restore_scene(restored, load_project_file(path)["canvas"], QUndoStack())
    assert len(restored.items()) == expected_count
    assert restored.sceneRect() == expected_rect
    assert sum(item.isVisible() for item in restored.items()) == expected_visible


def test_schematic_round_trip_preserves_installed_quantity_and_physical_kind(qapp) -> None:
    routes, poles = _project_inputs()
    source = QGraphicsScene()
    render_schematic(
        source,
        create_schematic_layout(build_road_network_geometry(routes, poles)),
        QUndoStack(),
    )

    saved = scene_to_data(source)
    restored = QGraphicsScene()
    restore_scene(restored, saved, QUndoStack())

    label = next(item for item in restored.items() if item.data(0) == "label")
    pole = next(item for item in restored.items() if item.data(0) == "pole")
    assert label.data(7) == 2
    assert pole.data(8) == "single"


def test_failed_serialization_does_not_replace_existing_project(tmp_path) -> None:
    path = tmp_path / "existing.prs"
    save_project_file(path, {"value": "original"})

    with pytest.raises(ProjectFileError):
        save_project_file(path, {"value": object()})

    assert load_project_file(path)["value"] == "original"
