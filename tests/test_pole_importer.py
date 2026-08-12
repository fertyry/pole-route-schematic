import csv

import pytest
from openpyxl import Workbook

from pole_route.domain.pole import PoleSide
from pole_route.importers.pole_importer import (
    PoleImportError,
    import_poles,
    inspect_pole_file,
    poles_from_table,
    suggest_column_mapping,
)

HEADERS = ["Pole No.", "Latitude", "Longitude", "Detail", "Side"]


def test_imports_csv_poles(tmp_path) -> None:
    source = tmp_path / "poles.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS)
        writer.writerow(["P-001", 13.7563, 100.5018, "Transformer", "Left"])
        writer.writerow(["P-002", 13.7564, 100.5019, "", "ขวา"])

    poles = import_poles(source)

    assert [pole.number for pole in poles] == ["P-001", "P-002"]
    assert poles[0].side is PoleSide.LEFT
    assert poles[1].side is PoleSide.RIGHT


def test_imports_active_excel_worksheet(tmp_path) -> None:
    source = tmp_path / "poles.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(HEADERS)
    worksheet.append(["P-101", 18.7883, 98.9853, "Switch", "R"])
    workbook.save(source)

    poles = import_poles(source)

    assert len(poles) == 1
    assert poles[0].number == "P-101"
    assert poles[0].side is PoleSide.RIGHT


def test_rejects_missing_columns(tmp_path) -> None:
    source = tmp_path / "poles.csv"
    source.write_text("Pole No.,Latitude\nP-001,13.75\n", encoding="utf-8")

    with pytest.raises(PoleImportError, match="Choose columns for"):
        import_poles(source)


def test_detects_aliases_and_header_below_title(tmp_path) -> None:
    source = tmp_path / "field-export.csv"
    source.write_text(
        "Project,North feeder\n"
        "Pole ID,Lat,Lng,Description,Road Side\n"
        "A-01,13.75,100.50,Transformer,L\n",
        encoding="utf-8",
    )

    table = inspect_pole_file(source)
    mapping = suggest_column_mapping(table.headers)
    poles = poles_from_table(table, mapping)

    assert table.header_row == 2
    assert mapping["number"] == "Pole ID"
    assert mapping["longitude"] == "Lng"
    assert poles[0].number == "A-01"


def test_imports_with_explicit_mapping_and_optional_fields_omitted(tmp_path) -> None:
    source = tmp_path / "custom.csv"
    source.write_text("Asset,Y Coordinate,X Coordinate\nP-9,13.7,100.4\n", encoding="utf-8")
    table = inspect_pole_file(source)

    poles = poles_from_table(
        table,
        {
            "number": "Asset",
            "latitude": "Y Coordinate",
            "longitude": "X Coordinate",
            "detail": None,
            "side": None,
        },
    )

    assert poles[0].number == "P-9"
    assert poles[0].detail == ""
    assert poles[0].side is PoleSide.UNKNOWN


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected_latitude", "expected_longitude"),
    [
        ("13.797493°", "100.7002°", 13.797493, 100.7002),
        ("13.797493 N", "100.7002 E", 13.797493, 100.7002),
        ("13° 47' 50.9748\" N", "100° 42' 0.72\" E", 13.797493, 100.7002),
        ("๑๓.๗๙๗๔๙๓°", "๑๐๐.๗๐๐๒°", 13.797493, 100.7002),
    ],
)
def test_imports_coordinate_text_formats(
    tmp_path,
    latitude,
    longitude,
    expected_latitude,
    expected_longitude,
) -> None:
    source = tmp_path / "coordinate-text.csv"
    source.write_text(
        ",".join(HEADERS) + f"\nP-1,{latitude},{longitude},,L\n",
        encoding="utf-8",
    )

    pole = import_poles(source)[0]

    assert pole.latitude == pytest.approx(expected_latitude)
    assert pole.longitude == pytest.approx(expected_longitude)


@pytest.mark.parametrize(
    ("latitude", "longitude", "message"),
    [(91, 100, "Latitude"), (13, 181, "Longitude")],
)
def test_rejects_out_of_range_coordinates(tmp_path, latitude, longitude, message) -> None:
    source = tmp_path / "poles.csv"
    source.write_text(
        ",".join(HEADERS) + f"\nP-001,{latitude},{longitude},,Left\n",
        encoding="utf-8",
    )

    with pytest.raises(PoleImportError, match=message):
        import_poles(source)
