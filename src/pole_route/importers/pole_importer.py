"""Import and validate pole rows from CSV and Excel workbooks."""

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path

from openpyxl import load_workbook

from pole_route.domain.pole import Pole, PoleSide

REQUIRED_COLUMNS = ("Pole No.", "Latitude", "Longitude", "Detail", "Side")
SUPPORTED_SUFFIXES = {".csv", ".xlsx"}


class PoleImportError(ValueError):
    """A source file cannot be converted into valid pole records."""


def import_poles(path: str | Path) -> list[Pole]:
    """Load pole records from a UTF-8 CSV file or the active XLSX worksheet."""
    source = Path(path)
    suffix = source.suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise PoleImportError("Choose a .csv or .xlsx pole-data file")
    if not source.is_file():
        raise PoleImportError(f"File not found: {source}")

    rows = _read_csv(source) if suffix == ".csv" else _read_xlsx(source)
    poles = [_row_to_pole(row, row_number) for row_number, row in rows]
    if not poles:
        raise PoleImportError("The file contains headers but no pole rows")
    return poles


def _read_csv(path: Path) -> list[tuple[int, Mapping[str, object]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            _validate_headers(fieldnames)
            return [(row_number, row) for row_number, row in enumerate(reader, start=2)]
    except UnicodeDecodeError as error:
        raise PoleImportError("CSV must be saved with UTF-8 encoding") from error


def _read_xlsx(path: Path) -> list[tuple[int, Mapping[str, object]]]:
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as error:
        raise PoleImportError(f"Could not open Excel file: {error}") from error

    try:
        worksheet = workbook.active
        values = worksheet.iter_rows(values_only=True)
        headers = [str(value).strip() if value is not None else "" for value in next(values, ())]
        _validate_headers(headers)
        rows = []
        for row_number, values_row in enumerate(values, start=2):
            rows.append((row_number, dict(zip(headers, values_row, strict=False))))
        return rows
    finally:
        workbook.close()


def _validate_headers(headers: Iterable[str]) -> None:
    available = {str(header).strip() for header in headers}
    missing = [column for column in REQUIRED_COLUMNS if column not in available]
    if missing:
        raise PoleImportError("Missing required columns: " + ", ".join(missing))


def _row_to_pole(row: Mapping[str, object], row_number: int) -> Pole:
    try:
        return Pole(
            number=str(row.get("Pole No.") or "").strip(),
            latitude=float(row.get("Latitude")),
            longitude=float(row.get("Longitude")),
            detail=str(row.get("Detail") or "").strip(),
            side=PoleSide.from_text(row.get("Side")),
        )
    except (TypeError, ValueError) as error:
        raise PoleImportError(f"Row {row_number}: {error}") from error

