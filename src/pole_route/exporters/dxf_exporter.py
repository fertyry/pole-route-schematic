"""Export metric road geometry as an editable AutoCAD DXF drawing."""

from __future__ import annotations

from math import atan2, ceil, cos, degrees, hypot, isfinite, sin
from pathlib import Path

import ezdxf
from ezdxf import units
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, Polygon
from shapely.ops import nearest_points, substring, unary_union

from pole_route.domain.context import ContextFeature, OSMFeatureCategory, OSMGeometryKind
from pole_route.domain.route import GeoPoint, RouteType
from pole_route.exporters.excel_exporter import ExcelExportSettings
from pole_route.geometry.road_geometry import RoadNetworkGeometry
from pole_route.importers.edited_dxf_importer import inspect_edited_dxf


class DxfExportError(RuntimeError):
    """The metric geometry cannot be written as DXF."""


LAYERS = (
    ("MAIN_CENTERLINE", 8, "DASHED"),
    ("MAIN_ROAD_EDGE", 7, "CONTINUOUS"),
    ("CROSS_CENTERLINE", 1, "DASHED"),
    ("CROSS_ROAD_EDGE", 1, "CONTINUOUS"),
    ("T_CENTERLINE", 30, "DASHED"),
    ("T_ROAD_EDGE", 30, "CONTINUOUS"),
    ("ROAD_NETWORK_EDGE", 7, "CONTINUOUS"),
    ("SOI_CENTERLINE", 8, "DASHED"),
    ("SOI_EDGE", 9, "CONTINUOUS"),
    ("POLE_OFFSET", 3, "DASHED"),
    ("POLES", 1, "CONTINUOUS"),
    ("POLE_LABELS", 7, "CONTINUOUS"),
    ("ROAD_LABELS", 7, "CONTINUOUS"),
    ("SHEET_FRAME", 7, "CONTINUOUS"),
    ("SHEET_TABLE", 7, "CONTINUOUS"),
    ("SHEET_VIEWPORT", 7, "CONTINUOUS"),
    ("SHEET_BREAK", 6, "DASHED"),
    ("PRS_OSM_BRIDGE", 30, "CONTINUOUS"),
    ("PRS_OSM_BRIDGE_NAME", 30, "CONTINUOUS"),
    ("PRS_OSM_FOOTBRIDGE", 2, "CONTINUOUS"),
    ("PRS_OSM_RIVER", 5, "CONTINUOUS"),
    ("PRS_OSM_RIVER_NAME", 5, "CONTINUOUS"),
    ("PRS_OSM_CANAL", 4, "CONTINUOUS"),
    ("PRS_OSM_CANAL_NAME", 4, "CONTINUOUS"),
    ("PRS_OSM_BUILDING", 8, "CONTINUOUS"),
    ("PRS_OSM_BUILDING_NAME", 8, "CONTINUOUS"),
    ("PRS_BUILDING", 8, "CONTINUOUS"),
    ("PRS_BUILDING_NAME", 8, "CONTINUOUS"),
    ("PRS_OSM_FUEL", 1, "CONTINUOUS"),
    ("PRS_OSM_FUEL_NAME", 1, "CONTINUOUS"),
    ("PRS_OSM_SHOP", 6, "CONTINUOUS"),
    ("PRS_OSM_SHOP_NAME", 6, "CONTINUOUS"),
    ("PRS_OSM_POI", 3, "CONTINUOUS"),
    ("PRS_OSM_POI_NAME", 3, "CONTINUOUS"),
)

OSM_DXF_LAYERS = {
    OSMFeatureCategory.ROAD_BRIDGE: ("PRS_OSM_BRIDGE", "PRS_OSM_BRIDGE_NAME"),
    OSMFeatureCategory.FOOTBRIDGE: ("PRS_OSM_FOOTBRIDGE", "PRS_OSM_BRIDGE_NAME"),
    OSMFeatureCategory.RIVER: ("PRS_OSM_RIVER", "PRS_OSM_RIVER_NAME"),
    OSMFeatureCategory.CANAL: ("PRS_OSM_CANAL", "PRS_OSM_CANAL_NAME"),
    OSMFeatureCategory.BUILDING: ("PRS_BUILDING", "PRS_BUILDING_NAME"),
    OSMFeatureCategory.FUEL: ("PRS_OSM_FUEL", "PRS_OSM_FUEL_NAME"),
    OSMFeatureCategory.SHOP: ("PRS_OSM_SHOP", "PRS_OSM_SHOP_NAME"),
    OSMFeatureCategory.POI: ("PRS_OSM_POI", "PRS_OSM_POI_NAME"),
}

DXF_TARGET_SPAN_METRES = 350.0
PRS_CONTEXT_APPID = "POLEROUTE"


def export_edited_dxf_with_sheet_layouts(
    source_path: str | Path,
    destination_path: str | Path,
    settings: ExcelExportSettings | None = None,
) -> int:
    """Create plot-ready A4 layouts from a manually edited CAD Master."""
    settings = settings or ExcelExportSettings()
    inspection = inspect_edited_dxf(source_path)
    try:
        document = ezdxf.readfile(source_path)
    except (OSError, ezdxf.DXFError) as error:
        raise DxfExportError(f"Edited DXF could not be opened: {error}") from error

    for name, color, line_type in LAYERS:
        if name not in document.layers:
            document.layers.add(name, color=color, linetype=line_type)
    for layer_name in ("SHEET_VIEWPORT", "SHEET_BREAK", "POLE_OFFSET", "POLE_LABELS"):
        document.layers.get(layer_name).dxf.plot = 0
    old_layouts = [name for name in document.layout_names() if name != "Model"]
    temporary_layout = "_PRS_OLD_LAYOUT"
    if old_layouts:
        document.layouts.rename(old_layouts[0], temporary_layout)
        for name in old_layouts[1:]:
            document.layouts.delete(name)

    poles = tuple(sorted(inspection.pole_blocks, key=lambda item: item.station_metres))
    if not poles:
        raise DxfExportError("The edited DXF contains no PoleRoute pole blocks.")
    breaks = tuple(sorted(inspection.sheet_breaks, key=lambda item: item.station_metres))
    station_boundaries = [poles[0].station_metres]
    station_boundaries.extend(item.station_metres for item in breaks)
    station_boundaries.append(poles[-1].station_metres)
    page_pole_groups = [
        [
            pole for pole in poles
            if start_station - 0.01 <= pole.station_metres <= end_station + 0.01
        ]
        for start_station, end_station in zip(station_boundaries, station_boundaries[1:])
    ]
    # A sheet-break block is only a stable station marker.  Its XY may be left
    # behind when a CAD user moves the road or poles, so never use that XY to
    # orient a sheet.  The edited pole positions are the authoritative axis.
    page_axes = [_page_axis_from_edited_poles(group) for group in page_pole_groups]
    spans = [axis[2] for axis in page_axes]
    scale = min(0.68, 250.0 / max(max(spans, default=1.0), 1.0))
    main_road_name = _prepare_main_road_label_for_sheets(document, poles)

    count = 0
    total = len(page_pole_groups)
    for index, (page_poles, axis) in enumerate(zip(page_pole_groups, page_axes), start=1):
        layout = document.layouts.new(f"Sheet {index:02d}")
        if index == 1 and temporary_layout in document.layout_names():
            document.layouts.delete(temporary_layout)
        layout.page_setup(size=(297, 210), margins=(5, 5, 5, 5), units="mm", device="DWG to PDF.pc3")
        count += _draw_sheet_frame(layout, settings, index, total)
        center, angle, _span = axis
        dcs_center = (
            center[0] * cos(angle) + center[1] * sin(angle),
            -center[0] * sin(angle) + center[1] * cos(angle),
        )
        paper_center = (148.5, 126.0)
        layout.add_viewport(
            center=paper_center,
            size=(267.0, 104.0),
            view_center_point=dcs_center,
            view_height=104.0 / scale,
            status=2,
            dxfattribs={"layer": "SHEET_VIEWPORT", "view_twist_angle": -degrees(angle)},
        )
        count += 1
        count += _draw_edited_pole_labels(layout, page_poles, center, angle, scale, paper_center)
        if main_road_name:
            count += _draw_sheet_main_road_name(layout, main_road_name)
        count += _draw_edited_pole_table(layout, page_poles)
        count += _draw_north_arrow(layout, angle)

    try:
        document.saveas(Path(destination_path))
    except (OSError, ezdxf.DXFError) as error:
        raise DxfExportError(f"Sheeted DXF could not be saved: {error}") from error
    return count


def _page_axis_from_edited_poles(poles):
    """Return viewport center, angle, and span from edited physical poles."""
    if not poles:
        return (0.0, 0.0), 0.0, 1.0
    start, end = poles[0], poles[-1]
    span = hypot(end.x - start.x, end.y - start.y)
    if span > 0.01:
        angle = atan2(end.y - start.y, end.x - start.x)
    else:
        angle = start.rotation * 3.141592653589793 / 180.0
        span = 1.0
    return ((start.x + end.x) / 2.0, (start.y + end.y) / 2.0), angle, span


def _prepare_main_road_label_for_sheets(document, poles) -> str:
    """Find the route-parallel road name and hide only its model-space text."""
    labels = list(document.modelspace().query('TEXT[layer=="ROAD_LABELS"]'))
    if not labels or len(poles) < 2:
        return ""
    route_angle = degrees(atan2(poles[-1].y - poles[0].y, poles[-1].x - poles[0].x))

    def score(entity):
        angle_delta = abs(((float(entity.dxf.rotation) - route_angle + 90.0) % 180.0) - 90.0)
        point = Point(float(entity.dxf.insert.x), float(entity.dxf.insert.y))
        pole_axis = LineString([(pole.x, pole.y) for pole in poles])
        return angle_delta * 10.0 + point.distance(pole_axis)

    label = min(labels, key=score)
    text = str(label.dxf.text).strip()
    # Keep soi/cross-road labels in the viewport, but suppress this duplicate;
    # a clean horizontal copy is placed in Paper Space on every sheet.
    label.dxf.layer = "POLE_LABELS"
    return text


def _draw_sheet_main_road_name(layout, text: str) -> int:
    """Place the main-road name horizontally below the road viewport center."""
    entity = layout.add_text(
        text,
        dxfattribs={"layer": "SHEET_TABLE", "height": 2.2, "rotation": 0.0},
    )
    entity.set_placement((148.5, 92.0))
    return 1


def _draw_edited_pole_labels(layout, poles, center, angle, scale, paper_center) -> int:
    """Draw route-perpendicular Paper Space labels from stable pole metadata."""
    count = 0
    cos_a, sin_a = cos(angle), sin(angle)
    for pole in poles:
        dx, dy = pole.x - center[0], pole.y - center[1]
        paper_x = paper_center[0] + (dx * cos_a + dy * sin_a) * scale
        paper_y = paper_center[1] + (-dx * sin_a + dy * cos_a) * scale
        details = list(pole.details) + [""] * max(0, len(pole.pole_ids) - len(pole.details))
        for slot, (pole_id, detail) in enumerate(zip(pole.pole_ids, details)):
            _add_dxf_text(layout, "SHEET_TABLE", paper_x + slot * 3.0, paper_y + 2.5,
                          f"{pole_id}  {detail}".strip(), 1.8, rotation=90.0)
            count += 1
    return count


def _draw_edited_pole_table(layout, poles) -> int:
    """Build the Paper Space schedule from edited pole-block attributes."""
    rows = []
    for pole in poles:
        details = list(pole.details) + [""] * max(0, len(pole.pole_ids) - len(pole.details))
        quantities = list(pole.quantities) + [1] * max(0, len(pole.pole_ids) - len(pole.quantities))
        rows.extend(zip(pole.pole_ids, details, quantities))
    row_count = max(1, ceil(len(rows) / 2))
    count = 0
    for column, left in enumerate((14.0, 151.0)):
        right, top = left + 132.0, 68.0
        row_height = min(5.0, 48.0 / (row_count + 1))
        layout.add_lwpolyline(
            ((left, top), (right, top), (right, top - row_height * (row_count + 1)), (left, top - row_height * (row_count + 1))),
            close=True, dxfattribs={"layer": "SHEET_TABLE"},
        )
        _add_dxf_text(layout, "SHEET_TABLE", left + 2, top - row_height + 1,
                      "Pole No. / Detail                 Installed Qty.", 2.0)
        count += 2
        start = column * row_count
        for row_index, (pole_id, detail, quantity) in enumerate(rows[start:start + row_count], start=1):
            y = top - row_height * row_index
            layout.add_line((left, y), (right, y), dxfattribs={"layer": "SHEET_TABLE"})
            _add_dxf_text(layout, "SHEET_TABLE", left + 2, y - row_height + 1,
                          f"{pole_id}  {detail}                 {quantity}".strip(), 1.8)
            count += 2
    return count


def _add_solid_square(block, center_x: float) -> None:
    """Add a filled one-metre pole marker to a reusable block definition."""
    block.add_solid(
        (
            (center_x - 0.5, -0.5),
            (center_x + 0.5, -0.5),
            (center_x - 0.5, 0.5),
            (center_x + 0.5, 0.5),
        ),
        dxfattribs={"layer": "POLES"},
    )


def _add_pole_metadata_attdefs(block) -> None:
    """Define invisible identity fields carried by every physical pole insert."""
    for tag in (
        "POLE_IDS",
        "DETAILS",
        "QUANTITIES",
        "PHYSICAL_GROUP",
        "STATION_M",
        "KIND",
    ):
        block.add_attdef(
            tag,
            insert=(0.0, 0.0),
            height=0.01,
            dxfattribs={"layer": "POLES", "flags": 1},
        )


def _pole_metadata(members, station: float, block_name: str) -> dict[str, str]:
    """Return stable source data used to rebuild labels after CAD editing."""
    poles = [member.pole for member in members]
    pole_ids = [pole.number for pole in poles]
    return {
        "POLE_IDS": "|".join(pole_ids),
        "DETAILS": "|".join(pole.detail for pole in poles),
        "QUANTITIES": "|".join(str(pole.installed_quantity) for pole in poles),
        "PHYSICAL_GROUP": "|".join(pole_ids),
        "STATION_M": f"{station:.3f}",
        "KIND": "TRANSFORMER_RACK" if block_name == "PRS_TRANSFORMER_RACK" else "POLE",
    }


def export_geometry_to_dxf(
    geometry: RoadNetworkGeometry,
    path: str | Path,
    settings: ExcelExportSettings | None = None,
    *,
    include_sheet_layouts: bool = True,
    same_pole_groups: tuple[frozenset[str], ...] = (),
    transformer_rack_groups: tuple[frozenset[str], ...] = (),
    osm_features: tuple[ContextFeature, ...] = (),
) -> int:
    """Write real metric geometry, Unicode labels, CAD layers, and pole blocks."""
    if not geometry.roads:
        raise DxfExportError("There is no road geometry to export.")

    document = ezdxf.new("R2010", setup=True)
    document.units = units.M
    if PRS_CONTEXT_APPID not in document.appids:
        document.appids.add(PRS_CONTEXT_APPID)
    if "THAI" not in document.styles:
        document.styles.add("THAI", font="tahoma.ttf")
    for name, color, line_type in LAYERS:
        if name not in document.layers:
            document.layers.add(name, color=color, linetype=line_type)
    # The viewport boundary is useful while editing a layout, but must not be
    # printed as part of the drawing frame.
    document.layers.get("SHEET_VIEWPORT").dxf.plot = 0
    document.layers.get("SHEET_BREAK").dxf.plot = 0
    # This is a construction/projection guide. Keep it editable in Model Space
    # but do not include it in plotted sheets.
    document.layers.get("POLE_OFFSET").dxf.plot = 0

    pole_block = document.blocks.new("PRS_POLE")
    _add_solid_square(pole_block, 0.0)
    _add_pole_metadata_attdefs(pole_block)
    rack_block = document.blocks.new("PRS_TRANSFORMER_RACK")
    for x in (-1.5, 1.5):
        _add_solid_square(rack_block, x)
    rack_block.add_line((-1.0, 0.0), (1.0, 0.0), dxfattribs={"layer": "POLES"})
    _add_pole_metadata_attdefs(rack_block)
    _define_sheet_break_block(document)
    modelspace = document.modelspace()
    export_roads = _deduplicate_context_roads(geometry)
    object_count = 0
    structural_roads = tuple(
        road
        for road in export_roads
        if road.route_type
        in {RouteType.MAIN_ROUTE, RouteType.CROSS_ROAD, RouteType.T_JUNCTION}
    )
    surface_roads, matched_osm_roads = _structural_surface_roads(
        geometry.roads, structural_roads
    )
    integrated_road_ids = {id(road) for road in (*structural_roads, *matched_osm_roads)}
    structural_surface = _joined_road_surface(surface_roads)
    if structural_surface is not None:
        network_boundary = _remove_road_end_caps(
            structural_surface.boundary, surface_roads
        )
        for part in _line_parts(network_boundary):
            _add_dxf_line(modelspace, "ROAD_NETWORK_EDGE", part)
            object_count += 1

    labelled_roads: set[str] = set()
    for road in export_roads:
        center_layer, edge_layer = _road_layers(road)
        visible_centerline = (
            road.centerline
            if structural_surface is None or id(road) in integrated_road_ids
            else road.centerline.difference(structural_surface.buffer(0.02))
        )
        for part in _line_parts(visible_centerline):
            _add_dxf_line(modelspace, center_layer, part)
            object_count += 1
        if id(road) in integrated_road_ids:
            edges = ()
        else:
            edges = (road.left_edge, road.right_edge)
        for edge in edges:
            visible = (
                edge
                if structural_surface is None
                else edge.difference(structural_surface.buffer(0.02))
            )
            for part in _line_parts(visible):
                _add_dxf_line(modelspace, edge_layer, part)
                object_count += 1
        if road.pole_line_enabled:
            _add_dxf_line(modelspace, "POLE_OFFSET", road.left_pole_line)
            _add_dxf_line(modelspace, "POLE_OFFSET", road.right_pole_line)
            object_count += 2
        normalized_name = _normalized_road_name(road.route_name)
        if normalized_name and normalized_name not in labelled_roads:
            labelled_roads.add(normalized_name)
            midpoint = road.centerline.interpolate(road.centerline.length / 2.0)
            label_rotation = _line_angle(
                road.centerline, road.centerline.length / 2.0
            )
            _add_dxf_text(
                modelspace,
                "ROAD_LABELS",
                midpoint.x,
                midpoint.y,
                road.route_name,
                2.5,
                rotation=label_rotation,
            )
            object_count += 1

    object_count += _export_osm_features(modelspace, geometry, osm_features)

    rendered_groups: set[frozenset[str]] = set()
    label_slots: dict[tuple[float, float], int] = {}
    for projected in geometry.projected_poles:
        position = (round(projected.snapped.x, 3), round(projected.snapped.y, 3))
        road = geometry.roads[projected.route_index]
        rotation = _line_angle(
            road.centerline, road.centerline.project(projected.snapped)
        )
        rack_group = next(
            (group for group in transformer_rack_groups if projected.pole.number in group),
            None,
        )
        same_group = next(
            (group for group in same_pole_groups if projected.pole.number in group),
            None,
        )
        physical_group = rack_group or same_group or frozenset({projected.pole.number})
        if physical_group not in rendered_groups:
            rendered_groups.add(physical_group)
            members = [
                item
                for item in geometry.projected_poles
                if item.pole.number in physical_group
            ]
            main = next((item for item in geometry.roads if item.is_main_route), road)
            station = main.centerline.project(projected.original)
            block_name = "PRS_TRANSFORMER_RACK" if rack_group else "PRS_POLE"
            reference = modelspace.add_blockref(
                block_name,
                (projected.snapped.x, projected.snapped.y),
                dxfattribs={"layer": "POLES", "rotation": rotation},
            )
            reference.add_auto_attribs(_pole_metadata(members, station, block_name))
            object_count += 1
        label = projected.pole.number
        if projected.pole.detail:
            label += f"  {projected.pole.detail}"
        label_height = 1.8
        label_slot = label_slots.get(position, 0)
        label_slots[position] = label_slot + 1
        _add_dxf_text(
            modelspace,
            "POLE_LABELS",
            projected.snapped.x + 1.2,
            projected.snapped.y + 1.2 + label_slot * (label_height + 0.4),
            label,
            label_height,
            # Keep the CAD Master easy to read and edit.  Text is re-oriented
            # per sheet only after the edited DXF returns for page cutting.
            rotation=0.0,
        )
        object_count += 1

    object_count += _add_sheet_break_markers(
        modelspace,
        geometry,
        settings or ExcelExportSettings(),
    )

    if include_sheet_layouts:
        object_count += _add_sheet_layouts(
            document,
            geometry,
            export_roads,
            structural_surface,
            settings or ExcelExportSettings(),
        )

    try:
        document.saveas(Path(path))
    except (OSError, ezdxf.DXFError) as error:
        raise DxfExportError(f"DXF could not be saved: {error}") from error
    return object_count


def _export_osm_features(modelspace, geometry, features) -> int:
    """Export every accepted OSM feature or fail with its stable identity."""
    count = 0
    for feature in features:
        try:
            count += _export_osm_feature(modelspace, geometry, feature)
        except DxfExportError:
            raise
        except Exception as error:
            raise _osm_export_error(feature, str(error)) from error
    return count


def _export_osm_feature(modelspace, geometry, feature: ContextFeature) -> int:
    geometry_layer, name_layer = OSM_DXF_LAYERS[feature.category]
    projected_parts = []
    for part in feature.parts:
        exterior = tuple(
            _metric_osm_point(geometry, point, feature) for point in part.coordinates
        )
        holes = tuple(
            tuple(_metric_osm_point(geometry, point, feature) for point in hole)
            for hole in part.holes
        )
        projected_parts.append((exterior, holes))

    count = 0
    kind = feature.geometry_kind
    if kind is OSMGeometryKind.POINT:
        for exterior, holes in projected_parts:
            if holes or len(exterior) != 1:
                raise _osm_export_error(feature, "POINT requires one coordinate and no holes")
            entity = modelspace.add_circle(
                exterior[0], radius=1.5, dxfattribs={"layer": geometry_layer}
            )
            _set_context_feature_xdata(entity, feature, part_index=0, ring_role="point")
            count += 1
    elif kind in {OSMGeometryKind.LINESTRING, OSMGeometryKind.MULTILINESTRING}:
        if kind is OSMGeometryKind.LINESTRING and len(projected_parts) != 1:
            raise _osm_export_error(feature, "LINESTRING requires exactly one part")
        for part_index, (exterior, holes) in enumerate(projected_parts):
            if holes or len(exterior) < 2:
                raise _osm_export_error(feature, "line parts require at least two coordinates and no holes")
            entity = modelspace.add_lwpolyline(
                exterior, dxfattribs={"layer": geometry_layer}
            )
            _set_context_feature_xdata(
                entity, feature, part_index=part_index, ring_role="line"
            )
            count += 1
    elif kind in {OSMGeometryKind.POLYGON, OSMGeometryKind.MULTIPOLYGON}:
        if kind is OSMGeometryKind.POLYGON and len(projected_parts) != 1:
            raise _osm_export_error(feature, "POLYGON requires exactly one part")
        for part_index, (exterior, holes) in enumerate(projected_parts):
            if len(exterior) < 3:
                raise _osm_export_error(feature, "polygon exterior requires at least three coordinates")
            entity = modelspace.add_lwpolyline(
                exterior, close=True, dxfattribs={"layer": geometry_layer}
            )
            _set_context_feature_xdata(
                entity, feature, part_index=part_index, ring_role="exterior"
            )
            count += 1
            for ring_index, hole in enumerate(holes):
                if len(hole) < 3:
                    raise _osm_export_error(feature, "polygon hole requires at least three coordinates")
                entity = modelspace.add_lwpolyline(
                    hole, close=True, dxfattribs={"layer": geometry_layer}
                )
                _set_context_feature_xdata(
                    entity,
                    feature,
                    part_index=part_index,
                    ring_role=f"hole:{ring_index}",
                )
                count += 1
    else:
        raise _osm_export_error(feature, "unsupported geometry kind")

    if feature.name:
        x, y = _osm_label_anchor(projected_parts, kind)
        label = _add_dxf_text(modelspace, name_layer, x, y, feature.name, 2.0)
        _set_context_feature_xdata(label, feature, part_index=-1, ring_role="label")
        count += 1
    return count


def _set_context_feature_xdata(
    entity, feature: ContextFeature, *, part_index: int, ring_role: str
) -> None:
    """Attach non-visual, AutoLISP-readable identity metadata to a CAD entity."""

    values = {
        "prs_object_type": "context_feature",
        "prs_feature_key": feature.feature_key,
        "category": feature.category.value,
        "source": feature.source,
        "source_id": feature.source_id,
        "name": feature.name or "",
        "source_release": feature.source_release,
        "provider": feature.provider,
        "dataset": feature.dataset,
        "osm_type": feature.osm_type,
        "osm_id": str(feature.osm_id) if feature.osm_id > 0 else "",
        "prs_part_index": str(part_index),
        "prs_ring_role": ring_role,
    }
    xdata = [(1000, f"{key}={value}"[:255]) for key, value in values.items() if value]
    if feature.confidence is not None:
        xdata.append((1040, feature.confidence))
    entity.set_xdata(PRS_CONTEXT_APPID, xdata)


def _metric_osm_point(geometry, point: GeoPoint, feature: ContextFeature):
    coordinate = geometry.projection.to_metric(point)
    if len(coordinate) != 2 or not all(isfinite(value) for value in coordinate):
        raise _osm_export_error(feature, "coordinate could not be projected to finite metric XY")
    return coordinate


def _osm_label_anchor(projected_parts, kind: OSMGeometryKind) -> tuple[float, float]:
    if kind is OSMGeometryKind.POINT:
        return projected_parts[0][0][0]
    if kind in {OSMGeometryKind.POLYGON, OSMGeometryKind.MULTIPOLYGON}:
        polygons = [Polygon(exterior, holes) for exterior, holes in projected_parts]
        polygon = max(polygons, key=lambda item: item.area)
        anchor = polygon.representative_point()
        return anchor.x, anchor.y
    lines = [LineString(exterior) for exterior, _holes in projected_parts]
    line = max(lines, key=lambda item: item.length)
    anchor = line.interpolate(line.length / 2.0)
    return anchor.x, anchor.y


def _osm_export_error(feature: ContextFeature, reason: str) -> DxfExportError:
    return DxfExportError(
        "OSM feature export failed: "
        f"category={feature.category.value}, identity={feature.osm_type}/{feature.osm_id}, "
        f"geometry_kind={feature.geometry_kind.value}, reason={reason}"
    )


def _define_sheet_break_block(document) -> None:
    """Create a visible, non-plotting CAD marker that survives manual editing."""
    block = document.blocks.new("PRS_SHEET_BREAK")
    block.add_line((0.0, -12.0), (0.0, 12.0), dxfattribs={"layer": "SHEET_BREAK"})
    block.add_line((-1.5, 10.5), (0.0, 12.0), dxfattribs={"layer": "SHEET_BREAK"})
    block.add_line((1.5, 10.5), (0.0, 12.0), dxfattribs={"layer": "SHEET_BREAK"})
    for index, tag in enumerate(("BREAK_ID", "POLE_ID", "STATION_M", "SHEETS")):
        block.add_attdef(
            tag,
            insert=(2.0, 8.0 - index * 2.5),
            height=1.8,
            dxfattribs={"layer": "SHEET_BREAK", "style": "THAI"},
        )


def _add_sheet_break_markers(modelspace, geometry, settings: ExcelExportSettings) -> int:
    """Add one reusable marker at every planned internal pole boundary."""
    main = next((road for road in geometry.roads if road.is_main_route), None)
    if main is None:
        return 0
    requested = int(settings.page_count)
    page_count = requested if requested > 1 else recommended_dxf_sheet_count(geometry)
    ranges = _sheet_station_ranges(geometry, page_count)
    internal_stations = [end for _, end in ranges[:-1]]
    if not internal_stations:
        return 0
    pole_stations = [
        (main.centerline.project(projected.original), projected.pole.number)
        for projected in geometry.projected_poles
    ]
    for index, station in enumerate(internal_stations, start=1):
        point = main.centerline.interpolate(station)
        rotation = _line_angle(main.centerline, station)
        pole_id = min(pole_stations, key=lambda item: abs(item[0] - station))[1]
        reference = modelspace.add_blockref(
            "PRS_SHEET_BREAK",
            (point.x, point.y),
            dxfattribs={"layer": "SHEET_BREAK", "rotation": rotation},
        )
        reference.add_auto_attribs(
            {
                "BREAK_ID": f"SB{index:02d}",
                "POLE_ID": pole_id,
                "STATION_M": f"{station:.2f}",
                "SHEETS": f"{index}/{index + 1}",
            }
        )
    return len(internal_stations)


def recommended_dxf_sheet_count(geometry: RoadNetworkGeometry) -> int:
    """Recommend A4 landscape sheets from true Main-route length."""
    main = next((road for road in geometry.roads if road.is_main_route), None)
    if main is None:
        return 1
    return max(1, ceil(main.centerline.length / DXF_TARGET_SPAN_METRES))


def _sheet_station_ranges(geometry: RoadNetworkGeometry, page_count: int):
    main = next(road for road in geometry.roads if road.is_main_route)
    axis = main.centerline
    stations = sorted(
        {
            round(axis.project(projected.original), 3)
            for projected in geometry.projected_poles
        }
    )
    boundaries = [0.0]
    for page in range(1, page_count):
        target = axis.length * page / page_count
        candidates = [value for value in stations if value > boundaries[-1] + 0.01]
        if not candidates:
            break
        boundaries.append(min(candidates, key=lambda value: abs(value - target)))
    boundaries.append(axis.length)
    return tuple(zip(boundaries, boundaries[1:]))


def _add_sheet_layouts(
    document,
    geometry: RoadNetworkGeometry,
    roads,
    structural_surface,
    settings: ExcelExportSettings,
) -> int:
    main = next((road for road in geometry.roads if road.is_main_route), None)
    if main is None:
        return 0
    requested = int(settings.page_count)
    page_count = requested if requested > 1 else recommended_dxf_sheet_count(geometry)
    ranges = _sheet_station_ranges(geometry, page_count)
    if not ranges:
        return 0
    longest_span = max(end - start for start, end in ranges)
    scale = min(0.68, 250.0 / max(longest_span, 1.0))
    count = 0
    for index, (start_station, end_station) in enumerate(ranges, start=1):
        layout = document.layouts.new(f"Sheet {index:02d}")
        if index == 1 and "Layout1" in document.layout_names():
            document.layouts.delete("Layout1")
        layout.page_setup(
            size=(297, 210),
            margins=(5, 5, 5, 5),
            units="mm",
            device="DWG to PDF.pc3",
        )
        count += _draw_sheet_frame(layout, settings, index, len(ranges))
        axis_part = substring(main.centerline, start_station, end_station)
        if not isinstance(axis_part, LineString) or axis_part.length <= 0:
            continue
        origin = axis_part.coords[0]
        end = axis_part.coords[-1]
        angle = atan2(end[1] - origin[1], end[0] - origin[0])
        view_center = axis_part.interpolate(axis_part.length / 2.0)
        # DXF stores VIEWPORT view-center coordinates in the display coordinate
        # system (DCS).  Once a view twist is applied, passing the unrotated WCS
        # point makes AutoCAD look far away from the actual model geometry.
        dcs_center = (
            view_center.x * cos(angle) + view_center.y * sin(angle),
            -view_center.x * sin(angle) + view_center.y * cos(angle),
        )

        # A sheet is a real Paper Space viewport into the complete Model Space
        # drawing.  Do not reconstruct road geometry here: doing so loses road
        # labels, layers, joined junction outlines, and later CAD edits.
        layout.add_viewport(
            center=(148.5, 126.0),
            size=(267.0, 104.0),
            view_center_point=dcs_center,
            view_height=104.0 / scale,
            status=2,
            dxfattribs={
                "layer": "SHEET_VIEWPORT",
                # VIEWPORT stores the twist in degrees.  The negative route
                # angle makes the selected Main-route section horizontal.
                "view_twist_angle": -degrees(angle),
            },
        )
        count += 1
        page_poles = []
        for projected in geometry.projected_poles:
            station = main.centerline.project(projected.original)
            if start_station - 0.01 <= station <= end_station + 0.01:
                page_poles.append(projected.pole)
        count += _draw_pole_table(layout, page_poles)
        count += _draw_north_arrow(layout, angle)
    return count


def _draw_sheet_frame(layout, settings, page: int, total: int) -> int:
    layout.add_lwpolyline(
        ((8, 8), (289, 8), (289, 202), (8, 202)),
        close=True,
        dxfattribs={"layer": "SHEET_FRAME"},
    )
    _add_dxf_text(layout, "SHEET_FRAME", 14, 194, settings.project_title, 4.0)
    if settings.location:
        _add_dxf_text(layout, "SHEET_FRAME", 14, 188, settings.location, 2.5)
    if settings.work_description:
        _add_dxf_text(layout, "SHEET_FRAME", 14, 183, settings.work_description, 2.5)
    _add_dxf_text(layout, "SHEET_FRAME", 14, 12, f"NOT TO SCALE  |  Sheet {page} / {total}", 2.5)
    if page > 1:
        _add_dxf_text(layout, "SHEET_FRAME", 14, 18, f"<- Sheet {page - 1}", 2.2)
    if page < total:
        _add_dxf_text(layout, "SHEET_FRAME", 260, 18, f"Sheet {page + 1} ->", 2.2)
    return 5 + int(bool(settings.location)) + int(bool(settings.work_description))


def _draw_pole_table(layout, poles) -> int:
    unique = []
    seen = set()
    for pole in poles:
        key = pole.number
        if key not in seen:
            seen.add(key)
            unique.append(pole)
    columns = 2
    rows = max(1, ceil(len(unique) / columns))
    lefts = (14.0, 151.0)
    table_top = 68.0
    row_height = min(5.0, 48.0 / (rows + 1))
    count = 0
    for column, left in enumerate(lefts):
        right = left + 132.0
        layout.add_lwpolyline(
            ((left, table_top), (right, table_top), (right, table_top - row_height * (rows + 1)), (left, table_top - row_height * (rows + 1))),
            close=True,
            dxfattribs={"layer": "SHEET_TABLE"},
        )
        _add_dxf_text(
            layout,
            "SHEET_TABLE",
            left + 2,
            table_top - row_height + 1,
            "No.   Pole No. / Detail                 Installed Qty.",
            2.0,
        )
        count += 2
        start = column * rows
        for row, pole in enumerate(unique[start : start + rows], start=1):
            y = table_top - row_height * row
            layout.add_line((left, y), (right, y), dxfattribs={"layer": "SHEET_TABLE"})
            detail = (
                f"{pole.number}  {pole.detail}"
                f"                 {pole.installed_quantity}"
            ).strip()
            _add_dxf_text(layout, "SHEET_TABLE", left + 2, y - row_height + 1, detail, 1.8)
            count += 2
    return count


def _draw_north_arrow(layout, content_angle: float) -> int:
    north_x = -sin(content_angle)
    north_y = cos(content_angle)
    start = (278.0, 188.0)
    end = (start[0] + north_x * 10.0, start[1] + north_y * 10.0)
    layout.add_line(start, end, dxfattribs={"layer": "SHEET_FRAME"})
    arrow_angle = atan2(end[1] - start[1], end[0] - start[0])
    for delta in (-0.45, 0.45):
        layout.add_line(
            end,
            (end[0] - cos(arrow_angle + delta) * 3.0, end[1] - sin(arrow_angle + delta) * 3.0),
            dxfattribs={"layer": "SHEET_FRAME"},
        )
    _add_dxf_text(layout, "SHEET_FRAME", end[0] + 1, end[1] + 1, "N", 2.5)
    return 4


def _joined_road_surface(roads):
    """Return one road surface so large junction mouths have joined outlines."""
    surfaces = [
        road.centerline.buffer(
            road.road_width_metres / 2.0,
            cap_style="flat",
            join_style="round",
        )
        for road in roads
    ]
    return unary_union(surfaces) if surfaces else None


def _structural_surface_roads(all_roads, structural_roads):
    """Use nearby OSM geometry for manual junctions when a reliable match exists."""
    main_roads = tuple(road for road in structural_roads if road.is_main_route)
    manual_roads = tuple(
        road
        for road in structural_roads
        if road.route_type in {RouteType.CROSS_ROAD, RouteType.T_JUNCTION}
    )
    osm_roads = tuple(road for road in all_roads if road.route_type is RouteType.ROAD)
    if not main_roads or not manual_roads:
        return tuple(structural_roads), ()
    main_axis = unary_union([road.centerline for road in main_roads])
    surfaces = list(main_roads)
    matched: list = []
    for manual in manual_roads:
        manual_anchor, _ = nearest_points(main_axis, manual.centerline)
        candidates = []
        for road in osm_roads:
            road_anchor, _ = nearest_points(main_axis, road.centerline)
            if road.road_width_metres < 8.0:
                continue
            if manual_anchor.distance(road_anchor) > max(
                20.0, manual.road_width_metres / 2.0 + 5.0
            ):
                continue
            if manual.centerline.distance(road.centerline) > max(
                15.0, manual.road_width_metres / 2.0
            ):
                continue
            if _orientation_difference(manual.centerline, road.centerline) > 15.0:
                continue
            candidates.append(road)
        if candidates:
            surfaces.extend(candidates)
            matched.extend(candidates)
        else:
            surfaces.append(manual)
    return tuple(_unique_roads(surfaces)), tuple(_unique_roads(matched))


def _unique_roads(roads):
    result = []
    seen: set[int] = set()
    for road in roads:
        if id(road) not in seen:
            seen.add(id(road))
            result.append(road)
    return result


def _orientation_difference(first: LineString, second: LineString) -> float:
    difference = abs(_overall_line_angle(first) - _overall_line_angle(second)) % 180.0
    return min(difference, 180.0 - difference)


def _overall_line_angle(line: LineString) -> float:
    start = line.coords[0]
    end = line.coords[-1]
    return degrees(atan2(end[1] - start[1], end[0] - start[0])) % 180.0


def _remove_road_end_caps(boundary, roads):
    """Open only the true route ends while preserving joined intersection corners."""
    cap_masks = []
    for road in roads:
        coordinates = tuple(road.centerline.coords)
        if len(coordinates) < 2:
            continue
        half_width = road.road_width_metres / 2.0
        for endpoint, neighbour in (
            (coordinates[0], coordinates[1]),
            (coordinates[-1], coordinates[-2]),
        ):
            dx = endpoint[0] - neighbour[0]
            dy = endpoint[1] - neighbour[1]
            length = hypot(dx, dy)
            if length <= 0:
                continue
            nx = -dy / length * half_width
            ny = dx / length * half_width
            cap = LineString(
                (
                    (endpoint[0] - nx, endpoint[1] - ny),
                    (endpoint[0] + nx, endpoint[1] + ny),
                )
            )
            cap_masks.append(cap.buffer(0.03, cap_style="flat"))
    return boundary.difference(unary_union(cap_masks)) if cap_masks else boundary


def _add_dxf_line(modelspace, layer: str, line: LineString) -> None:
    if len(line.coords) >= 2:
        modelspace.add_lwpolyline(line.coords, dxfattribs={"layer": layer})


def _add_dxf_text(
    modelspace,
    layer: str,
    x: float,
    y: float,
    value: str,
    height: float,
    *,
    rotation: float = 0.0,
) -> object:
    entity = modelspace.add_text(
        value,
        height=height,
        dxfattribs={"layer": layer, "style": "THAI", "rotation": rotation},
    )
    entity.set_placement((x, y))
    return entity


def _deduplicate_context_roads(geometry: RoadNetworkGeometry):
    """Preserve every road explicitly accepted in the surroundings review."""
    return tuple(geometry.roads)


def _road_layers(road) -> tuple[str, str]:
    if road.route_type is RouteType.MAIN_ROUTE:
        return "MAIN_CENTERLINE", "MAIN_ROAD_EDGE"
    if road.route_type is RouteType.CROSS_ROAD:
        return "CROSS_CENTERLINE", "CROSS_ROAD_EDGE"
    if road.route_type is RouteType.T_JUNCTION:
        return "T_CENTERLINE", "T_ROAD_EDGE"
    return "SOI_CENTERLINE", "SOI_EDGE"


def _normalized_road_name(value: str) -> str:
    name = value.strip()
    return "" if not name or name.startswith("Unnamed") else name.casefold()


def _line_parts(geometry) -> tuple[LineString, ...]:
    if isinstance(geometry, LineString):
        return (geometry,) if geometry.length > 0 else ()
    if isinstance(geometry, (MultiLineString, GeometryCollection)):
        return tuple(
            part
            for child in geometry.geoms
            for part in _line_parts(child)
            if part.length > 0
        )
    return ()


def _add_linetype(add, name: str, segments: tuple[float, ...]) -> None:
    add(0, "LTYPE")
    add(2, name)
    add(70, 0)
    add(3, name.title())
    add(72, 65)
    add(73, len(segments))
    add(40, sum(abs(value) for value in segments))
    for value in segments:
        add(49, value)


def _add_polyline(add, layer: str, points, closed: bool = False) -> None:
    points = tuple(points)
    if len(points) < 2:
        return
    add(0, "POLYLINE")
    add(8, layer)
    add(66, 1)
    add(10, 0.0)
    add(20, 0.0)
    add(30, 0.0)
    add(70, 1 if closed else 0)
    for x, y in points:
        add(0, "VERTEX")
        add(8, layer)
        add(10, float(x))
        add(20, float(y))
        add(30, 0.0)
    add(0, "SEQEND")
    add(8, layer)


def _add_insert(add, layer: str, name: str, x: float, y: float, rotation: float) -> None:
    add(0, "INSERT")
    add(8, layer)
    add(2, name)
    add(10, x)
    add(20, y)
    add(30, 0.0)
    add(50, rotation)


def _add_text(add, layer: str, x: float, y: float, value: str, height: float) -> None:
    add(0, "TEXT")
    add(8, layer)
    add(10, x)
    add(20, y)
    add(30, 0.0)
    add(40, height)
    add(1, _dxf_text(value))


def _line_angle(line: LineString, station: float) -> float:
    step = max(min(line.length * 0.001, 1.0), 0.01)
    before = line.interpolate(max(0.0, station - step))
    after = line.interpolate(min(line.length, station + step))
    return degrees(atan2(after.y - before.y, after.x - before.x))


def _dxf_text(value: str) -> str:
    return "".join(character if ord(character) < 128 else f"\\U+{ord(character):04X}" for character in value)


def _format(value: object) -> str:
    return f"{value:.9f}" if isinstance(value, float) else str(value)
