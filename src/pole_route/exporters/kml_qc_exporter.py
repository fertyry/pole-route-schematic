"""Persistent Google Earth QC export for reviewed PEA GIS poles."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import (
    PEAPoleOrdering,
    PEAPoleReviewEntry,
    PoleQCStatus,
)
from pole_route.domain.route import GeoPoint, Route

KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NAMESPACE)


class KMLQCExportError(ValueError):
    """The current project state cannot produce a trustworthy QC KML."""


class KMLQCLaunchError(RuntimeError):
    """The generated QC KML could not be opened by Windows."""


def pea_qc_kml_path(project_path: str | Path) -> Path:
    """Return the one deterministic QC-artifact path beside a saved project."""
    project = Path(project_path)
    if not project.name:
        raise KMLQCExportError("Save the PoleRoute project before generating QC KML.")
    return project.with_name(f"{project.stem}_PEA_QC.kml")


def export_pea_qc_kml(
    path: str | Path,
    main_route: Route,
    records: list[PEAPoleRecord],
    ordering: PEAPoleOrdering,
) -> Path:
    """Atomically replace a persistent KML without mutating project-domain state."""
    payload = build_pea_qc_kml(main_route, records, ordering)
    return write_kml_atomically(path, payload)


def write_kml_atomically(path: str | Path, payload: bytes) -> Path:
    """Atomically replace a generated KML artifact and leave no stale temp file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.stem}-",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise KMLQCExportError(f"Could not write Google Earth QC file: {error}") from error
    return destination


def launch_kml(path: str | Path) -> None:
    """Open KML through the user's Windows file association."""
    source = Path(path)
    try:
        startfile = os.startfile
        startfile(str(source))
    except (AttributeError, OSError) as error:
        raise KMLQCLaunchError(
            "The QC KML was generated but Windows could not open it. "
            "Open the file manually or associate .kml with Google Earth Pro. "
            f"File: {source}"
        ) from error


def build_pea_qc_kml(
    main_route: Route,
    records: list[PEAPoleRecord],
    ordering: PEAPoleOrdering,
) -> bytes:
    """Build UTF-8 KML from the current A2 review state, preserving its exact order."""
    records_by_key = {record.source_key: record for record in records}
    missing = [entry.source_key for entry in ordering.entries if entry.source_key not in records_by_key]
    if missing:
        raise KMLQCExportError(
            "Pole review state refers to missing PEA source records: " + ", ".join(missing[:3])
        )
    if not ordering.entries:
        raise KMLQCExportError("No reviewed PEA pole records are available for QC export.")

    kml = ET.Element(_tag("kml"))
    document = ET.SubElement(kml, _tag("Document"))
    state = "Confirmed" if ordering.confirmed else "Proposed / Unconfirmed"
    _text(document, "name", f"{main_route.name or 'Main Route'} — PEA Pole QC — {state}")
    _add_styles(document)

    route_folder = _folder(document, "Main Route")
    effective_points = (
        tuple(reversed(main_route.points)) if ordering.direction_reversed else main_route.points
    )
    _add_route(route_folder, main_route, effective_points)
    _add_endpoint(route_folder, "START", effective_points[0], "Effective pole-order start")
    _add_endpoint(route_folder, "END", effective_points[-1], "Effective pole-order end")

    included_folder = _folder(document, "Included Poles")
    excluded_folder = _folder(document, "Excluded / Review Poles")
    # ordered_included() is the canonical A2 ordering operation. The exporter deliberately
    # does not derive or independently sort by station.
    for entry in ordering.ordered_included():
        _add_pole(included_folder, records_by_key[entry.source_key], entry, ordering)
    for entry in ordering.entries:
        if not entry.included:
            _add_pole(excluded_folder, records_by_key[entry.source_key], entry, ordering)

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


def _add_styles(document: ET.Element) -> None:
    # KML colors use aabbggrr ordering.
    colors = {
        "normal": "ff00aa00",
        "review": "ff00aaff",
        "strong_review": "ff0000ff",
        "excluded": "ff888888",
        "route": "ffff5500",
        "endpoint": "ffff00ff",
    }
    for style_id in ("normal", "review", "strong_review", "excluded", "endpoint"):
        style = ET.SubElement(document, _tag("Style"), id=style_id)
        icon_style = ET.SubElement(style, _tag("IconStyle"))
        _text(icon_style, "color", colors[style_id])
        _text(icon_style, "scale", "0.9")
        icon = ET.SubElement(icon_style, _tag("Icon"))
        _text(icon, "href", "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png")
        label_style = ET.SubElement(style, _tag("LabelStyle"))
        _text(label_style, "color", colors[style_id])
        _text(label_style, "scale", "0.9")
    route_style = ET.SubElement(document, _tag("Style"), id="route")
    line_style = ET.SubElement(route_style, _tag("LineStyle"))
    _text(line_style, "color", colors["route"])
    _text(line_style, "width", "4")


def _add_route(parent: ET.Element, route: Route, points: tuple[GeoPoint, ...]) -> None:
    placemark = ET.SubElement(parent, _tag("Placemark"))
    _text(placemark, "name", route.name or "Main Route")
    _text(placemark, "styleUrl", "#route")
    line = ET.SubElement(placemark, _tag("LineString"))
    _text(line, "tessellate", "1")
    _text(line, "coordinates", " ".join(_coordinate(point) for point in points))


def _add_endpoint(parent: ET.Element, name: str, point: GeoPoint, description: str) -> None:
    placemark = ET.SubElement(parent, _tag("Placemark"))
    _text(placemark, "name", name)
    _text(placemark, "description", description)
    _text(placemark, "styleUrl", "#endpoint")
    geometry = ET.SubElement(placemark, _tag("Point"))
    _text(geometry, "coordinates", _coordinate(point))


def _add_pole(
    parent: ET.Element,
    record: PEAPoleRecord,
    entry: PEAPoleReviewEntry,
    ordering: PEAPoleOrdering,
) -> None:
    placemark = ET.SubElement(parent, _tag("Placemark"))
    visible_order = entry.review_order
    _text(
        placemark,
        "name",
        f"Order {visible_order}" if entry.included and visible_order is not None
        else f"Excluded — {record.source_id}",
    )
    style = "excluded" if not entry.included else {
        PoleQCStatus.NORMAL: "normal",
        PoleQCStatus.REVIEW: "review",
        PoleQCStatus.STRONG_REVIEW: "strong_review",
    }[entry.qc_status]
    _text(placemark, "styleUrl", f"#{style}")
    extended = ET.SubElement(placemark, _tag("ExtendedData"))
    values = {
        "Order": visible_order if visible_order is not None else "",
        "Pole ID": record.source_id,
        "Latitude": _number(record.latitude, 8),
        "Longitude": _number(record.longitude, 8),
        "Height (m)": _optional_number(record.height_metres),
        "Raw Voltage": record.raw_voltage if record.raw_voltage is not None else "",
        "Normalized Voltage (kV)": _voltage_range(record),
        "Station (m)": _number(entry.station_metres, 2),
        "Offset (m)": _number(entry.offset_metres, 2),
        "QC Status": entry.qc_status.value,
        "QC Reasons": "; ".join(entry.qc_reasons),
        "Included": "Yes" if entry.included else "No",
        "Manual Override": "Yes" if ordering.manual_override else "No",
        "Review State": "Confirmed" if ordering.confirmed else "Proposed / Unconfirmed",
        "Source Key": entry.source_key,
    }
    for name, value in values.items():
        data = ET.SubElement(extended, _tag("Data"), name=name)
        _text(data, "value", value)
    point = ET.SubElement(placemark, _tag("Point"))
    _text(point, "coordinates", f"{record.longitude:.8f},{record.latitude:.8f},0")


def _coordinate(point: GeoPoint) -> str:
    altitude = point.altitude if point.altitude is not None else 0
    return f"{point.longitude:.8f},{point.latitude:.8f},{altitude:g}"


def _number(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _optional_number(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _voltage_range(record: PEAPoleRecord) -> str:
    minimum = record.voltage_min_kv
    maximum = record.voltage_max_kv
    if minimum is None or maximum is None:
        return ""
    if minimum == maximum:
        return f"{minimum:g}"
    return f"{minimum:g}–{maximum:g}"
