import ezdxf
import pytest

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.exporters.dxf_exporter import (
    export_edited_dxf_with_sheet_layouts,
    export_geometry_to_dxf,
)
from pole_route.exporters.excel_exporter import ExcelExportSettings
from pole_route.geometry.road_geometry import build_road_network_geometry
from pole_route.importers.edited_dxf_importer import (
    EditedDxfImportError,
    inspect_edited_dxf,
)


def _export_test_master(path) -> None:
    route = Route(
        "Main",
        "main.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )
    poles = [
        Pole("P1", 13.00005, 100.002, "first", PoleSide.LEFT, 1),
        Pole("P2", 13.00005, 100.006, "second", PoleSide.LEFT, 2),
    ]
    geometry = build_road_network_geometry(
        [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 12.0, 2.0)], poles
    )
    export_geometry_to_dxf(geometry, path, include_sheet_layouts=False)


def test_inspect_edited_dxf_reads_moved_pole_blocks_and_sheet_breaks(tmp_path) -> None:
    path = tmp_path / "master.dxf"
    _export_test_master(path)
    document = ezdxf.readfile(path)
    first = next(
        entity
        for entity in document.modelspace().query("INSERT")
        if entity.dxf.name == "PRS_POLE" and entity.get_attrib_text("POLE_IDS") == "P1"
    )
    first.dxf.insert = (123.0, 456.0)
    first.dxf.rotation = 17.5
    document.saveas(path)

    result = inspect_edited_dxf(path, ("P1", "P2"))

    assert result.is_valid
    assert len(result.pole_blocks) == 2
    assert result.pole_blocks[0].pole_ids == ("P1",)
    assert result.pole_blocks[0].x == 123.0
    assert result.pole_blocks[0].y == 456.0
    assert result.pole_blocks[0].rotation == 17.5
    assert len(result.sheet_breaks) >= 1
    assert result.to_data()["pole_blocks"][0]["pole_ids"] == ("P1",)


def test_inspect_edited_dxf_reports_missing_and_unexpected_ids(tmp_path) -> None:
    path = tmp_path / "master.dxf"
    _export_test_master(path)
    document = ezdxf.readfile(path)
    pole = next(
        entity
        for entity in document.modelspace().query("INSERT")
        if entity.dxf.name == "PRS_POLE"
    )
    pole.get_attrib("POLE_IDS").dxf.text = "OTHER"
    document.saveas(path)

    result = inspect_edited_dxf(path, ("P1", "P2"))

    assert not result.is_valid
    assert result.missing_pole_ids
    assert result.unexpected_pole_ids == ("OTHER",)


def test_inspect_edited_dxf_rejects_unrelated_cad_file(tmp_path) -> None:
    path = tmp_path / "unrelated.dxf"
    document = ezdxf.new("R2010")
    document.modelspace().add_line((0, 0), (1, 1))
    document.saveas(path)

    with pytest.raises(EditedDxfImportError, match="No PRS_POLE"):
        inspect_edited_dxf(path, ("P1",))


def test_create_cad_sheets_from_edited_dxf_rebuilds_perpendicular_labels(tmp_path) -> None:
    source = tmp_path / "edited.dxf"
    destination = tmp_path / "sheets.dxf"
    _export_test_master(source)
    document = ezdxf.readfile(source)
    first = next(
        entity for entity in document.modelspace().query("INSERT")
        if entity.dxf.name == "PRS_POLE" and entity.get_attrib_text("POLE_IDS") == "P1"
    )
    first.dxf.insert = (321.0, 654.0)
    document.saveas(source)

    count = export_edited_dxf_with_sheet_layouts(
        source, destination, ExcelExportSettings(project_title="Edited CAD")
    )

    result = ezdxf.readfile(destination)
    sheets = [name for name in result.layout_names() if name.startswith("Sheet ")]
    assert count > 0
    assert sheets
    first_sheet = result.layouts.get(sheets[0])
    labels = list(first_sheet.query('TEXT[layer=="SHEET_TABLE"]'))
    assert any(entity.dxf.text.startswith("P1") and entity.dxf.rotation == 90.0 for entity in labels)
    assert result.layers.get("POLE_LABELS").dxf.plot == 0
    assert len([entity for entity in first_sheet.query("VIEWPORT") if entity.dxf.status == 2]) == 1
