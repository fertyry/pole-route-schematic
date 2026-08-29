from __future__ import annotations

from dataclasses import replace
from xml.etree import ElementTree as ET

from pole_route.domain.pea_asset import (
    AssetMatchState,
    AssetPoleCandidate,
    AssetSideRelation,
    PEAAsset,
    PEAAssetMatch,
    PEAAssetType,
)
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.exporters.kml_qc_exporter import KML_NAMESPACE, KMLQCLaunchError
from pole_route.exporters.pea_asset_kml_qc_exporter import (
    build_pea_asset_qc_kml,
    export_pea_asset_qc_kml,
    pea_asset_qc_kml_path,
)
from pole_route.geometry.pea_linear_reference import reference_pea_poles
from pole_route.ui.main_window import MainWindow

NS = {"kml": KML_NAMESPACE}


def _route() -> Route:
    return Route(
        "ถนนทดสอบ",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )


def _pole(identifier: str, row: int, longitude: float, *, included: bool = True):
    return PEAPoleRecord(
        identifier, "DS_Pole", row, 13.0, longitude,
        included_by_default=included,
    )


def _asset(identifier: str, asset_type: PEAAssetType, longitude: float) -> PEAAsset:
    return PEAAsset(
        f"{asset_type.value}:{identifier}",
        "DS_Transformer" if asset_type is PEAAssetType.TRANSFORMER else "DS_Switch",
        7,
        asset_type,
        identifier,
        13.00001234,
        longitude,
        name="ชื่อไทย",
        raw_voltage="22 kV",
        rating="100 kVA",
        phase="3",
        equipment_subtype="ชนิดทดสอบ",
        status="ใช้งาน",
        feeder_reference="FDB-01",
        qc_warnings=("ตรวจสอบ",),
    )


def _candidate(pole, distance, relation=AssetSideRelation.SAME_SIDE):
    return AssetPoleCandidate(
        pole.source_key,
        pole.source_id,
        distance,
        pole_order=pole.source_row - 1,
        pole_included=pole.included_by_default,
        strength="strong" if distance <= 5 else "review",
        side_relation=relation,
        asset_route_offset_metres=2.0,
        pole_route_offset_metres=1.0,
    )


def _data(placemark: ET.Element) -> dict[str, str]:
    return {
        item.attrib["name"]: item.findtext("kml:value", default="", namespaces=NS)
        for item in placemark.findall("kml:ExtendedData/kml:Data", NS)
    }


def _fixture():
    route = _route()
    poles = [
        _pole("P-1", 2, 100.002),
        _pole("P-2", 3, 100.004),
        _pole("P-X", 4, 100.006, included=False),
    ]
    ordering = reference_pea_poles(poles, route)
    assets = [
        _asset("TX-ยืนยัน", PEAAssetType.TRANSFORMER, 100.00201),
        _asset("SW-เสนอ", PEAAssetType.SWITCH, 100.00401),
        _asset("TX-กำกวม", PEAAssetType.TRANSFORMER, 100.003),
        _asset("SW-ไม่พบ", PEAAssetType.SWITCH, 100.0062),
    ]
    c1, c2, cx = _candidate(poles[0], 1.25), _candidate(poles[1], 2.5), _candidate(
        poles[2], 22.0, AssetSideRelation.OPPOSITE_SIDE
    )
    matches = [
        PEAAssetMatch(
            assets[0].stable_id, AssetMatchState.CONFIRMED, (c1,),
            suggested_pole_key=poles[0].source_key,
            confirmed_pole_key=poles[0].source_key,
        ),
        PEAAssetMatch(
            assets[1].stable_id, AssetMatchState.SUGGESTED, (c2,),
            suggested_pole_key=poles[1].source_key,
        ),
        PEAAssetMatch(
            assets[2].stable_id, AssetMatchState.AMBIGUOUS, (c1, c2),
            suggested_pole_key=poles[0].source_key,
        ),
        PEAAssetMatch(assets[3].stable_id, AssetMatchState.UNMATCHED, (cx,)),
    ]
    return route, poles, ordering, assets, matches


def test_asset_qc_contains_route_poles_assets_statuses_and_source_coordinates() -> None:
    route, poles, ordering, assets, matches = _fixture()
    before = (tuple(poles), ordering, tuple(assets), tuple(matches))
    root = ET.fromstring(build_pea_asset_qc_kml(route, poles, ordering, assets, matches))
    names = [item.text for item in root.findall(".//kml:Placemark/kml:name", NS)]
    folders = [item.text for item in root.findall(".//kml:Folder/kml:name", NS)]

    assert {"Main Route", "Poles", "Transformers", "Switches", "Match Evidence"}.issubset(folders)
    assert {"START", "END", "Transformer TX-ยืนยัน", "Switch SW-เสนอ"}.issubset(names)
    assert "Pole 1 — P-1" in names
    assert "Excluded Pole — P-X" in names
    transformer = next(
        item for item in root.findall(".//kml:Placemark", NS)
        if item.findtext("kml:name", namespaces=NS) == "Transformer TX-ยืนยัน"
    )
    values = _data(transformer)
    assert transformer.findtext("kml:Point/kml:coordinates", namespaces=NS) == (
        "100.00201000,13.00001234,0"
    )
    assert values["Source Latitude"] == "13.00001234"
    assert values["Source Longitude"] == "100.00201000"
    assert values["Distance (m)"] == "1.25"
    assert values["Side Evidence"] == "SAME_SIDE"
    assert values["Rating / Capacity"] == "100 kVA"
    assert values["QC Warnings"] == "ตรวจสอบ"
    assert (tuple(poles), ordering, tuple(assets), tuple(matches)) == before


def test_relationship_lines_are_explicit_and_ambiguous_keeps_all_candidates() -> None:
    route, poles, ordering, assets, matches = _fixture()
    root = ET.fromstring(build_pea_asset_qc_kml(route, poles, ordering, assets, matches))
    evidence = root.findall(
        ".//kml:Folder[kml:name='Match Evidence']/kml:Placemark", NS
    )
    by_state = {}
    for item in evidence:
        by_state.setdefault(_data(item)["Relationship"], []).append(item)

    assert len(by_state["CONFIRMED"]) == 1
    assert len(by_state["SUGGESTED"]) == 1
    assert len(by_state["AMBIGUOUS"]) == 2
    assert len(by_state["UNMATCHED"]) == 1
    assert by_state["CONFIRMED"][0].findtext("kml:styleUrl", namespaces=NS) == "#confirmed_line"
    assert by_state["SUGGESTED"][0].findtext("kml:styleUrl", namespaces=NS) == "#suggested_line"
    assert by_state["UNMATCHED"][0].findtext("kml:styleUrl", namespaces=NS) == "#unmatched_line"
    assert _data(by_state["UNMATCHED"][0])["Side Evidence"] == "OPPOSITE_SIDE"


def test_regeneration_replaces_stale_suggestion_with_current_confirmation(tmp_path) -> None:
    route, poles, ordering, assets, matches = _fixture()
    project = tmp_path / "งาน B003.prs"
    path = pea_asset_qc_kml_path(project)
    assert path == tmp_path / "งาน B003_PEA_ASSET_QC.kml"
    export_pea_asset_qc_kml(path, route, poles, ordering, assets, matches)
    assert "SUGGESTED: SW-เสนอ → P-2" in path.read_text(encoding="utf-8")

    changed = list(matches)
    changed[1] = replace(
        changed[1], state=AssetMatchState.CONFIRMED,
        suggested_pole_key=poles[1].source_key,
        confirmed_pole_key=poles[0].source_key,
        candidates=(_candidate(poles[0], 4.0, AssetSideRelation.UNCERTAIN),),
        manual_override=True,
    )
    export_pea_asset_qc_kml(path, route, poles, ordering, assets, changed)
    payload = path.read_text(encoding="utf-8")
    assert "CONFIRMED: SW-เสนอ → P-1" in payload
    assert "SUGGESTED: SW-เสนอ → P-2" not in payload
    assert "UNCERTAIN" in payload
    assert not list(tmp_path.glob("*.tmp"))


def test_asset_google_earth_action_save_first_and_launch_failure_keeps_artifact(
    qtbot, tmp_path, monkeypatch
) -> None:
    route, poles, ordering, assets, matches = _fixture()
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_routes = [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 6.0)]
    window.current_pea_poles = poles
    window.current_pea_ordering = ordering
    window.current_pea_assets = assets
    window.current_pea_asset_matches = matches
    window._update_pea_qc_action()
    assert window.check_pea_assets_google_earth_action.isEnabled()

    monkeypatch.setattr(window, "_save_project_as", lambda: False)
    window._check_pea_assets_in_google_earth()
    assert not list(tmp_path.glob("*.kml"))

    project = tmp_path / "A_Test.prs"
    window.project_path = str(project)
    warnings = []
    monkeypatch.setattr(
        "pole_route.ui.main_window.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    monkeypatch.setattr(
        "pole_route.ui.main_window.launch_kml",
        lambda _path: (_ for _ in ()).throw(KMLQCLaunchError("launch failed")),
    )
    window._check_pea_assets_in_google_earth()
    assert (tmp_path / "A_Test_PEA_ASSET_QC.kml").exists()
    assert warnings == [("Google Earth launch failed", "launch failed")]
