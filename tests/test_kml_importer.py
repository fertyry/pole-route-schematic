from zipfile import ZipFile

import pytest

from pole_route.importers.kml_importer import RouteImportError, inspect_route_file

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Main Road</name>
      <LineString>
        <coordinates>
          100.5000,13.7000,0 100.5010,13.7010,0 100.5020,13.7015,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""


def test_imports_kml_linestring(tmp_path) -> None:
    source = tmp_path / "route.kml"
    source.write_text(KML, encoding="utf-8")

    routes = inspect_route_file(source)

    assert len(routes) == 1
    assert routes[0].name == "Main Road"
    assert len(routes[0].points) == 3
    assert routes[0].points[0].longitude == pytest.approx(100.5)


def test_imports_doc_kml_from_kmz(tmp_path) -> None:
    source = tmp_path / "route.kmz"
    with ZipFile(source, "w") as archive:
        archive.writestr("files/other.kml", "<kml />")
        archive.writestr("doc.kml", KML)

    routes = inspect_route_file(source)

    assert routes[0].name == "Main Road"


def test_rejects_kml_without_linestring(tmp_path) -> None:
    source = tmp_path / "empty.kml"
    source.write_text("<kml><Placemark><Point /></Placemark></kml>", encoding="utf-8")

    with pytest.raises(RouteImportError, match="No valid LineString"):
        inspect_route_file(source)


def test_rejects_invalid_coordinate_range(tmp_path) -> None:
    source = tmp_path / "invalid.kml"
    source.write_text(
        "<kml><Placemark><LineString><coordinates>"
        "181,13 100,14"
        "</coordinates></LineString></Placemark></kml>",
        encoding="utf-8",
    )

    with pytest.raises(RouteImportError, match="Longitude"):
        inspect_route_file(source)
