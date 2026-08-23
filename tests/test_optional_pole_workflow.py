from __future__ import annotations

import ezdxf

from pole_route.domain.context import (
    ContextFeature,
    ContextGeometryPart,
    OSMFeatureCategory,
    OSMGeometryKind,
)
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.exporters.dxf_exporter import export_geometry_to_dxf
from pole_route.geometry.road_geometry import build_road_network_geometry
from pole_route.geometry.schematic_layout import create_schematic_layout
from pole_route.ui.schematic_renderer import render_schematic


def _main_route() -> ClassifiedRoute:
    return ClassifiedRoute(
        Route(
            "Base route",
            "route.kml",
            (GeoPoint(100.6500, 13.8100), GeoPoint(100.6550, 13.8150)),
        ),
        RouteType.MAIN_ROUTE,
        6.0,
        2.0,
    )


def _building() -> ContextFeature:
    return ContextFeature(
        osm_type="way",
        osm_id=123,
        category=OSMFeatureCategory.BUILDING,
        geometry_kind=OSMGeometryKind.POLYGON,
        parts=(
            ContextGeometryPart(
                (
                    GeoPoint(100.6510, 13.8110),
                    GeoPoint(100.6511, 13.8110),
                    GeoPoint(100.6511, 13.8111),
                    GeoPoint(100.6510, 13.8111),
                    GeoPoint(100.6510, 13.8110),
                )
            ),
        ),
        name="Test building",
    )


def test_route_only_build_succeeds_without_poles() -> None:
    geometry = build_road_network_geometry([_main_route()], [])

    assert len(geometry.roads) == 1
    assert geometry.projected_poles == ()
    assert geometry.unplaced_poles == ()
    assert geometry.roads[0].pole_line_enabled


def test_route_and_surround_generate_schematic_without_poles(qtbot) -> None:
    from PySide6.QtGui import QUndoStack
    from PySide6.QtWidgets import QGraphicsScene

    geometry = build_road_network_geometry([_main_route()], [])
    layout = create_schematic_layout(geometry)
    scene = QGraphicsScene()
    undo_stack = QUndoStack()

    render_schematic(scene, layout, undo_stack, (_building(),), geometry)

    assert layout.poles == ()
    assert layout.roads
    assert scene.items()


def test_route_and_surround_export_valid_dxf_without_fake_poles(tmp_path) -> None:
    geometry = build_road_network_geometry([_main_route()], [])
    destination = tmp_path / "base-map.dxf"

    export_geometry_to_dxf(
        geometry,
        destination,
        include_sheet_layouts=False,
        osm_features=(_building(),),
    )

    document = ezdxf.readfile(destination)
    errors = document.audit().errors
    modelspace = document.modelspace()
    pole_inserts = [
        entity
        for entity in modelspace.query("INSERT")
        if entity.dxf.name in {"PRS_POLE", "PRS_TRANSFORMER_RACK"}
    ]

    assert errors == []
    assert pole_inserts == []
    assert len(modelspace.query("LWPOLYLINE[layer=='PRS_BUILDING']")) == 1
