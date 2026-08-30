"""Inspect, map, import, and validate pole data from CSV and Excel."""

import re
from dataclasses import dataclass
from pathlib import Path

from pole_route.domain.pole import Pole, PoleSide
from pole_route.importers.tabular_source import detect_header, read_rows, unique_headers

FIELD_LABELS = {
    "number": "Pole No.",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "detail": "Detail",
    "installed_quantity": "Installed quantity",
    "side": "Side",
}
REQUIRED_FIELDS = ("number", "latitude", "longitude")
OPTIONAL_FIELDS = ("detail", "installed_quantity", "side")
SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xlsm"}
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
COORDINATE_PATTERN = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:[°º]|deg)?\s*"
    r"(?:(\d+(?:\.\d+)?)\s*['′])?\s*"
    r"(?:(\d+(?:\.\d+)?)\s*[\"″])?\s*([NSEW])?\s*$",
    re.IGNORECASE,
)

HEADER_ALIASES = {
    "number": {
        "poleno",
        "polenumber",
        "poleid",
        "pole",
        "no",
        "number",
        "หมายเลขเสา",
        "เลขเสา",
        "ลำดับ",
    },
    "latitude": {"latitude", "lat", "ละติจูด", "พิกัดละติจูด"},
    "longitude": {"longitude", "long", "lon", "lng", "ลองจิจูด", "พิกัดลองจิจูด"},
    "detail": {"detail", "details", "description", "remark", "remarks", "รายละเอียด"},
    "installed_quantity": {
        "installedquantity",
        "installationquantity",
        "quantity",
        "qty",
        "\u0e08\u0e33\u0e19\u0e27\u0e19\u0e17\u0e35\u0e48\u0e15\u0e34\u0e14\u0e15\u0e31\u0e49\u0e07",
        "\u0e08\u0e33\u0e19\u0e27\u0e19\u0e15\u0e34\u0e14\u0e15\u0e31\u0e49\u0e07",
    },
    "side": {"side", "roadside", "ฝั่ง", "ด้าน"},
}


class PoleImportError(ValueError):
    """A source file cannot be converted into valid pole records."""


@dataclass(frozen=True, slots=True)
class PoleTable:
    """Raw tabular content selected from a source file."""

    headers: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    header_row: int
    sheet_name: str | None = None
    confidence: str = "High"


def inspect_pole_file(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    header_row: int | None = None,
) -> PoleTable:
    """Read a supported source and detect the most likely header row."""
    source = Path(path)
    suffix = source.suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise PoleImportError("Choose a .csv, .xlsx, or .xlsm pole-data file")
    if not source.is_file():
        raise PoleImportError(f"File not found: {source}")

    try:
        raw_rows = read_rows(source, sheet_name)
    except ValueError as error:
        raise PoleImportError(str(error)) from error
    if not raw_rows:
        raise PoleImportError("The file is empty")
    detection = detect_header(raw_rows, HEADER_ALIASES, REQUIRED_FIELDS)
    header_index = detection.row_index if header_row is None else header_row - 1
    if not 0 <= header_index < len(raw_rows):
        raise PoleImportError("Header row is outside the selected worksheet")
    headers = unique_headers(raw_rows[header_index])
    data_rows = tuple(
        tuple(row[index] if index < len(row) else None for index in range(len(headers)))
        for row in raw_rows[header_index + 1 :]
        if any(value not in (None, "") for value in row)
    )
    confidence = detection.confidence if header_row is None else "Manual"
    return PoleTable(headers, data_rows, header_index + 1, sheet_name, confidence)


def suggest_column_mapping(headers: tuple[str, ...]) -> dict[str, str | None]:
    """Match common English and Thai header variants to application fields."""
    mapping: dict[str, str | None] = {}
    for field in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS):
        normalized_aliases = {_normalize_header(alias) for alias in HEADER_ALIASES[field]}
        matches = [header for header in headers if _normalize_header(header) in normalized_aliases]
        mapping[field] = matches[0] if len(matches) == 1 else None
    return mapping


def import_poles(
    path: str | Path,
    mapping: dict[str, str | None] | None = None,
) -> list[Pole]:
    """Import poles using automatic aliases or an explicit column mapping."""
    table = inspect_pole_file(path)
    selected_mapping = mapping or suggest_column_mapping(table.headers)
    return poles_from_table(table, selected_mapping)


def poles_from_table(table: PoleTable, mapping: dict[str, str | None]) -> list[Pole]:
    """Convert inspected rows using a user-confirmed column mapping."""
    missing = [FIELD_LABELS[field] for field in REQUIRED_FIELDS if not mapping.get(field)]
    if missing:
        raise PoleImportError("Choose columns for: " + ", ".join(missing))

    header_indexes = {header: index for index, header in enumerate(table.headers)}
    unknown = [column for column in mapping.values() if column and column not in header_indexes]
    if unknown:
        raise PoleImportError("Mapped columns not found: " + ", ".join(unknown))

    poles = [
        _row_to_pole(row, table.header_row + row_offset, mapping, header_indexes)
        for row_offset, row in enumerate(table.rows, start=1)
    ]
    if not poles:
        raise PoleImportError("The file contains headers but no pole rows")
    return poles


def _normalize_header(value: object) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").strip().casefold(), flags=re.UNICODE)


def _row_to_pole(
    row: tuple[object, ...],
    row_number: int,
    mapping: dict[str, str | None],
    header_indexes: dict[str, int],
) -> Pole:
    def value(field: str) -> object:
        column = mapping.get(field)
        return row[header_indexes[column]] if column else None

    try:
        return Pole(
            number=str(value("number") or "").strip(),
            latitude=_parse_coordinate(value("latitude"), "Latitude"),
            longitude=_parse_coordinate(value("longitude"), "Longitude"),
            detail=str(value("detail") or "").strip(),
            side=PoleSide.from_text(value("side")),
            installed_quantity=_parse_installed_quantity(value("installed_quantity")),
        )
    except (TypeError, ValueError) as error:
        raise PoleImportError(f"Row {row_number}: {error}") from error


def _parse_coordinate(value: object, label: str) -> float:
    """Parse numeric or text decimal-degree/DMS coordinates."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} is required")
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().translate(THAI_DIGITS)
    match = COORDINATE_PATTERN.fullmatch(text)
    if not match:
        raise ValueError(
            f"{label} must be decimal degrees, for example 13.797493° or 13.797493 N"
        )
    degrees_text, minutes_text, seconds_text, direction_text = match.groups()
    degrees = float(degrees_text)
    minutes = float(minutes_text or 0)
    seconds = float(seconds_text or 0)
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"{label} minutes and seconds must be less than 60")

    coordinate = abs(degrees) + minutes / 60 + seconds / 3600
    if degrees < 0:
        coordinate = -coordinate
    direction = (direction_text or "").upper()
    if direction in {"S", "W"}:
        coordinate = -abs(coordinate)
    elif direction in {"N", "E"}:
        coordinate = abs(coordinate)
    return coordinate


def _parse_installed_quantity(value: object) -> int:
    """Parse an optional positive whole-number installation quantity."""
    if value in (None, ""):
        return 1
    if isinstance(value, bool):
        raise ValueError("Installed quantity must be a positive whole number")
    text = str(value).strip().translate(THAI_DIGITS)
    try:
        numeric = float(text)
    except ValueError as error:
        raise ValueError("Installed quantity must be a positive whole number") from error
    quantity = int(numeric)
    if numeric != quantity or quantity < 1:
        raise ValueError("Installed quantity must be a positive whole number")
    return quantity
