"""Small geometry helpers for portable OSM context features."""

from __future__ import annotations

from collections.abc import Mapping

from shapely.geometry import Polygon

from pole_route.domain.context import ContextGeometryPart, OSMGeometryKind
from pole_route.domain.route import GeoPoint


def geometry_parts_from_element(
    element: Mapping[str, object],
    nodes: Mapping[int, GeoPoint],
    *,
    polygonal: bool,
) -> tuple[OSMGeometryKind, tuple[ContextGeometryPart, ...]]:
    """Return portable geometry for an Overpass way or relation.

    Invalid or incomplete polygon topology raises ``ValueError`` so the caller can
    report and skip only that candidate instead of fabricating a shape.
    """

    element_type = element.get("type")
    if element_type == "node":
        if "lon" not in element or "lat" not in element:
            raise ValueError("node has no usable coordinate")
        point = GeoPoint(float(element["lon"]), float(element["lat"]))
        return OSMGeometryKind.POINT, (ContextGeometryPart((point,)),)

    if element_type == "way":
        points = _element_points(element, nodes)
        if polygonal:
            return OSMGeometryKind.POLYGON, (_polygon_part(points, ()),)
        if len(points) < 2:
            raise ValueError("way has fewer than two usable coordinates")
        return OSMGeometryKind.LINESTRING, (ContextGeometryPart(points),)

    if element_type != "relation":
        raise ValueError("only OSM ways and relations have supported geometry")

    members = element.get("members")
    if not isinstance(members, list):
        raise ValueError("relation has no member geometry")
    if not polygonal:
        parts = tuple(
            ContextGeometryPart(points)
            for member in members
            if isinstance(member, Mapping)
            and len(points := _element_points(member, nodes)) >= 2
        )
        if not parts:
            raise ValueError("relation has no usable line member geometry")
        kind = (
            OSMGeometryKind.LINESTRING
            if len(parts) == 1
            else OSMGeometryKind.MULTILINESTRING
        )
        return kind, parts

    outer_segments: list[tuple[GeoPoint, ...]] = []
    inner_segments: list[tuple[GeoPoint, ...]] = []
    for member in members:
        if not isinstance(member, Mapping):
            continue
        points = _element_points(member, nodes)
        role = str(member.get("role", ""))
        if role == "outer":
            outer_segments.append(points)
        elif role == "inner":
            inner_segments.append(points)
    outer_rings = _assemble_rings(outer_segments)
    inner_rings = _assemble_rings(inner_segments) if inner_segments else []
    if not outer_rings:
        raise ValueError("multipolygon relation has no complete outer ring")

    outer_polygons = [Polygon(_xy(ring)) for ring in outer_rings]
    holes_by_outer: list[list[tuple[GeoPoint, ...]]] = [
        [] for _ring in outer_rings
    ]
    for inner_ring in inner_rings:
        inner_polygon = Polygon(_xy(inner_ring))
        if not inner_polygon.is_valid or inner_polygon.is_empty:
            raise ValueError("multipolygon relation has an invalid inner ring")
        owner = next(
            (
                index
                for index, outer in enumerate(outer_polygons)
                if outer.covers(inner_polygon.representative_point())
            ),
            None,
        )
        if owner is None:
            raise ValueError("multipolygon inner ring is not inside an outer ring")
        holes_by_outer[owner].append(inner_ring)

    parts = tuple(
        _polygon_part(outer, tuple(holes_by_outer[index]))
        for index, outer in enumerate(outer_rings)
    )
    kind = OSMGeometryKind.POLYGON if len(parts) == 1 else OSMGeometryKind.MULTIPOLYGON
    return kind, parts


def _element_points(
    element: Mapping[str, object], nodes: Mapping[int, GeoPoint]
) -> tuple[GeoPoint, ...]:
    geometry = element.get("geometry")
    if isinstance(geometry, list):
        points: list[GeoPoint] = []
        for point in geometry:
            if isinstance(point, Mapping) and "lon" in point and "lat" in point:
                points.append(GeoPoint(float(point["lon"]), float(point["lat"])))
        return tuple(points)
    node_ids = element.get("nodes")
    if not isinstance(node_ids, list):
        return ()
    return tuple(nodes[node_id] for node_id in node_ids if node_id in nodes)


def _closed_ring(points: tuple[GeoPoint, ...]) -> tuple[GeoPoint, ...]:
    if len(points) < 4:
        raise ValueError("polygon ring is incomplete")
    if points[0] != points[-1]:
        raise ValueError("polygon ring is not closed")
    return points


def _assemble_rings(
    segments: list[tuple[GeoPoint, ...]],
) -> list[tuple[GeoPoint, ...]]:
    """Join relation members only when their exact endpoints form unambiguous rings."""
    unused = [segment for segment in segments if len(segment) >= 2]
    rings: list[tuple[GeoPoint, ...]] = []
    while unused:
        chain = list(unused.pop(0))
        while chain[0] != chain[-1]:
            matches: list[tuple[int, tuple[GeoPoint, ...]]] = []
            for index, segment in enumerate(unused):
                if segment[0] == chain[-1]:
                    matches.append((index, segment))
                elif segment[-1] == chain[-1]:
                    matches.append((index, tuple(reversed(segment))))
            if len(matches) != 1:
                raise ValueError(
                    "multipolygon ring members do not form one unambiguous closed ring"
                )
            index, oriented = matches[0]
            unused.pop(index)
            chain.extend(oriented[1:])
        rings.append(_closed_ring(tuple(chain)))
    return rings


def _polygon_part(
    exterior: tuple[GeoPoint, ...], holes: tuple[tuple[GeoPoint, ...], ...]
) -> ContextGeometryPart:
    exterior = _closed_ring(exterior)
    holes = tuple(_closed_ring(hole) for hole in holes)
    polygon = Polygon(_xy(exterior), [_xy(hole) for hole in holes])
    if polygon.is_empty or polygon.area == 0 or not polygon.is_valid:
        raise ValueError("polygon geometry is empty or invalid")
    return ContextGeometryPart(exterior, holes)


def _xy(points: tuple[GeoPoint, ...]) -> list[tuple[float, float]]:
    return [(point.longitude, point.latitude) for point in points]
