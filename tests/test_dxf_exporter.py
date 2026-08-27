import os
import stat

import ezdxf
import pytest

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.exporters.dxf_exporter import (
    DxfExportError,
    _sheet_station_ranges,
    export_geometry_to_dxf,
    recommended_dxf_sheet_count,
)
from pole_route.exporters.excel_exporter import ExcelExportSettings
from pole_route.exporters.dxf_diagnostics import diagnose_dxf
from pole_route.geometry.road_geometry import build_road_network_geometry
from ezdxf.math import Vec3
from shapely.ops import substring


def _simple_geometry():
    route = Route(
        "Main",
        "main.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.002, 13.0)),
    )
    return build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 12.0, 2.0)],
        [Pole("P1", 13.00005, 100.001, "", PoleSide.LEFT)],
    )


def _assert_writable_valid_r2010_dxf(path) -> None:
    result = diagnose_dxf(path)
    assert result.exists
    assert result.os_writable
    assert result.windows_readonly in (False, None)
    assert result.read_write_open_succeeded
    assert result.dxf_version == "AC1024"
    assert result.has_eof_marker
    assert result.audit_errors == ()
    assert result.read_error is None


def test_normal_export_creates_writable_auditable_dxf_and_releases_handle(tmp_path) -> None:
    destination = tmp_path / "new-master.dxf"

    export_geometry_to_dxf(_simple_geometry(), destination, include_sheet_layouts=False)

    _assert_writable_valid_r2010_dxf(destination)
    renamed = destination.with_name("renamed-master.dxf")
    os.replace(destination, renamed)
    assert renamed.exists()


def test_normal_export_can_overwrite_existing_writable_dxf(tmp_path) -> None:
    destination = tmp_path / "existing-master.dxf"
    destination.write_text("old content", encoding="ascii")

    export_geometry_to_dxf(_simple_geometry(), destination, include_sheet_layouts=False)

    _assert_writable_valid_r2010_dxf(destination)


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only attribute behavior")
def test_normal_export_reports_error_instead_of_overwriting_readonly_destination(tmp_path) -> None:
    destination = tmp_path / "readonly-master.dxf"
    destination.write_text("do not replace", encoding="ascii")
    os.chmod(destination, stat.S_IREAD)
    try:
        with pytest.raises(DxfExportError, match="could not be saved"):
            export_geometry_to_dxf(
                _simple_geometry(), destination, include_sheet_layouts=False
            )
        assert destination.read_text(encoding="ascii") == "do not replace"
    finally:
        os.chmod(destination, stat.S_IWRITE)


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
    assert "PRS_POLE" in document
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

    document = ezdxf.readfile(destination)
    modelspace = document.modelspace()
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
    assert document.layers.get("POLE_OFFSET").dxf.plot == 0
    start, end = _sheet_station_ranges(geometry, expected)[0]
    axis = geometry.roads[0].centerline
    sheet_axis = substring(axis, start, end)
    model_center = sheet_axis.interpolate(sheet_axis.length / 2.0)
    paper_center = viewports[0].get_transformation_matrix().transform(
        Vec3(model_center.x, model_center.y)
    )
    assert paper_center.isclose(Vec3(148.5, 126.0), abs_tol=0.01)


def test_dxf_export_can_create_modelspace_only_for_cad_editing(tmp_path) -> None:
    route = Route(
        "Main",
        "main.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.002, 13.0)),
    )
    geometry = build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 12.0, 2.0)],
        [],
    )
    destination = tmp_path / "model-only.dxf"

    export_geometry_to_dxf(
        geometry, destination, include_sheet_layouts=False
    )

    document = ezdxf.readfile(destination)
    assert document.layout_names() == ["Model", "Layout1"]
    assert len(document.modelspace().query('LWPOLYLINE[layer=="MAIN_CENTERLINE"]')) == 1


def test_modelspace_export_contains_non_plotting_sheet_break_blocks(tmp_path) -> None:
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
    destination = tmp_path / "breaks.dxf"

    export_geometry_to_dxf(geometry, destination, include_sheet_layouts=False)

    document = ezdxf.readfile(destination)
    breaks = document.modelspace().query('INSERT[name=="PRS_SHEET_BREAK"]')
    assert len(breaks) == recommended_dxf_sheet_count(geometry) - 1
    assert document.layers.get("SHEET_BREAK").dxf.plot == 0
    assert breaks[0].get_attrib_text("BREAK_ID") == "SB01"
    assert breaks[0].get_attrib_text("POLE_ID")


def test_dxf_export_draws_one_transformer_rack_block_for_group(tmp_path) -> None:
    route = Route(
        "Main",
        "main.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.002, 13.0)),
    )
    poles = [
        Pole("P1", 13.00005, 100.001, "rack left", PoleSide.LEFT, 2),
        Pole("P1/1", 13.00005, 100.001, "rack right", PoleSide.LEFT, 2),
        Pole("A1", 13.00005, 100.001, "accessory", PoleSide.LEFT, 1),
    ]
    geometry = build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 12.0, 2.0)], poles
    )
    destination = tmp_path / "rack.dxf"

    export_geometry_to_dxf(
        geometry,
        destination,
        include_sheet_layouts=False,
        transformer_rack_groups=(frozenset({"P1", "P1/1", "A1"}),),
        transformer_rack_leg_pairs=(("P1", "P1/1"),),
    )

    document = ezdxf.readfile(destination)
    modelspace = document.modelspace()
    racks = modelspace.query('INSERT[name=="PRS_TRANSFORMER_RACK"]')
    assert len(racks) == 1
    assert len(modelspace.query('INSERT[name=="PRS_POLE"]')) == 0
    assert racks[0].get_attrib_text("POLE_IDS") == "P1|P1/1|A1"
    assert racks[0].get_attrib_text("QUANTITIES") == "2|2|1"
    assert racks[0].get_attrib_text("KIND") == "TRANSFORMER_RACK"
    assert len(list(document.blocks.get("PRS_TRANSFORMER_RACK").query("SOLID"))) == 3
    labels = list(modelspace.query('TEXT[layer=="POLE_LABELS"]'))
    assert {entity.dxf.text for entity in labels} == {"P1", "P2"}
    assert all(entity.dxf.rotation == 0.0 for entity in labels)
    assert len({(entity.dxf.insert.x, entity.dxf.insert.y) for entity in labels}) == 2


def test_dxf_export_groups_one_physical_pole_and_keeps_source_metadata(tmp_path) -> None:
    route = Route(
        "Main",
        "main.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.002, 13.0)),
    )
    poles = [
        Pole("P1", 13.00005, 100.001, "work one", PoleSide.LEFT, 1),
        Pole("P2", 13.00005, 100.001, "work two", PoleSide.LEFT, 2),
    ]
    geometry = build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 12.0, 2.0)], poles
    )
    destination = tmp_path / "same-pole.dxf"

    export_geometry_to_dxf(
        geometry,
        destination,
        include_sheet_layouts=False,
        same_pole_groups=(frozenset({"P1", "P2"}),),
    )

    document = ezdxf.readfile(destination)
    poles_in_cad = document.modelspace().query('INSERT[name=="PRS_POLE"]')
    assert len(poles_in_cad) == 1
    assert poles_in_cad[0].get_attrib_text("POLE_IDS") == "P1|P2"
    assert poles_in_cad[0].get_attrib_text("DETAILS") == "work one|work two"
    assert poles_in_cad[0].get_attrib_text("QUANTITIES") == "1|2"
    assert poles_in_cad[0].get_attrib_text("STATION_M")
    assert len(list(document.blocks.get("PRS_POLE").query("SOLID"))) == 1
import ezdxf
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
