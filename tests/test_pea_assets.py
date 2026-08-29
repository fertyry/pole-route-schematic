from __future__ import annotations

from dataclasses import replace

from openpyxl import Workbook

from pole_route.domain.pea_asset import AssetMatchState, PEAAsset, PEAAssetType, merge_pea_assets
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import PEAPoleOrdering, PEAPoleReviewEntry, PoleQCStatus
from pole_route.geometry.pea_asset_matching import match_pea_assets
from pole_route.importers.pea_assets import import_pea_assets
from pole_route.importers.pea_gis import discover_pea_workbook
from pole_route.project.storage import (
    load_project_file,
    pea_asset_matches_from_data,
    pea_asset_matches_to_data,
    pea_assets_from_data,
    pea_assets_to_data,
    save_project_file,
)


def _workbook(path):
    workbook = Workbook()
    transformer = workbook.active
    transformer.title = "DS_Transformer"
    transformer.append(["Transformer ID", "Latitude", "Longitude", "Capacity", "Phase", "Custom"])
    transformer.append(["TX-1", 13.0, 100.0, "250 kVA", "3", "เก็บไว้"])
    transformer.append([None, "bad", None, None, None, "audit"])
    switch = workbook.create_sheet("DS_Switch")
    switch.append(["Switch ID", "Lat", "Lng", "Switch Type", "Status"])
    switch.append(["SW-1", 13.0001, 100.0001, "LBS", "Active"])
    workbook.create_sheet("DS_Capacitor")
    workbook.save(path)


def _pole(source_id, longitude, *, row=2):
    return PEAPoleRecord(source_id, "DS_Pole", row, 13.0, longitude)


def _asset(stable_id="DS_Transformer:tx-1", longitude=100.0):
    return PEAAsset(stable_id, "DS_Transformer", 2, PEAAssetType.TRANSFORMER,
                    "TX-1", 13.0, longitude, {"Custom": "เก็บไว้"})


def test_asset_profiles_discovery_parse_qc_and_raw_attributes(tmp_path):
    path = tmp_path / "pea.xlsx"
    _workbook(path)
    discovery = discover_pea_workbook(path)
    assert [item.profile for item in discovery.supported_sheets] == ["DS_Transformer", "DS_Switch"]
    assert discovery.unsupported_ds_sheets == ("DS_Capacitor",)
    assets = import_pea_assets(path)
    assert len(assets) == 3
    transformer = assets[0]
    assert transformer.stable_id == "DS_Transformer:tx-1"
    assert transformer.rating == "250 kVA" and transformer.phase == "3"
    assert transformer.raw_attributes["Custom"] == "เก็บไว้"
    invalid = assets[1]
    assert not invalid.coordinate_valid and len(invalid.qc_warnings) == 3
    assert "fingerprint:" in invalid.stable_id
    switch = assets[2]
    assert switch.asset_type is PEAAssetType.SWITCH
    assert switch.equipment_subtype == "LBS" and switch.status == "Active"


def test_asset_identity_survives_row_order_change(tmp_path):
    first = tmp_path / "first.xlsx"; second = tmp_path / "second.xlsx"
    _workbook(first); _workbook(second)
    workbook = Workbook(); sheet = workbook.active; sheet.title = "DS_Transformer"
    sheet.append(["Transformer ID", "Latitude", "Longitude"])
    sheet.append(["OTHER", 13.1, 100.1]); sheet.append(["TX-1", 13.0, 100.0]); workbook.save(second)
    one = import_pea_assets(first)[0]
    two = next(item for item in import_pea_assets(second) if item.source_asset_id == "TX-1")
    assert one.stable_id == two.stable_id and one.source_row != two.source_row


def test_matcher_suggests_deterministically_and_keeps_suggestion_unconfirmed():
    asset = _asset(longitude=100.00001)
    poles = [_pole("B", 100.00002, row=3), _pole("A", 100.00002, row=2)]
    match = match_pea_assets([asset], poles)[0]
    assert match.state is AssetMatchState.AMBIGUOUS
    assert [item.pole_id for item in match.candidates[:2]] == ["A", "B"]
    assert match.suggested_pole_key is not None and match.confirmed_pole_key is None
    assert match.candidates[0].strength == "strong"


def test_matcher_invalid_no_poles_and_excluded_pole_handling():
    invalid = replace(_asset(), latitude=None)
    assert match_pea_assets([invalid], [ _pole("A", 100.0) ])[0].state is AssetMatchState.UNMATCHED
    pole = _pole("A", 100.0)
    entry = PEAPoleReviewEntry(pole.source_key, "A", 0, 0, 13, 100, 1, 1, None, False, PoleQCStatus.NORMAL)
    ordering = PEAPoleOrdering((entry,))
    match = match_pea_assets([_asset()], [pole], ordering)[0]
    assert match.candidates[0].pole_included is False
    assert match.state is AssetMatchState.UNMATCHED
    assert match_pea_assets([_asset()], [])[0].state is AssetMatchState.UNMATCHED


def test_manual_confirmation_survives_recompute_and_reimport():
    poles = [_pole("A", 100.0, row=2), _pole("B", 100.0001, row=3)]
    suggested = match_pea_assets([_asset()], poles)[0]
    confirmed = suggested.confirm(poles[1].source_key)
    recomputed = match_pea_assets([_asset()], poles, previous=[confirmed])[0]
    assert recomputed.state is AssetMatchState.CONFIRMED
    assert recomputed.confirmed_pole_key == poles[1].source_key and recomputed.manual_override
    refreshed = replace(_asset(), rating="500 kVA", source_row=9)
    merged = merge_pea_assets([_asset()], [confirmed], [refreshed], imported_sheets={"DS_Transformer"})
    assert len(merged.assets) == 1 and merged.assets[0].rating == "500 kVA"
    assert merged.matches[0] == confirmed


def test_reimport_marks_missing_and_adds_new_without_duplicate():
    existing = _asset()
    new = replace(_asset("DS_Transformer:tx-2"), source_asset_id="TX-2")
    merged = merge_pea_assets([existing], [], [new], imported_sheets={"DS_Transformer"})
    assert (merged.added, merged.updated, merged.missing_from_source) == (1, 0, 1)
    assert len(merged.assets) == 2
    assert next(item for item in merged.assets if item.stable_id == existing.stable_id).source_present is False


def test_asset_and_match_project_round_trip_and_legacy_default(tmp_path):
    asset = _asset(); pole = _pole("A", 100.0)
    match = match_pea_assets([asset], [pole])[0].confirm(pole.source_key)
    path = tmp_path / "new.prs"
    save_project_file(path, {"pea_assets": pea_assets_to_data([asset]),
                             "pea_asset_matches": pea_asset_matches_to_data([match])})
    document = load_project_file(path)
    assert pea_assets_from_data(document["pea_assets"]) == [asset]
    assert pea_asset_matches_from_data(document["pea_asset_matches"]) == [match]
    legacy = tmp_path / "old.prs"; save_project_file(legacy, {})
    old = load_project_file(legacy)
    assert old["pea_assets"] == [] and old["pea_asset_matches"] == []
