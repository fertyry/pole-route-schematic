import ezdxf
import pytest
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from pole_route.domain.context import (
    ContextFeature,
    ContextGeometryPart,
    OSMFeatureCategory,
    OSMGeometryKind,
)
from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.exporters.dxf_exporter import (
    DxfExportError,
    export_edited_dxf_with_sheet_layouts,
    export_geometry_to_dxf,
)
from pole_route.geometry.road_geometry import build_road_network_geometry
from pole_route.geometry.schematic_layout import SchematicLayoutMode, create_schematic_layout
from pole_route.project.storage import restore_scene, scene_to_data
from pole_route.ui.geometry_renderer import render_road_geometry
from pole_route.ui.scene_lifecycle import clear_scene
from pole_route.ui.schematic_renderer import render_schematic


def _geometry():
    route = Route(
        "Main",
        "main.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.003, 13.0)),
    )
    return build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 12.0, 2.0)],
        [
            Pole("P1", 13.00005, 100.001, "", PoleSide.LEFT),
            Pole("P2", 13.00005, 100.002, "", PoleSide.LEFT),
        ],
    )


def _part(*coordinates, holes=()):
    return ContextGeometryPart(tuple(GeoPoint(*point) for point in coordinates), holes)


def _feature(osm_id, category, kind, parts, name=None):
    return ContextFeature("way", osm_id, category, kind, tuple(parts), name=name)


def _features():
    return (
        _feature(1, OSMFeatureCategory.ROAD_BRIDGE, OSMGeometryKind.LINESTRING,
                 [_part((100.0002, 12.9998), (100.0002, 13.0002))], "สะพานทดสอบ"),
        _feature(2, OSMFeatureCategory.FOOTBRIDGE, OSMGeometryKind.LINESTRING,
                 [_part((100.0004, 12.9998), (100.0004, 13.0002))]),
        _feature(3, OSMFeatureCategory.RIVER, OSMGeometryKind.MULTILINESTRING,
                 [_part((100.0006, 12.9998), (100.0006, 13.0002)),
                  _part((100.0007, 12.9998), (100.0007, 13.0002))], "แม่น้ำจริง"),
        _feature(4, OSMFeatureCategory.CANAL, OSMGeometryKind.LINESTRING,
                 [_part((100.0008, 12.9998), (100.0008, 13.0002))], "คลองจริง"),
        _feature(5, OSMFeatureCategory.BUILDING, OSMGeometryKind.POLYGON,
                 [_part((100.0010, 13.0001), (100.0012, 13.0001),
                        (100.0012, 13.0003), (100.0010, 13.0003),
                        holes=((GeoPoint(100.00105, 13.00015),
                                GeoPoint(100.00115, 13.00015),
                                GeoPoint(100.00115, 13.00025)),))], "อาคารจริง"),
        _feature(6, OSMFeatureCategory.FUEL, OSMGeometryKind.POINT,
                 [_part((100.0014, 13.0001))], "ปั๊มจริง"),
        _feature(7, OSMFeatureCategory.SHOP, OSMGeometryKind.MULTIPOLYGON,
                 [_part((100.0016, 13.0001), (100.0017, 13.0001), (100.0017, 13.0002)),
                  _part((100.0018, 13.0001), (100.0019, 13.0001), (100.0019, 13.0002))]),
        _feature(8, OSMFeatureCategory.POI, OSMGeometryKind.POINT,
                 [_part((100.0020, 13.0001))], "จุดสำคัญ"),
    )


def _xdata(entity):
    return {
        tag.value.split("=", 1)[0]: tag.value.split("=", 1)[1]
        for tag in entity.get_xdata("POLEROUTE")
        if tag.code == 1000 and "=" in tag.value
    }


def test_dxf_exports_every_osm_geometry_and_semantic_layer(tmp_path) -> None:
    destination = tmp_path / "osm.dxf"
    export_geometry_to_dxf(
        _geometry(), destination, include_sheet_layouts=False, osm_features=_features()
    )
    document = ezdxf.readfile(destination)
    layers = {entity.dxf.layer for entity in document.modelspace()}

    assert {
        "PRS_OSM_BRIDGE", "PRS_OSM_BRIDGE_NAME", "PRS_OSM_FOOTBRIDGE",
        "PRS_OSM_RIVER", "PRS_OSM_RIVER_NAME", "PRS_OSM_CANAL",
        "PRS_OSM_CANAL_NAME", "PRS_BUILDING", "PRS_BUILDING_NAME",
        "PRS_OSM_FUEL", "PRS_OSM_FUEL_NAME", "PRS_OSM_SHOP", "PRS_OSM_POI",
        "PRS_OSM_POI_NAME",
    } <= layers
    assert len(document.modelspace().query('LWPOLYLINE[layer=="PRS_BUILDING"]')) == 2
    assert len(document.modelspace().query('LWPOLYLINE[layer=="PRS_OSM_SHOP"]')) == 2
    assert len(document.modelspace().query('LWPOLYLINE[layer=="PRS_OSM_RIVER"]')) == 2
    assert len(document.modelspace().query('CIRCLE[layer=="PRS_OSM_FUEL"]')) == 1


def test_dxf_uses_real_names_only_and_metric_projection(tmp_path) -> None:
    features = _features()
    destination = tmp_path / "labels.dxf"
    geometry = _geometry()
    export_geometry_to_dxf(
        geometry, destination, include_sheet_layouts=False, osm_features=features
    )
    document = ezdxf.readfile(destination)
    texts = {entity.dxf.text for entity in document.modelspace().query("TEXT")}
    circle = document.modelspace().query('CIRCLE[layer=="PRS_OSM_FUEL"]')[0]
    expected = geometry.projection.to_metric(GeoPoint(100.0014, 13.0001))

    assert {"สะพานทดสอบ", "แม่น้ำจริง", "คลองจริง", "อาคารจริง", "ปั๊มจริง", "จุดสำคัญ"} <= texts
    assert not any("OpenStreetMap:" in text or "way/" in text for text in texts)
    assert circle.dxf.center.x == pytest.approx(expected[0])
    assert circle.dxf.center.y == pytest.approx(expected[1])


def test_invalid_osm_geometry_fails_with_identity_and_reason(tmp_path) -> None:
    invalid = _feature(
        99, OSMFeatureCategory.RIVER, OSMGeometryKind.LINESTRING,
        [_part((100.0, 13.0))],
    )
    with pytest.raises(DxfExportError, match=r"river.*way/99.*linestring.*at least two"):
        export_geometry_to_dxf(
            _geometry(), tmp_path / "invalid.dxf",
            include_sheet_layouts=False, osm_features=(invalid,),
        )


def test_legacy_dxf_call_still_accepts_no_osm_features(tmp_path) -> None:
    destination = tmp_path / "legacy.dxf"
    export_geometry_to_dxf(_geometry(), destination, include_sheet_layouts=False)
    assert ezdxf.readfile(destination).audit().has_errors is False


def test_edited_dxf_sheet_export_preserves_osm_modelspace_entities(tmp_path) -> None:
    source = tmp_path / "cad-master.dxf"
    destination = tmp_path / "sheets.dxf"
    export_geometry_to_dxf(
        _geometry(), source, include_sheet_layouts=False, osm_features=_features()
    )

    export_edited_dxf_with_sheet_layouts(source, destination)
    document = ezdxf.readfile(destination)
    layers = {entity.dxf.layer for entity in document.modelspace()}

    assert "PRS_OSM_BRIDGE" in layers
    assert "PRS_BUILDING" in layers
    assert "PRS_OSM_FUEL" in layers
    assert document.audit().has_errors is False


def test_osm_and_overture_buildings_share_canonical_layer_with_source_xdata(tmp_path) -> None:
    osm = _feature(
        901,
        OSMFeatureCategory.BUILDING,
        OSMGeometryKind.POLYGON,
        [_part((100.0010, 13.0001), (100.0011, 13.0001), (100.0011, 13.0002))],
        "อาคาร OSM",
    )
    overture = ContextFeature(
        "",
        0,
        OSMFeatureCategory.BUILDING,
        OSMGeometryKind.POLYGON,
        (_part((100.0012, 13.0001), (100.0013, 13.0001), (100.0013, 13.0002)),),
        name="อาคาร Overture",
        source="Overture",
        source_id="building-abc",
        source_release="2026-07-22.0",
        provider="Overture Maps Foundation",
        dataset="buildings",
        confidence=0.87,
    )
    destination = tmp_path / "multi-source.dxf"

    export_geometry_to_dxf(
        _geometry(), destination, include_sheet_layouts=False,
        osm_features=(osm, overture),
    )
    modelspace = ezdxf.readfile(destination).modelspace()
    buildings = list(modelspace.query('LWPOLYLINE[layer=="PRS_BUILDING"]'))
    metadata = [_xdata(entity) for entity in buildings]

    assert len(buildings) == 2
    assert {item["source"] for item in metadata} == {"OpenStreetMap", "Overture"}
    assert {item["source_id"] for item in metadata} == {"way/901", "building-abc"}
    assert all(item["category"] == "building" for item in metadata)
    assert all(item["prs_object_type"] == "context_feature" for item in metadata)
    assert all(item["prs_ring_role"] == "exterior" for item in metadata)


def test_context_feature_xdata_preserves_part_and_ring_identity(tmp_path) -> None:
    feature = ContextFeature(
        "relation",
        77,
        OSMFeatureCategory.BUILDING,
        OSMGeometryKind.MULTIPOLYGON,
        (
            _part(
                (100.0010, 13.0001), (100.0011, 13.0001), (100.0011, 13.0002),
                holes=((
                    GeoPoint(100.00102, 13.00012),
                    GeoPoint(100.00104, 13.00012),
                    GeoPoint(100.00102, 13.00012),
                ),),
            ),
            _part((100.0012, 13.0001), (100.0013, 13.0001), (100.0013, 13.0002)),
        ),
    )
    destination = tmp_path / "parts.dxf"

    export_geometry_to_dxf(
        _geometry(), destination, include_sheet_layouts=False,
        osm_features=(feature,),
    )
    entities = ezdxf.readfile(destination).modelspace().query(
        'LWPOLYLINE[layer=="PRS_BUILDING"]'
    )
    metadata = [_xdata(entity) for entity in entities]

    assert {(item["prs_part_index"], item["prs_ring_role"]) for item in metadata} == {
        ("0", "exterior"), ("0", "hole:0"), ("1", "exterior")
    }
    assert {item["prs_feature_key"] for item in metadata} == {
        "building:OpenStreetMap:relation/77"
    }


def test_legacy_osm_building_layer_survives_sheet_handoff(tmp_path) -> None:
    source = tmp_path / "legacy.dxf"
    destination = tmp_path / "legacy-sheets.dxf"
    export_geometry_to_dxf(_geometry(), source, include_sheet_layouts=False)
    document = ezdxf.readfile(source)
    document.modelspace().add_lwpolyline(
        ((0, 0), (1, 0), (1, 1)), close=True,
        dxfattribs={"layer": "PRS_OSM_BUILDING"},
    )
    document.saveas(source)

    export_edited_dxf_with_sheet_layouts(source, destination)

    restored = ezdxf.readfile(destination)
    assert len(restored.modelspace().query('LWPOLYLINE[layer=="PRS_OSM_BUILDING"]')) == 1


def test_osm_canvas_survives_metric_schematic_and_scene_round_trip(qapp) -> None:
    geometry = _geometry()
    features = _features()
    metric_scene = QGraphicsScene()
    render_road_geometry(metric_scene, geometry, osm_features=features)
    assert {item.data(1) for item in metric_scene.items() if item.data(0) == "osm_feature"} >= {
        "way/1", "way/8"
    }

    source_stack = QUndoStack()
    scene = QGraphicsScene()
    render_schematic(
        scene, create_schematic_layout(geometry), source_stack, features, geometry
    )
    before = [item for item in scene.items() if item.data(0) == "osm_feature"]
    saved = scene_to_data(scene)
    restored_stack = QUndoStack()
    restored = QGraphicsScene()
    restore_scene(restored, saved, restored_stack)
    after = [item for item in restored.items() if item.data(0) == "osm_feature"]

    assert before
    assert len(after) == len(before)
    assert {item.data(1) for item in after} == {item.data(1) for item in before}
    del before, after
    clear_scene(restored)
    clear_scene(scene)
    clear_scene(metric_scene)


def test_osm_features_render_in_straight_schematic(qapp) -> None:
    geometry = _geometry()
    stack = QUndoStack()
    scene = QGraphicsScene()
    layout = create_schematic_layout(
        geometry, layout_mode=SchematicLayoutMode.STRAIGHT_RELATIVE
    )

    render_schematic(scene, layout, stack, _features(), geometry)

    items = [item for item in scene.items() if item.data(0) == "osm_feature"]
    assert items
    assert {item.data(1) for item in items} >= {"way/1", "way/8"}
    del items
    clear_scene(scene)
