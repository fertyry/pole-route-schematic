from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.exporters.dxf_exporter import (
    export_geometry_to_dxf,
    recommended_dxf_sheet_count,
)
from pole_route.exporters.excel_exporter import ExcelExportSettings
from pole_route.geometry.road_geometry import build_road_network_geometry


def test_dxf_export_contains_metric_layers_and_reusable_pole_block(tmp_path) -> None:
    route = Route(
        "Main Road",
        "main.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.002, 13.0)),
    )
    geometry = build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 6.0, 2.0)],
        [Pole("P1", 12.99995, 100.001, "Transformer", PoleSide.RIGHT)],
    )
    destination = tmp_path / "drawing.dxf"

    count = export_geometry_to_dxf(geometry, destination)
    document = destination.read_text(encoding="ascii")

    assert count >= 8
    assert "MAIN_CENTERLINE" in document
    assert "MAIN_ROAD_EDGE" in document
    assert "SOI_EDGE" in document
    assert "POLE_OFFSET" in document
    assert "POLE_1M" in document
    assert "POLE_LABELS" in document
    assert "ROAD_LABELS" in document
    assert "INSERT" in document
    assert "P1  Transformer" in document
    assert "\\U+" not in document


def test_dxf_export_escapes_thai_text_for_autocad(tmp_path) -> None:
    route = Route(
        "ถนนทดสอบ",
        "main.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.001, 13.0)),
    )
    geometry = build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 6.0, 2.0)],
        [],
    )
    destination = tmp_path / "thai.dxf"

    export_geometry_to_dxf(geometry, destination)

    document = destination.read_text(encoding="utf-8")
    assert route.name in document
    assert "\\U+" not in document


def test_dxf_export_joins_manual_cross_road_into_main_road_outline(tmp_path) -> None:
    main = Route(
        "Main",
        "junction.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.002, 13.0)),
    )
    cross = Route(
        "Cross",
        "junction.kml",
        (GeoPoint(100.001, 12.999), GeoPoint(100.001, 13.001)),
    )
    geometry = build_road_network_geometry(
        [
            ClassifiedRoute(main, RouteType.MAIN_ROUTE, 20.0, 2.0),
            ClassifiedRoute(cross, RouteType.CROSS_ROAD, 10.0, 2.0),
        ],
        [],
    )
    destination = tmp_path / "joined-junction.dxf"

    export_geometry_to_dxf(geometry, destination)

    modelspace = ezdxf.readfile(destination).modelspace()
    outlines = [
        LineString(tuple((point[0], point[1]) for point in entity.get_points()))
        for entity in modelspace.query('LWPOLYLINE[layer=="ROAD_NETWORK_EDGE"]')
    ]
    assert outlines
    outline = unary_union(outlines)
    junction = geometry.roads[0].centerline.intersection(geometry.roads[1].centerline)
    main_edge_point = Point(junction.x, junction.y + 10.0)
    assert outline.distance(main_edge_point) > 1.0


def test_dxf_export_preserves_selected_nearby_sois(tmp_path) -> None:
    main = Route(
        "Main",
        "roads.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.002, 13.0)),
    )
    soi_one = Route(
        "Soi 1",
        "osm-1",
        (GeoPoint(100.0008, 13.0), GeoPoint(100.0008, 13.0002)),
    )
    soi_two = Route(
        "Soi 1",
        "osm-2",
        (GeoPoint(100.00085, 13.0), GeoPoint(100.00085, 13.0002)),
    )
    geometry = build_road_network_geometry(
        [
            ClassifiedRoute(main, RouteType.MAIN_ROUTE, 20.0, 2.0),
            ClassifiedRoute(soi_one, RouteType.ROAD, 6.0, 2.0, False),
            ClassifiedRoute(soi_two, RouteType.ROAD, 6.0, 2.0, False),
        ],
        [],
    )
    destination = tmp_path / "selected-sois.dxf"

    export_geometry_to_dxf(geometry, destination)

    modelspace = ezdxf.readfile(destination).modelspace()
    assert len(modelspace.query('LWPOLYLINE[layer=="SOI_CENTERLINE"]')) == 2


def test_dxf_export_creates_automatic_a4_sheet_layouts(tmp_path) -> None:
    route = Route(
        "Long Main",
        "long.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )
    geometry = build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 20.0, 2.0)],
        [
            Pole(f"P{index}", 13.00005, 100.0 + 0.001 * index, "", PoleSide.LEFT)
            for index in range(1, 10)
        ],
    )
    destination = tmp_path / "sheets.dxf"
    settings = ExcelExportSettings(project_title="Test Project", page_count=1)

    export_geometry_to_dxf(geometry, destination, settings)

    document = ezdxf.readfile(destination)
    expected = recommended_dxf_sheet_count(geometry)
    assert expected > 1
    assert len([name for name in document.layout_names() if name.startswith("Sheet ")]) == expected
    first_sheet = document.layouts.get("Sheet 01")
    assert len(first_sheet.query('LWPOLYLINE[layer=="SHEET_FRAME"]')) >= 1
    assert any(entity.dxf.text == "Test Project" for entity in first_sheet.query("TEXT"))
    # Every Paper Space layout also owns its internal status-1 viewport.
    viewports = [
        entity for entity in first_sheet.query("VIEWPORT") if entity.dxf.status == 2
    ]
    assert len(viewports) == 1
    assert viewports[0].dxf.layer == "SHEET_VIEWPORT"
    # Sheet geometry comes from the complete Model Space drawing through the
    # viewport; roads are not copied and simplified in Paper Space.
    assert len(first_sheet.query('LWPOLYLINE[layer=="MAIN_ROAD_EDGE"]')) == 0
    assert document.layers.get("SHEET_VIEWPORT").dxf.plot == 0
import ezdxf
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
