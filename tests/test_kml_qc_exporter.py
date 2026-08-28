from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import PoleQCStatus
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.exporters.kml_qc_exporter import (
    KML_NAMESPACE,
    KMLQCLaunchError,
    build_pea_qc_kml,
    export_pea_qc_kml,
    launch_kml,
    pea_qc_kml_path,
)
from pole_route.geometry.pea_linear_reference import reference_pea_poles
from pole_route.ui.main_window import MainWindow

NS = {"kml": KML_NAMESPACE}


def _route() -> Route:
    return Route(
        "ถนนทดสอบ",
        "route.kml",
        (
            GeoPoint(100.0, 13.0),
            GeoPoint(100.005, 13.0),
            GeoPoint(100.01, 13.0),
        ),
    )


def _record(
    source_id: str,
    row: int,
    longitude: float,
    latitude: float = 13.0,
    *,
    included: bool = True,
) -> PEAPoleRecord:
    return PEAPoleRecord(
        source_id=source_id,
        source_sheet="DS_Pole",
        source_row=row,
        latitude=latitude,
        longitude=longitude,
        raw_height="12 เมตร",
        height_metres=12.0,
        raw_voltage="22-33 kV",
        voltage_min_kv=22.0,
        voltage_max_kv=33.0,
        included_by_default=included,
        qc_warnings=("ตรวจสอบภาษาไทย",) if source_id == "กฟภ-1" else (),
    )


def _data(placemark: ET.Element) -> dict[str, str]:
    return {
        item.attrib["name"]: item.findtext("kml:value", default="", namespaces=NS)
        for item in placemark.findall("kml:ExtendedData/kml:Data", NS)
    }


def test_kml_is_valid_contains_route_endpoints_and_unicode_audit_fields() -> None:
    records = [_record("กฟภ-1", 2, 100.002, 13.0001), _record("P-2", 3, 100.008)]
    ordering = reference_pea_poles(records, _route())

    payload = build_pea_qc_kml(_route(), records, ordering)
    root = ET.fromstring(payload)
    names = [item.text for item in root.findall(".//kml:Placemark/kml:name", NS)]
    route_coordinates = root.findtext(
        ".//kml:Placemark[kml:name='ถนนทดสอบ']/kml:LineString/kml:coordinates",
        namespaces=NS,
    )
    pole = next(
        item for item in root.findall(".//kml:Placemark", NS)
        if _data(item).get("Pole ID") == "กฟภ-1"
    )
    audit = _data(pole)

    assert root.tag == f"{{{KML_NAMESPACE}}}kml"
    assert "ถนนทดสอบ" in payload.decode("utf-8")
    assert {"START", "END", "Order 1", "Order 2"}.issubset(names)
    assert route_coordinates == (
        "100.00000000,13.00000000,0 100.00500000,13.00000000,0 "
        "100.01000000,13.00000000,0"
    )
    assert audit["Order"] == "1"
    assert audit["Pole ID"] == "กฟภ-1"
    assert audit["Latitude"] == "13.00010000"
    assert audit["Longitude"] == "100.00200000"
    assert audit["Height (m)"] == "12"
    assert audit["Raw Voltage"] == "22-33 kV"
    assert audit["Normalized Voltage (kV)"] == "22–33"
    assert audit["Station (m)"]
    assert audit["Offset (m)"]
    assert audit["QC Status"] == PoleQCStatus.REVIEW.value
    assert audit["Included"] == "Yes"
    assert audit["Review State"] == "Proposed / Unconfirmed"


def test_manual_order_is_used_without_exporter_station_resort_and_state_is_not_mutated() -> None:
    records = [_record("A", 2, 100.002), _record("B", 3, 100.008)]
    automatic = reference_pea_poles(records, _route())
    ordering = automatic.move(records[1].source_key, -1).confirm()
    before = ordering

    root = ET.fromstring(build_pea_qc_kml(_route(), records, ordering))
    included = root.findall(".//kml:Folder[kml:name='Included Poles']/kml:Placemark", NS)

    assert [item.findtext("kml:name", namespaces=NS) for item in included] == [
        "Order 1", "Order 2"
    ]
    assert [_data(item)["Pole ID"] for item in included] == ["B", "A"]
    assert all(_data(item)["Manual Override"] == "Yes" for item in included)
    assert all(_data(item)["Review State"] == "Confirmed" for item in included)
    assert ordering == before


def test_reverse_state_changes_effective_start_end_and_line_direction() -> None:
    records = [_record("A", 2, 100.002), _record("B", 3, 100.008)]
    ordering = reference_pea_poles(records, _route(), direction_reversed=True)
    root = ET.fromstring(build_pea_qc_kml(_route(), records, ordering))
    route_coordinates = root.findtext(
        ".//kml:Placemark[kml:name='ถนนทดสอบ']/kml:LineString/kml:coordinates",
        namespaces=NS,
    )
    start = root.findtext(
        ".//kml:Placemark[kml:name='START']/kml:Point/kml:coordinates",
        namespaces=NS,
    )

    assert route_coordinates.startswith("100.01000000,13.00000000,0")
    assert start == "100.01000000,13.00000000,0"
    assert [_data(item)["Pole ID"] for item in root.findall(
        ".//kml:Folder[kml:name='Included Poles']/kml:Placemark", NS
    )] == ["B", "A"]


def test_qc_and_excluded_styles_are_deterministic_and_excluded_remains_visible() -> None:
    records = [
        _record("Normal", 2, 100.002),
        _record("Review", 3, 100.004, 13.0001),
        _record("Strong", 4, 100.006, 13.0002),
        _record("Excluded", 5, 100.008, included=False),
    ]
    ordering = reference_pea_poles(records, _route())
    root = ET.fromstring(build_pea_qc_kml(_route(), records, ordering))
    styles = {
        _data(item).get("Pole ID"): item.findtext("kml:styleUrl", namespaces=NS)
        for item in root.findall(".//kml:Placemark", NS)
        if _data(item)
    }

    assert styles == {
        "Normal": "#normal",
        "Review": "#review",
        "Strong": "#strong_review",
        "Excluded": "#excluded",
    }
    excluded = next(
        item for item in root.findall(".//kml:Placemark", NS)
        if _data(item).get("Pole ID") == "Excluded"
    )
    assert excluded.findtext("kml:name", namespaces=NS) == "Excluded — Excluded"
    assert _data(excluded)["Included"] == "No"


def test_project_path_is_deterministic_and_repeated_export_replaces_same_file(tmp_path) -> None:
    project = tmp_path / "งาน A001.prs"
    path = pea_qc_kml_path(project)
    records = [_record("A", 2, 100.002)]
    first = reference_pea_poles(records, _route())

    assert path == tmp_path / "งาน A001_PEA_QC.kml"
    assert export_pea_qc_kml(path, _route(), records, first) == path
    first_bytes = path.read_bytes()
    second = first.confirm()
    assert export_pea_qc_kml(path, _route(), records, second) == path
    assert path.read_bytes() != first_bytes
    assert list(tmp_path.glob("*.kml")) == [path]
    assert not list(tmp_path.glob("*.tmp"))


def test_launch_failure_keeps_generated_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "project_PEA_QC.kml"
    path.write_text("<kml/>", encoding="utf-8")

    def fail(_path: str) -> None:
        raise OSError("association missing")

    monkeypatch.setattr("pole_route.exporters.kml_qc_exporter.os.startfile", fail)
    with pytest.raises(KMLQCLaunchError, match="generated"):
        launch_kml(path)
    assert path.exists()


def test_google_earth_action_requires_save_and_launch_failure_keeps_kml(
    qtbot, tmp_path, monkeypatch
) -> None:
    route = _route()
    records = [_record("A", 2, 100.002)]
    ordering = reference_pea_poles(records, route)
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_routes = [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 6.0)]
    window.current_route = route
    window.current_pea_poles = records
    window.current_pea_ordering = ordering
    window._update_pea_qc_action()

    assert window.check_google_earth_action.isEnabled()
    monkeypatch.setattr(window, "_save_project_as", lambda: False)
    window._check_pea_qc_in_google_earth()
    assert not list(tmp_path.glob("*.kml"))

    project = tmp_path / "A001.prs"
    window.project_path = str(project)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "pole_route.ui.main_window.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    monkeypatch.setattr(
        "pole_route.ui.main_window.launch_kml",
        lambda _path: (_ for _ in ()).throw(KMLQCLaunchError("launch failed")),
    )
    window._check_pea_qc_in_google_earth()

    assert (tmp_path / "A001_PEA_QC.kml").exists()
    assert warnings == [("Google Earth launch failed", "launch failed")]


def test_google_earth_action_reports_missing_route_and_missing_pea_data(
    qtbot, monkeypatch
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "pole_route.ui.main_window.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    window._check_pea_qc_in_google_earth()
    assert "Exactly one Main Route" in warnings[-1][1]

    route = _route()
    window.current_routes = [ClassifiedRoute(route, RouteType.MAIN_ROUTE, 6.0)]
    window.current_route = route
    window._check_pea_qc_in_google_earth()
    assert "Import PEA GIS data" in warnings[-1][1]
