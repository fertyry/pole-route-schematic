"""Inspect KML and KMZ files for road-centerline LineStrings."""

from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pole_route.domain.route import GeoPoint, Route


class RouteImportError(ValueError):
    """A route source cannot be read as valid KML/KMZ LineStrings."""


def inspect_route_file(path: str | Path) -> list[Route]:
    """Return every valid LineString candidate found in a KML or KMZ file."""
    source = Path(path)
    if source.suffix.casefold() not in {".kml", ".kmz"}:
        raise RouteImportError("Choose a .kml or .kmz route file")
    if not source.is_file():
        raise RouteImportError(f"File not found: {source}")

    xml_data = _read_kml_bytes(source)
    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as error:
        raise RouteImportError(f"Invalid KML XML: {error}") from error

    routes: list[Route] = []
    unnamed_index = 1
    for placemark in _descendants(root, "Placemark"):
        name_element = next(_children(placemark, "name"), None)
        base_name = (name_element.text or "").strip() if name_element is not None else ""
        line_strings = list(_descendants(placemark, "LineString"))
        for line_index, line_string in enumerate(line_strings, start=1):
            coordinates = next(_descendants(line_string, "coordinates"), None)
            if coordinates is None or not (coordinates.text or "").strip():
                continue
            try:
                points = _parse_coordinates(coordinates.text or "")
                route_name = base_name or f"Unnamed route {unnamed_index}"
                if len(line_strings) > 1:
                    route_name = f"{route_name} - part {line_index}"
                routes.append(Route(route_name, str(source), points))
                unnamed_index += 1
            except ValueError as error:
                raise RouteImportError(f"Invalid coordinates in {base_name or 'Placemark'}: {error}") from error

    if not routes:
        raise RouteImportError("No valid LineString was found in this KML/KMZ file")
    return routes


def _read_kml_bytes(path: Path) -> bytes:
    if path.suffix.casefold() == ".kml":
        return path.read_bytes()
    try:
        with ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.casefold().endswith(".kml")]
            if not names:
                raise RouteImportError("KMZ archive does not contain a KML document")
            selected = next((name for name in names if Path(name).name.casefold() == "doc.kml"), names[0])
            return archive.read(selected)
    except BadZipFile as error:
        raise RouteImportError("The KMZ file is not a valid ZIP archive") from error


def _parse_coordinates(text: str) -> tuple[GeoPoint, ...]:
    points: list[GeoPoint] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            raise ValueError(f"expected longitude,latitude but found {token!r}")
        longitude = float(parts[0])
        latitude = float(parts[1])
        altitude = float(parts[2]) if len(parts) >= 3 and parts[2] else None
        points.append(GeoPoint(longitude, latitude, altitude))
    if len(points) < 2:
        raise ValueError("LineString requires at least two coordinate pairs")
    return tuple(points)


def _local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ElementTree.Element, name: str):
    return (child for child in element if _local_name(child) == name)


def _descendants(element: ElementTree.Element, name: str):
    return (child for child in element.iter() if child is not element and _local_name(child) == name)

