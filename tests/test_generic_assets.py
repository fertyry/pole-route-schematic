import csv
from dataclasses import replace

from openpyxl import Workbook

from pole_route.domain.pea_asset import (
    AssetMatchState,
    PEAAsset,
    PEAAssetMatch,
    PEAAssetType,
    merge_pea_assets,
)
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pole import Pole
from pole_route.domain.route import GeoPoint, Route
from pole_route.exporters.pea_asset_kml_qc_exporter import build_pea_asset_qc_kml
from pole_route.geometry.pea_asset_matching import match_pea_assets
from pole_route.importers.asset_importer import (
    assets_from_table,
    inspect_asset_file,
    suggest_asset_mapping,
)
from pole_route.project.storage import pea_assets_from_data, pea_assets_to_data
from pole_route.ui.pea_asset_review_dialog import PEAAssetReviewDialog

HEADERS = [
    "Asset ID", "Type", "Latitude", "Longitude", "Description", "Voltage",
    "Capacity", "Phase", "Subtype", "Status", "Circuit", "Source ID",
]


def _write_csv(path, rows, headers=HEADERS):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _row(identifier="TX-1", kind="Transformer", latitude="13.0", longitude="100.0"):
    return [identifier, kind, latitude, longitude, "หม้อแปลงหน้าโรงเรียน", "22 kV", "100 kVA", "3", "Rack", "Active", "F01", identifier]


def _import(path):
    table = inspect_asset_file(path)
    mapping = suggest_asset_mapping(table.headers)
    return assets_from_table(table, mapping)


def test_generic_csv_maps_required_and_optional_fields(tmp_path):
    path = tmp_path / "assets.csv"
    _write_csv(path, [_row()])
    asset = _import(path)[0]
    assert asset.asset_type is PEAAssetType.TRANSFORMER
    assert asset.source_provider == "GENERIC_FILE"
    assert asset.source_file == "assets.csv"
    assert asset.name == "หม้อแปลงหน้าโรงเรียน"
    assert asset.rating == "100 kVA"
    assert asset.phase == "3"
    assert asset.feeder_reference == "F01"
    assert asset.latitude == 13.0 and asset.longitude == 100.0


def test_generic_xlsx_and_thai_headers(tmp_path):
    path = tmp_path / "อุปกรณ์.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["รหัสอุปกรณ์", "ประเภท", "ละติจูด", "ลองจิจูด", "รายละเอียด"])
    sheet.append(["SW-1", "สวิตช์", 13.1, 100.1, "สวิตช์หน้าอาคาร"])
    workbook.save(path)
    asset = _import(path)[0]
    assert asset.asset_type is PEAAssetType.SWITCH
    assert asset.source_asset_id == "SW-1"
    assert asset.name == "สวิตช์หน้าอาคาร"


def test_invalid_coordinates_and_unknown_type_are_retained_for_audit(tmp_path):
    path = tmp_path / "assets.csv"
    _write_csv(path, [["X-1", "Capacitor", "bad", "200", "", "", "", "", "", "", "", "X-1"]])
    asset = _import(path)[0]
    assert asset.asset_type is PEAAssetType.OTHER
    assert not asset.coordinate_valid
    assert any("Latitude" in warning for warning in asset.qc_warnings)
    assert any("Unsupported asset type" in warning for warning in asset.qc_warnings)


def test_missing_id_uses_stable_content_fingerprint_across_row_reorder(tmp_path):
    first = tmp_path / "assets.csv"
    rows = [_row("", "TX", "13.01", "100.01"), _row("SW-2", "SW", "13.02", "100.02")]
    _write_csv(first, rows)
    before = {asset.name + str(asset.latitude): asset.stable_id for asset in _import(first)}
    _write_csv(first, list(reversed(rows)))
    after = {asset.name + str(asset.latitude): asset.stable_id for asset in _import(first)}
    assert before == after
    assert any("fingerprint" in warning for warning in _import(first)[1].qc_warnings)


def test_generic_assets_match_generic_and_pea_poles():
    asset = PEAAsset(
        "generic:a:tx-1", "a.csv", 2, PEAAssetType.TRANSFORMER, "TX-1",
        13.0, 100.00001, source_provider="GENERIC_FILE", source_file="a.csv",
    )
    generic = match_pea_assets([asset], [Pole("G-1", 13.0, 100.0)])[0]
    pea_pole = PEAPoleRecord("P-1", "DS_Pole", 2, 13.0, 100.0)
    pea = match_pea_assets([asset], [pea_pole])[0]
    assert generic.state is AssetMatchState.SUGGESTED
    assert generic.suggested_pole_key == "GENERIC_POLE:G-1"
    assert pea.state is AssetMatchState.SUGGESTED
    assert pea.suggested_pole_key == pea_pole.source_key


def test_reimport_updates_preserves_confirmation_and_retains_missing(tmp_path):
    path = tmp_path / "assets.csv"
    _write_csv(path, [_row("TX-1"), _row("SW-1", "Switch", "13.1", "100.1")])
    original = _import(path)
    pole = Pole("P-1", 13.0, 100.0)
    confirmed = match_pea_assets([original[0]], [pole])[0].confirm("GENERIC_POLE:P-1")
    updated_row = _row("TX-1")
    updated_row[4] = "updated description"
    _write_csv(path, [updated_row])
    refreshed = _import(path)
    merged = merge_pea_assets(original, [confirmed], refreshed, imported_sheets={path.name})
    assert len(merged.assets) == 2
    assert merged.missing_from_source == 1
    assert next(item for item in merged.assets if item.source_asset_id == "TX-1").name == "updated description"
    assert next(item for item in merged.assets if item.source_asset_id == "SW-1").source_present is False
    assert next(item for item in merged.matches if item.asset_id == original[0].stable_id).state is AssetMatchState.CONFIRMED


def test_generic_asset_persistence_and_old_pea_default(tmp_path):
    path = tmp_path / "assets.csv"
    _write_csv(path, [_row()])
    asset = _import(path)[0]
    assert pea_assets_from_data(pea_assets_to_data([asset])) == [asset]
    old = pea_assets_to_data([asset])[0]
    old.pop("source_provider")
    old.pop("source_file")
    restored = pea_assets_from_data([old])[0]
    assert restored.source_provider == "PEA_GIS" and restored.source_file == ""


def test_review_filters_source_type_and_state(qtbot, tmp_path):
    path = tmp_path / "assets.csv"
    _write_csv(path, [_row()])
    generic = _import(path)[0]
    pea = replace(generic, stable_id="DS_Switch:sw-1", asset_type=PEAAssetType.SWITCH, source_provider="PEA_GIS")
    matches = [PEAAssetMatch(generic.stable_id, AssetMatchState.UNMATCHED), PEAAssetMatch(pea.stable_id, AssetMatchState.CONFIRMED)]
    dialog = PEAAssetReviewDialog([generic, pea], matches, [])
    qtbot.addWidget(dialog)
    dialog.source_filter.setCurrentIndex(dialog.source_filter.findData("GENERIC_FILE"))
    assert dialog.table.rowCount() == 1
    dialog.source_filter.setCurrentIndex(0)
    dialog.type_filter.setCurrentIndex(dialog.type_filter.findData("switch"))
    assert dialog.table.rowCount() == 1
    dialog.type_filter.setCurrentIndex(0)
    dialog.state_filter.setCurrentIndex(dialog.state_filter.findData("confirmed"))
    assert dialog.table.rowCount() == 1


def test_generic_asset_and_pole_kml_keep_source_coordinates(tmp_path):
    path = tmp_path / "assets.csv"
    _write_csv(path, [_row()])
    asset = _import(path)[0]
    pole = Pole("P-1", 13.0, 100.00001)
    match = match_pea_assets([asset], [pole])[0]
    route = Route("R", "test", (GeoPoint(99.99, 13.0), GeoPoint(100.01, 13.0)))
    kml = build_pea_asset_qc_kml(route, [pole], None, [asset], [match]).decode("utf-8")
    assert "GENERIC_FILE" in kml
    assert "100.00000000,13.00000000,0" in kml
    assert "GENERIC_POLE:P-1" not in kml  # internal key is not user-visible metadata
