import csv

import pytest
from openpyxl import Workbook

from pole_route.domain.pole import PoleSide
from pole_route.importers.pole_importer import PoleImportError, import_poles

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

    with pytest.raises(PoleImportError, match="Missing required columns"):
        import_poles(source)


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
