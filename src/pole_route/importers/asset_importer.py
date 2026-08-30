"""Source-neutral CSV/XLSX import for coordinate-bearing GIS point assets."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pole_route.domain.pea_asset import PEAAsset, PEAAssetType
from pole_route.importers.pea_assets import _optional_coordinate, _text
from pole_route.importers.pea_gis import _json_safe, parse_voltage_kv
from pole_route.importers.tabular_source import detect_header, read_rows, unique_headers

FIELD_LABELS = {
    "asset_id": "Asset ID",
    "asset_type": "Asset Type",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "description": "Description",
    "voltage": "Voltage",
    "rating": "Rating / Capacity",
    "phase": "Phase",
    "subtype": "Subtype",
    "status": "Status",
    "feeder": "Feeder / Circuit",
    "source_id": "Source ID",
}
REQUIRED_FIELDS = ("asset_id", "asset_type", "latitude", "longitude")
OPTIONAL_FIELDS = (
    "description", "voltage", "rating", "phase", "subtype", "status", "feeder",
    "source_id",
)
SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xlsm"}
HEADER_ALIASES = {
    "asset_id": {"assetid", "asset id", "equipmentid", "equipment id", "id", "รหัสอุปกรณ์", "รหัสทรัพย์สิน"},
    "asset_type": {"assettype", "asset type", "equipmenttype", "equipment type", "type", "ประเภท", "ชนิดอุปกรณ์"},
    "latitude": {"latitude", "lat", "ละติจูด", "พิกัดละติจูด"},
    "longitude": {"longitude", "long", "lon", "lng", "ลองจิจูด", "พิกัดลองจิจูด"},
    "description": {"description", "name", "detail", "รายละเอียด", "ชื่อ", "ชื่ออุปกรณ์"},
    "voltage": {"voltage", "volt", "แรงดัน", "ระดับแรงดัน"},
    "rating": {"rating", "capacity", "kva", "amp", "พิกัด", "ขนาด", "กำลัง"},
    "phase": {"phase", "เฟส", "เฟสที่ติดตั้ง"},
    "subtype": {"subtype", "equipment subtype", "ประเภทย่อย", "ชนิดย่อย"},
    "status": {"status", "สถานะ", "สถานะปัจจุบัน"},
    "feeder": {"feeder", "circuit", "feeder id", "ฟีดเดอร์", "วงจร", "สายป้อน"},
    "source_id": {"sourceid", "source id", "providerid", "provider id", "รหัสต้นทาง"},
}


class AssetImportError(ValueError):
    """A generic asset file cannot be inspected or normalized."""


@dataclass(frozen=True, slots=True)
class AssetTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    header_row: int
    source_path: Path
    sheet_name: str | None = None
    confidence: str = "High"


def inspect_asset_file(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    header_row: int | None = None,
) -> AssetTable:
    source = Path(path)
    if source.suffix.casefold() not in SUPPORTED_SUFFIXES:
        raise AssetImportError("Choose a .csv, .xlsx, or .xlsm asset-data file")
    if not source.is_file():
        raise AssetImportError(f"File not found: {source}")
    try:
        rows = read_rows(source, sheet_name)
    except ValueError as error:
        raise AssetImportError(str(error)) from error
    if not rows:
        raise AssetImportError("The file is empty")
    detection = detect_header(rows, HEADER_ALIASES, REQUIRED_FIELDS)
    header_index = detection.row_index if header_row is None else header_row - 1
    if not 0 <= header_index < len(rows):
        raise AssetImportError("Header row is outside the selected worksheet")
    headers = unique_headers(rows[header_index])
    values = tuple(
        tuple(row[index] if index < len(row) else None for index in range(len(headers)))
        for row in rows[header_index + 1:]
        if any(value not in (None, "") for value in row)
    )
    confidence = detection.confidence if header_row is None else "Manual"
    return AssetTable(headers, values, header_index + 1, source, sheet_name, confidence)


def suggest_asset_mapping(headers: tuple[str, ...]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for field in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS):
        aliases = {_normalize(value) for value in HEADER_ALIASES[field]}
        matches = [header for header in headers if _normalize(header) in aliases]
        result[field] = matches[0] if len(matches) == 1 else None
    return result


def assets_from_table(
    table: AssetTable,
    mapping: dict[str, str | None],
    *,
    source_provider: str = "GENERIC_FILE",
) -> list[PEAAsset]:
    missing = [FIELD_LABELS[field] for field in REQUIRED_FIELDS if not mapping.get(field)]
    if missing:
        raise AssetImportError("Choose columns for: " + ", ".join(missing))
    indexes = {header: index for index, header in enumerate(table.headers)}
    unknown = [column for column in mapping.values() if column and column not in indexes]
    if unknown:
        raise AssetImportError("Mapped columns not found: " + ", ".join(unknown))
    provider = source_provider.strip() or "GENERIC_FILE"
    return [
        _row_to_asset(row, table.header_row + offset, table, mapping, indexes, provider)
        for offset, row in enumerate(table.rows, start=1)
    ]


def normalize_asset_type(value: object) -> PEAAssetType:
    normalized = _normalize(value)
    if normalized in {_normalize(alias) for alias in ("transformer", "tx", "หม้อแปลง")}:
        return PEAAssetType.TRANSFORMER
    if normalized in {_normalize(alias) for alias in ("switch", "sw", "สวิตช์")}:
        return PEAAssetType.SWITCH
    return PEAAssetType.OTHER


def _row_to_asset(row, row_number, table, mapping, indexes, provider):
    def value(field):
        column = mapping.get(field)
        return row[indexes[column]] if column else None

    raw = {
        header: _json_safe(row[index] if index < len(row) else None)
        for index, header in enumerate(table.headers)
    }
    asset_id = _text(value("asset_id")) or ""
    source_id = _text(value("source_id")) or asset_id
    asset_type = normalize_asset_type(value("asset_type"))
    latitude, lat_warning = _optional_coordinate(value("latitude"), "Latitude")
    longitude, lon_warning = _optional_coordinate(value("longitude"), "Longitude")
    warnings = [item for item in (lat_warning, lon_warning) if item]
    if not asset_id:
        warnings.append("Asset ID is missing; content fingerprint identity is used")
    if asset_type is PEAAssetType.OTHER:
        warnings.append(f"Unsupported asset type retained for audit: {value('asset_type')!s}")
    fingerprint_values = {
        _normalize(key): raw[key]
        for key in sorted(raw, key=_normalize)
        if raw[key] not in (None, "")
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_values, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    identity = source_id.casefold() if source_id else f"fingerprint:{fingerprint}"
    raw_voltage = _json_safe(value("voltage"))
    voltage_min, voltage_max = parse_voltage_kv(raw_voltage)
    source_file = table.source_path.name
    stable_id = f"{provider.casefold()}:{source_file.casefold()}:{identity}"
    return PEAAsset(
        stable_id=stable_id,
        source_sheet=source_file,
        source_row=row_number,
        asset_type=asset_type,
        source_asset_id=source_id,
        latitude=latitude,
        longitude=longitude,
        raw_attributes=raw,
        name=_text(value("description")),
        raw_voltage=raw_voltage,
        voltage_min_kv=voltage_min,
        voltage_max_kv=voltage_max,
        rating=_text(value("rating")),
        phase=_text(value("phase")),
        equipment_subtype=_text(value("subtype")),
        status=_text(value("status")),
        feeder_reference=_text(value("feeder")),
        qc_warnings=tuple(warnings),
        source_provider=provider,
        source_file=source_file,
    )


def _normalize(value: object) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").strip().casefold(), flags=re.UNICODE)
