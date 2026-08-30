"""Read-only Google Earth QC export for reviewed PEA point assets."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from pole_route.domain.pea_asset import (
    AssetMatchState,
    AssetPoleCandidate,
    PEAAsset,
    PEAAssetMatch,
    PEAAssetType,
)
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import PEAPoleOrdering, PEAPoleReviewEntry
from pole_route.domain.pole import Pole
from pole_route.domain.route import GeoPoint, Route
from pole_route.exporters.kml_qc_exporter import (
    KML_NAMESPACE,
    KMLQCExportError,
    write_kml_atomically,
)


def pea_asset_qc_kml_path(project_path: str | Path) -> Path:
    """Return the deterministic asset-QC artifact beside a saved project."""
    project = Path(project_path)
    if not project.name:
        raise KMLQCExportError("Save the PoleRoute project before generating asset QC KML.")
    return project.with_name(f"{project.stem}_PEA_ASSET_QC.kml")


def export_pea_asset_qc_kml(
    path: str | Path,
    main_route: Route,
    poles: list[PEAPoleRecord | Pole] | tuple[PEAPoleRecord | Pole, ...],
    ordering: PEAPoleOrdering | None,
    assets: list[PEAAsset] | tuple[PEAAsset, ...],
    matches: list[PEAAssetMatch] | tuple[PEAAssetMatch, ...],
) -> Path:
    """Atomically regenerate a disposable QC view without mutating domain state."""
    return write_kml_atomically(
        path,
        build_pea_asset_qc_kml(main_route, poles, ordering, assets, matches),
    )


def build_pea_asset_qc_kml(
    main_route: Route,
    poles: list[PEAPoleRecord | Pole] | tuple[PEAPoleRecord | Pole, ...],
    ordering: PEAPoleOrdering | None,
    assets: list[PEAAsset] | tuple[PEAAsset, ...],
    matches: list[PEAAssetMatch] | tuple[PEAAssetMatch, ...],
) -> bytes:
    """Build deterministic KML exclusively from persisted review evidence."""
    if not poles:
        raise KMLQCExportError("No pole records are available for asset QC.")
    if not assets:
        raise KMLQCExportError("No GIS assets are available for asset QC.")
    records_by_key = {_pole_key(record): record for record in poles}
    entries_by_key = {entry.source_key: entry for entry in ordering.entries} if ordering else {}
    missing = [key for key in entries_by_key if key not in records_by_key]
    if missing:
        raise KMLQCExportError(
            "Pole review state refers to missing PEA source records: " + ", ".join(missing[:3])
        )
    matches_by_asset = {match.asset_id: match for match in matches}

    kml = ET.Element(_tag("kml"))
    document = ET.SubElement(kml, _tag("Document"))
    _text(document, "name", f"{main_route.name or 'Main Route'} — Asset QC")
    _text(document, "description", _summary(assets, matches_by_asset))
    _add_styles(document)

    route_folder = _folder(document, "Main Route")
    effective_points = (
        tuple(reversed(main_route.points))
        if ordering is not None and ordering.direction_reversed
        else main_route.points
    )
    _add_route(route_folder, main_route, effective_points)
    _add_endpoint(route_folder, "START", effective_points[0])
    _add_endpoint(route_folder, "END", effective_points[-1])

    pole_folder = _folder(document, "Poles")
    if ordering is not None:
        for entry in sorted(ordering.entries, key=_pole_sort_key):
            _add_pole(pole_folder, records_by_key[entry.source_key], entry, ordering)
    else:
        for pole in sorted(poles, key=_pole_key):
            _add_generic_pole(pole_folder, pole)

    type_folders = {
        PEAAssetType.TRANSFORMER: _status_folders(_folder(document, "Transformers")),
        PEAAssetType.SWITCH: _status_folders(_folder(document, "Switches")),
        PEAAssetType.OTHER: _status_folders(_folder(document, "Unsupported / Other")),
    }
    evidence_folder = _folder(document, "Match Evidence")
    for asset in sorted(assets, key=lambda item: (item.asset_type.value, item.stable_id)):
        if asset.asset_type not in type_folders:
            continue
        match = matches_by_asset.get(asset.stable_id, PEAAssetMatch(asset.stable_id))
        _add_asset(type_folders[asset.asset_type][match.state], asset, match, entries_by_key)
        _add_evidence(evidence_folder, asset, match, records_by_key)

    return ET.tostring(kml, encoding="utf-8", xml_declaration=True)


def _tag(name: str) -> str:
    return f"{{{KML_NAMESPACE}}}{name}"


def _text(parent: ET.Element, name: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, _tag(name))
    element.text = str(value)
    return element


def _folder(parent: ET.Element, name: str) -> ET.Element:
    folder = ET.SubElement(parent, _tag("Folder"))
    _text(folder, "name", name)
    return folder


def _status_folders(parent: ET.Element) -> dict[AssetMatchState, ET.Element]:
    return {
        state: _folder(parent, state.value.title())
        for state in (
            AssetMatchState.CONFIRMED,
            AssetMatchState.SUGGESTED,
            AssetMatchState.AMBIGUOUS,
            AssetMatchState.UNMATCHED,
        )
    }


def _add_styles(document: ET.Element) -> None:
    # KML colors are aabbggrr. Status is encoded by color and asset type by icon.
    colors = {
        AssetMatchState.CONFIRMED: "ff00aa00",
        AssetMatchState.SUGGESTED: "ffff9900",
        AssetMatchState.AMBIGUOUS: "ff00aaff",
        AssetMatchState.UNMATCHED: "ff0000ff",
    }
    icons = {
        PEAAssetType.TRANSFORMER: "http://maps.google.com/mapfiles/kml/shapes/lightning.png",
        PEAAssetType.SWITCH: "http://maps.google.com/mapfiles/kml/shapes/caution.png",
        PEAAssetType.OTHER: "http://maps.google.com/mapfiles/kml/shapes/info.png",
    }
    for asset_type, icon_href in icons.items():
        for state, color in colors.items():
            style = ET.SubElement(
                document, _tag("Style"), id=f"{asset_type.value}_{state.value}"
            )
            icon_style = ET.SubElement(style, _tag("IconStyle"))
            _text(icon_style, "color", color)
            _text(icon_style, "scale", "1.0" if state is not AssetMatchState.UNMATCHED else "1.2")
            icon = ET.SubElement(icon_style, _tag("Icon"))
            _text(icon, "href", icon_href)
            label = ET.SubElement(style, _tag("LabelStyle"))
            _text(label, "color", color)
            _text(label, "scale", "0.9")
    _line_style(document, "confirmed_line", "ff00aa00", 4)
    _line_style(document, "suggested_line", "ffff9900", 2)
    _line_style(document, "ambiguous_line", "ff00aaff", 2)
    _line_style(document, "unmatched_line", "ff0000ff", 1)
    _line_style(document, "route", "ffff5500", 4)
    for style_id, color, icon_href in (
        ("pole", "ffdddddd", "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"),
        ("excluded_pole", "ff888888", "http://maps.google.com/mapfiles/kml/shapes/forbidden.png"),
        ("endpoint", "ffff00ff", "http://maps.google.com/mapfiles/kml/shapes/target.png"),
    ):
        style = ET.SubElement(document, _tag("Style"), id=style_id)
        icon_style = ET.SubElement(style, _tag("IconStyle"))
        _text(icon_style, "color", color)
        icon = ET.SubElement(icon_style, _tag("Icon"))
        _text(icon, "href", icon_href)


def _line_style(document: ET.Element, style_id: str, color: str, width: int) -> None:
    style = ET.SubElement(document, _tag("Style"), id=style_id)
    line = ET.SubElement(style, _tag("LineStyle"))
    _text(line, "color", color)
    _text(line, "width", width)


def _add_route(parent: ET.Element, route: Route, points: tuple[GeoPoint, ...]) -> None:
    placemark = ET.SubElement(parent, _tag("Placemark"))
    _text(placemark, "name", route.name or "Main Route")
    _text(placemark, "styleUrl", "#route")
    line = ET.SubElement(placemark, _tag("LineString"))
    _text(line, "tessellate", "1")
    _text(line, "coordinates", " ".join(_coordinate(p.longitude, p.latitude) for p in points))


def _add_endpoint(parent: ET.Element, name: str, point: GeoPoint) -> None:
    placemark = ET.SubElement(parent, _tag("Placemark"))
    _text(placemark, "name", name)
    _text(placemark, "styleUrl", "#endpoint")
    geometry = ET.SubElement(placemark, _tag("Point"))
    _text(geometry, "coordinates", _coordinate(point.longitude, point.latitude))


def _add_pole(
    parent: ET.Element,
    record: PEAPoleRecord,
    entry: PEAPoleReviewEntry,
    ordering: PEAPoleOrdering,
) -> None:
    placemark = ET.SubElement(parent, _tag("Placemark"))
    order = entry.confirmed_order or entry.review_order
    prefix = f"Pole {order}" if order is not None else "Excluded Pole"
    _text(placemark, "name", f"{prefix} — {record.source_id}")
    _text(placemark, "styleUrl", "#pole" if entry.included else "#excluded_pole")
    _extended(placemark, {
        "Pole ID": record.source_id,
        "Order": order if order is not None else "",
        "Station (m)": _number(entry.station_metres),
        "Route Offset (m)": _number(entry.offset_metres),
        "Source Latitude": _coordinate_number(record.latitude),
        "Source Longitude": _coordinate_number(record.longitude),
        "Included": "Yes" if entry.included else "No — excluded but retained for audit",
        "QC Status": entry.qc_status.value,
        "Review State": "Confirmed" if ordering.confirmed else "Proposed / Unconfirmed",
    })
    point = ET.SubElement(placemark, _tag("Point"))
    _text(point, "coordinates", _coordinate(record.longitude, record.latitude))


def _add_asset(
    parent: ET.Element,
    asset: PEAAsset,
    match: PEAAssetMatch,
    entries: dict[str, PEAPoleReviewEntry],
) -> None:
    placemark = ET.SubElement(parent, _tag("Placemark"))
    type_name = asset.asset_type.value.title()
    asset_id = asset.source_asset_id or asset.stable_id
    _text(placemark, "name", f"{type_name} {asset_id}")
    _text(placemark, "styleUrl", f"#{asset.asset_type.value}_{match.state.value}")
    candidate = _primary_candidate(match)
    pole_key = match.confirmed_pole_key or match.suggested_pole_key
    pole_entry = entries.get(pole_key or "")
    values = {
        "Asset Type": type_name,
        "Asset ID": asset_id,
        "Source": asset.source_provider,
        "Source File": asset.source_file,
        "Source Sheet": asset.source_sheet,
        "Source Row": asset.source_row,
        "Source Latitude": _optional_coordinate(asset.latitude),
        "Source Longitude": _optional_coordinate(asset.longitude),
        "Match State": match.state.value.upper(),
        "Pole ID": candidate.pole_id if candidate is not None else "",
        "Distance (m)": _number(candidate.distance_metres) if candidate is not None else "",
        "Pole Order": candidate.pole_order if candidate and candidate.pole_order is not None else "",
        "Pole Station (m)": _number(pole_entry.station_metres) if pole_entry else "",
        "Side Evidence": candidate.side_relation.value.upper() if candidate else "",
        "Manual Override": "Yes" if match.manual_override else "No",
        "Voltage": asset.raw_voltage if asset.raw_voltage is not None else "",
        "Rating / Capacity": asset.rating or "",
        "Phase": asset.phase or "",
        "Subtype": asset.equipment_subtype or "",
        "Status": asset.status or "",
        "Feeder / Circuit": asset.feeder_reference or "",
        "QC Warnings": "; ".join(asset.qc_warnings),
        "Source Present": "Yes" if asset.source_present else "No",
    }
    _text(placemark, "description", "\n".join(f"{key}: {value}" for key, value in values.items()))
    _extended(placemark, values)
    if asset.coordinate_valid:
        point = ET.SubElement(placemark, _tag("Point"))
        _text(point, "coordinates", _coordinate(asset.longitude, asset.latitude))


def _add_evidence(
    parent: ET.Element,
    asset: PEAAsset,
    match: PEAAssetMatch,
    poles: dict[str, PEAPoleRecord | Pole],
) -> None:
    if not asset.coordinate_valid:
        return
    if match.state is AssetMatchState.CONFIRMED:
        candidates = _candidate_for_key(match, match.confirmed_pole_key)
    elif match.state is AssetMatchState.SUGGESTED:
        candidates = _candidate_for_key(match, match.suggested_pole_key)
    elif match.state is AssetMatchState.AMBIGUOUS:
        candidates = tuple(item for item in match.candidates if item.pole_included is not False)
    else:
        # A weak nearest-candidate line is useful audit evidence, never a confirmation.
        candidates = match.candidates[:1]
    for candidate in candidates:
        pole = poles.get(candidate.pole_source_key)
        if pole is None:
            continue
        placemark = ET.SubElement(parent, _tag("Placemark"))
        asset_id = asset.source_asset_id or asset.stable_id
        _text(
            placemark,
            "name",
            f"{match.state.value.upper()}: {asset_id} → {candidate.pole_id}",
        )
        _text(placemark, "styleUrl", f"#{match.state.value}_line")
        values = {
            "Relationship": match.state.value.upper(),
            "Asset ID": asset_id,
            "Pole ID": candidate.pole_id,
            "Distance (m)": _number(candidate.distance_metres),
            "Strength": candidate.strength,
            "Side Evidence": candidate.side_relation.value.upper(),
            "Manual Override": "Yes" if match.manual_override else "No",
        }
        _text(placemark, "description", "\n".join(f"{key}: {value}" for key, value in values.items()))
        _extended(placemark, values)
        line = ET.SubElement(placemark, _tag("LineString"))
        _text(line, "tessellate", "1")
        _text(
            line,
            "coordinates",
            f"{_coordinate(asset.longitude, asset.latitude)} "
            f"{_coordinate(pole.longitude, pole.latitude)}",
        )


def _candidate_for_key(
    match: PEAAssetMatch, key: str | None
) -> tuple[AssetPoleCandidate, ...]:
    if key is None:
        return ()
    return tuple(item for item in match.candidates if item.pole_source_key == key)[:1]


def _primary_candidate(match: PEAAssetMatch) -> AssetPoleCandidate | None:
    key = match.confirmed_pole_key or match.suggested_pole_key
    selected = _candidate_for_key(match, key)
    return selected[0] if selected else (match.candidates[0] if match.candidates else None)


def _extended(parent: ET.Element, values: dict[str, object]) -> None:
    extended = ET.SubElement(parent, _tag("ExtendedData"))
    for name, value in values.items():
        data = ET.SubElement(extended, _tag("Data"), name=name)
        _text(data, "value", value)


def _summary(assets: list[PEAAsset] | tuple[PEAAsset, ...], matches) -> str:
    counts = Counter(
        (asset.asset_type, matches.get(asset.stable_id, PEAAssetMatch(asset.stable_id)).state)
        for asset in assets
    )
    lines = ["Read-only QC artifact. Suggested and ambiguous links are evidence, not truth."]
    for asset_type in PEAAssetType:
        parts = [
            f"{state.value}={counts[(asset_type, state)]}"
            for state in AssetMatchState
        ]
        lines.append(f"{asset_type.value.title()}: " + ", ".join(parts))
    return "\n".join(lines)


def _pole_sort_key(entry: PEAPoleReviewEntry) -> tuple[int, int, str]:
    order = entry.confirmed_order or entry.review_order
    return (0 if entry.included else 1, order if order is not None else 10**9, entry.source_key)


def _pole_key(pole: PEAPoleRecord | Pole) -> str:
    return pole.source_key if isinstance(pole, PEAPoleRecord) else f"GENERIC_POLE:{pole.number}"


def _add_generic_pole(parent: ET.Element, pole: PEAPoleRecord | Pole) -> None:
    pole_id = pole.source_id if isinstance(pole, PEAPoleRecord) else pole.number
    placemark = ET.SubElement(parent, _tag("Placemark"))
    _text(placemark, "name", f"Pole — {pole_id}")
    _text(placemark, "styleUrl", "#pole")
    _extended(placemark, {
        "Pole ID": pole_id,
        "Source Latitude": _coordinate_number(pole.latitude),
        "Source Longitude": _coordinate_number(pole.longitude),
    })
    point = ET.SubElement(placemark, _tag("Point"))
    _text(point, "coordinates", _coordinate(pole.longitude, pole.latitude))


def _coordinate(longitude: float, latitude: float) -> str:
    return f"{longitude:.8f},{latitude:.8f},0"


def _coordinate_number(value: float) -> str:
    return f"{value:.8f}"


def _optional_coordinate(value: float | None) -> str:
    return "" if value is None else _coordinate_number(value)


def _number(value: float) -> str:
    return f"{value:.2f}"
