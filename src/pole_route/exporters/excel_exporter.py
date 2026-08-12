"""Export a Qt graphics scene as editable native Microsoft Excel Shapes."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points


class ExcelExportError(RuntimeError):
    """Raised when editable Excel export cannot be completed."""


@dataclass(frozen=True, slots=True)
class ExcelObject:
    kind: str
    points: tuple[tuple[float, float], ...] = ()
    text: str = ""
    line_color: int = 0
    fill_color: int | None = None
    line_width: float = 1.0
    rotation: float = 0.0
    font_size: float = 10.0
    line_style: str = "solid"
    role: str = "drawing"
    group_id: str = ""


@dataclass(frozen=True, slots=True)
class ExcelExportSettings:
    project_title: str = "PoleRoute Schematic"
    location: str = ""
    prepared_by: str = ""
    drawing_number: str = ""
    paper_size: str = "A4"
    orientation: str = "landscape"
    frame_style: str = "standard"
    centerline_mode: str = "dashed"
    pole_size_mm: float = 4.0
    show_compass: bool = True
    road_edge_width: float = 1.0
    centerline_width: float = 0.4
    page_count: int = 1
    work_description: str = ""
    context_road_length: float = 25.0


def collect_excel_objects(
    scene: QGraphicsScene, settings: ExcelExportSettings | None = None
) -> list[ExcelObject]:
    """Flatten visible scene graphics into editable Excel-shape descriptions."""
    return prepare_excel_objects(collect_scene_objects(scene), settings or ExcelExportSettings())


def collect_scene_objects(scene: QGraphicsScene) -> list[ExcelObject]:
    """Snapshot visible scene objects without applying paper or plot styling."""
    # PySide can keep Python ownership of QGraphicsItems even after addItem().  Retain
    # every wrapper on the scene before iterating so a temporary scene.items() list
    # cannot garbage-collect and delete the live canvas objects after export starts.
    scene._pole_route_item_refs = scene.items()
    objects: list[ExcelObject] = []
    items = [
        item
        for item in scene._pole_route_item_refs
        if item.parentItem() is None and item.isVisible()
    ]
    for item in reversed(items):
        _collect_item(item, objects)
    return objects


def export_scene_to_excel(
    scene: QGraphicsScene,
    path: str | Path,
    settings: ExcelExportSettings | None = None,
) -> int:
    """Create an XLSX workbook containing editable Shapes from the current scene."""
    settings = settings or ExcelExportSettings()
    objects = collect_excel_objects(scene, settings)
    return export_objects_to_excel(objects, path, settings)


def export_objects_to_excel(
    objects: list[ExcelObject],
    path: str | Path,
    settings: ExcelExportSettings,
) -> int:
    """Create an XLSX from the exact prepared objects approved in the preview."""
    if not objects:
        raise ExcelExportError("The preview has no objects to export.")
    destination = str(Path(path).resolve())
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
    except Exception as error:
        raise ExcelExportError(
            "Microsoft Excel could not be started. Confirm that desktop Excel is installed."
        ) from error

    workbook = None
    try:
        excel.Visible = False
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Add()
        sheet = workbook.Worksheets(1)
        sheet.Name = "PoleRoute Schematic"
        _write_shapes(sheet, objects)
        sheet.PageSetup.Orientation = 2 if settings.orientation == "landscape" else 1
        sheet.PageSetup.PaperSize = 9 if settings.paper_size == "A4" else 8
        sheet.PageSetup.Zoom = False
        sheet.PageSetup.FitToPagesWide = 1
        sheet.PageSetup.FitToPagesTall = 1
        workbook.SaveAs(destination, FileFormat=51)
        workbook.Close(SaveChanges=False)
        workbook = None
    except Exception as error:
        if workbook is not None:
            workbook.Close(SaveChanges=False)
        raise ExcelExportError(f"Excel export failed: {error}") from error
    finally:
        excel.Quit()
        pythoncom.CoUninitialize()
    return len(objects)


def export_pages_to_excel(
    pages: list[list[ExcelObject]],
    path: str | Path,
    settings: ExcelExportSettings,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> int:
    """Create one print-ready worksheet for each approved preview page."""
    if not pages or not any(pages):
        raise ExcelExportError("The preview has no objects to export.")
    destination = str(Path(path).resolve())
    total_steps = len(pages) + 1
    if progress_callback is not None:
        progress_callback(0, total_steps, "Starting Microsoft Excel...")
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
    except Exception as error:
        raise ExcelExportError(
            "Microsoft Excel could not be started. Confirm that desktop Excel is installed."
        ) from error
    workbook = None
    try:
        excel.Visible = False
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Add()
        while workbook.Worksheets.Count < len(pages):
            workbook.Worksheets.Add(After=workbook.Worksheets(workbook.Worksheets.Count))
        while workbook.Worksheets.Count > len(pages):
            workbook.Worksheets(workbook.Worksheets.Count).Delete()
        for index, objects in enumerate(pages, start=1):
            if progress_callback is not None:
                progress_callback(
                    index - 1,
                    total_steps,
                    f"Creating sheet {index} of {len(pages)}...",
                )
            sheet = workbook.Worksheets(index)
            sheet.Name = f"Sheet {index}"
            _write_shapes(sheet, objects)
            sheet.PageSetup.Orientation = 2 if settings.orientation == "landscape" else 1
            sheet.PageSetup.PaperSize = 9 if settings.paper_size == "A4" else 8
            sheet.PageSetup.Zoom = False
            sheet.PageSetup.FitToPagesWide = 1
            sheet.PageSetup.FitToPagesTall = 1
            if progress_callback is not None:
                progress_callback(index, total_steps, f"Completed sheet {index} of {len(pages)}")
        if progress_callback is not None:
            progress_callback(len(pages), total_steps, "Saving Excel workbook...")
        workbook.SaveAs(destination, FileFormat=51)
        workbook.Close(SaveChanges=False)
        workbook = None
        if progress_callback is not None:
            progress_callback(total_steps, total_steps, "Excel export complete")
    except Exception as error:
        if workbook is not None:
            workbook.Close(SaveChanges=False)
        raise ExcelExportError(f"Excel export failed: {error}") from error
    finally:
        excel.Quit()
        pythoncom.CoUninitialize()
    return sum(len(page) for page in pages)


def _collect_item(item: QGraphicsItem, objects: list[ExcelObject]) -> None:
    if isinstance(item, QGraphicsPathItem):
        path = item.path()
        previous = None
        for index in range(path.elementCount()):
            element = path.elementAt(index)
            current = item.mapToScene(QPointF(element.x, element.y))
            if element.isMoveTo():
                previous = current
            elif previous is not None:
                objects.append(_line_object(item, previous, current))
                previous = current
        return
    if isinstance(item, QGraphicsLineItem):
        line = item.line()
        objects.append(_line_object(item, item.mapToScene(line.p1()), item.mapToScene(line.p2())))
        return
    if isinstance(item, QGraphicsSimpleTextItem):
        bounds = _unrotated_scene_box(item, item.boundingRect())
        objects.append(
            ExcelObject(
                "text",
                _rect_points(bounds),
                item.text(),
                fill_color=_office_color(item.brush().color()),
                rotation=_scene_rotation(item),
                font_size=max(item.font().pointSizeF(), 8.0),
                role=item.data(0) or "label",
                group_id=str(item.data(1) or ""),
            )
        )
        return
    if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
        bounds = _unrotated_scene_box(item, item.rect())
        pen = item.pen()
        brush = item.brush()
        objects.append(
            ExcelObject(
                "rectangle" if isinstance(item, QGraphicsRectItem) else "ellipse",
                _rect_points(bounds),
                line_color=_office_color(pen.color()),
                fill_color=(
                    _office_color(brush.color())
                    if brush.style() is not Qt.BrushStyle.NoBrush
                    else None
                ),
                line_width=max(pen.widthF(), 0.5),
                rotation=_scene_rotation(item),
                role=item.data(0) or "drawing",
                group_id=str(item.data(1) or ""),
            )
        )
        return
    for child in reversed(item.childItems()):
        if child.isVisible():
            _collect_item(child, objects)


def _line_object(item, start: QPointF, end: QPointF) -> ExcelObject:
    pen = item.pen()
    return ExcelObject(
        "line",
        ((start.x(), start.y()), (end.x(), end.y())),
        line_color=_office_color(pen.color()),
        line_width=max(pen.widthF(), 0.5),
        line_style="dashed" if pen.style() is not Qt.PenStyle.SolidLine else "solid",
        role=(
            "main_centerline"
            if item.data(5) == "main_centerline"
            else "centerline"
            if pen.style() is not Qt.PenStyle.SolidLine
            else "road_edge"
        ),
        group_id=str(item.data(6) or ""),
    )


def prepare_excel_objects(
    objects: list[ExcelObject], settings: ExcelExportSettings
) -> list[ExcelObject]:
    """Apply print styling, paper fit, frame, title block, and compass."""
    objects = [
        item for item in objects
        if not (item.role in {"centerline", "main_centerline"} and settings.centerline_mode == "hide")
    ]
    scale_objects = [item for item in objects if item.role != "road_name"]
    coordinates = [point for item in scale_objects for point in item.points]
    if not coordinates:
        return objects
    min_x = min(point[0] for point in coordinates)
    min_y = min(point[1] for point in coordinates)
    paper_w_mm, paper_h_mm = ((297.0, 210.0) if settings.paper_size == "A4" else (420.0, 297.0))
    if settings.orientation == "portrait":
        paper_w_mm, paper_h_mm = paper_h_mm, paper_w_mm
    paper_w, paper_h = paper_w_mm * 72 / 25.4, paper_h_mm * 72 / 25.4
    margin, header, footer = 28.0, 72.0, 42.0
    max_x = max(point[0] for point in coordinates)
    max_y = max(point[1] for point in coordinates)
    span_x, span_y = max(max_x - min_x, 1.0), max(max_y - min_y, 1.0)
    scale = min((paper_w - 2 * margin) / span_x, (paper_h - header - footer - 2 * margin) / span_y)
    drawing = [
        _apply_pole_size(ExcelObject(
            item.kind,
            tuple(((x - min_x) * scale + margin, (y - min_y) * scale + margin + header) for x, y in item.points),
            item.text,
            0,
            0 if item.fill_color is not None or item.role == "pole" else None,
            settings.centerline_width if item.role in {"centerline", "main_centerline"} else settings.road_edge_width,
            item.rotation,
            item.font_size,
            "dashed" if item.role in {"centerline", "main_centerline"} else item.line_style,
            item.role,
            item.group_id,
        ), settings.pole_size_mm)
        for item in objects
    ]
    frame = _frame_objects(settings, paper_w, paper_h, margin, 1, 1, 0.0)
    return [*frame, *drawing]


def prepare_excel_pages(
    objects: list[ExcelObject], settings: ExcelExportSettings
) -> list[list[ExcelObject]]:
    """Split at physical poles along Main route and compose readable paper sheets."""
    page_count = max(1, int(settings.page_count))
    content = [
        item
        for item in objects
        if not (
            item.role in {"centerline", "main_centerline"}
            and settings.centerline_mode == "hide"
        )
    ]
    axis = _main_route_axis(content)
    if axis is not None:
        content = _limit_context_road_reach(
            content, axis, settings.context_road_length
        )
    if page_count == 1:
        return [prepare_excel_objects(content, settings)]
    if axis is None:
        return _prepare_pages_by_x(content, settings, page_count)
    stations = {_object_key(item): axis.project(Point(_object_center(item))) for item in content}
    pole_stations = {
        item.group_id: stations[_object_key(item)]
        for item in content
        if item.role == "pole" and item.group_id
    }
    ordered_poles = sorted(pole_stations, key=lambda group_id: (pole_stations[group_id], group_id))
    if len(ordered_poles) < 2:
        return [prepare_excel_objects(content, settings)]
    # Internal boundaries are real poles. The same match pole appears on both sheets.
    boundary_indices = _pole_boundary_indices(
        ordered_poles, pole_stations, content, axis, page_count
    )
    sequence_by_group = {
        group_id: index for index, group_id in enumerate(ordered_poles, start=1)
    }
    label_by_group = {
        item.group_id: item.text
        for item in content
        if item.role == "label" and item.group_id
    }
    page_specs = []
    for page_index in range(page_count):
        first_index = boundary_indices[page_index]
        last_index = boundary_indices[page_index + 1]
        page_groups = set(ordered_poles[first_index : last_index + 1])
        start_station = pole_stations[ordered_poles[first_index]]
        end_station = pole_stations[ordered_poles[last_index]]
        selected = []
        for item in content:
            station = pole_stations.get(item.group_id, stations[_object_key(item)])
            if item.kind == "line":
                line_stations = [axis.project(Point(point)) for point in item.points]
                belongs = max(line_stations) >= start_station and min(line_stations) <= end_station
            else:
                belongs = (
                    item.group_id in page_groups
                    if item.group_id in pole_stations
                    else start_station <= station <= end_station
                )
            if belongs:
                selected.append(item)
        start = axis.interpolate(start_station)
        end = axis.interpolate(end_station)
        angle = degrees(atan2(end.y - start.y, end.x - start.x))
        rotated = [
            _rotate_object(item, -angle, start.x, start.y)
            for item in selected
            if item.role != "label"
        ]
        records = [
            (sequence_by_group[group_id], group_id, label_by_group.get(group_id, group_id))
            for group_id in ordered_poles[first_index : last_index + 1]
        ]
        rotated_pole_centers = [
            _object_center(item)[0]
            for item in rotated
            if item.role == "pole" and item.group_id in page_groups
        ]
        clip_left, clip_right = min(rotated_pole_centers), max(rotated_pole_centers)
        clipped = _clip_objects_to_x(rotated, clip_left, clip_right)
        page_specs.append((clipped, -angle, records))
    shared_scale = _shared_page_scale(
        [spec[0] for spec in page_specs], settings
    )
    pages = []
    for page_index, (clipped, rotation, records) in enumerate(page_specs):
        pages.append(
            _prepare_page(
                clipped,
                settings,
                page_index + 1,
                page_count,
                content_rotation=rotation,
                pole_records=records,
                scale_override=shared_scale,
            )
        )
    return pages


def _limit_context_road_reach(
    objects: list[ExcelObject], axis: LineString, total_length: float
) -> list[ExcelObject]:
    """Clip surrounding roads to a narrow corridor used only by Excel output."""
    half_length = max(float(total_length), 1.0) / 2.0
    corridor = axis.buffer(half_length, cap_style="flat")
    name_anchors: dict[str, list[tuple[Point, Point, LineString]]] = {}
    all_anchors: list[tuple[Point, Point, LineString]] = []
    for item in objects:
        if item.kind != "line" or item.role != "centerline":
            continue
        context_line = LineString(item.points)
        anchor, context_point = nearest_points(axis, context_line)
        candidate = (anchor, context_point, context_line)
        all_anchors.append(candidate)
        if item.group_id:
            name_anchors.setdefault(item.group_id, []).append(candidate)
    limited: list[ExcelObject] = []
    for item in objects:
        if item.kind == "line" and item.role in {"road_edge", "centerline"}:
            intersection = LineString(item.points).intersection(corridor)
            parts = _line_parts(intersection)
            limited.extend(_replace_points(item, tuple(part.coords)) for part in parts)
            continue
        if item.role == "road_name" and item.kind == "text":
            limited.append(
                _place_road_name_at_junction(
                    item,
                    axis,
                    name_anchors.get(item.group_id) or all_anchors,
                    half_length * 0.72,
                )
            )
            continue
        limited.append(item)
    return limited


def _line_parts(geometry) -> list[LineString]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [
            part
            for child in geometry.geoms
            for part in _line_parts(child)
        ]
    return []


def _replace_points(
    item: ExcelObject, points: tuple[tuple[float, float], ...]
) -> ExcelObject:
    return ExcelObject(
        item.kind, points, item.text, item.line_color, item.fill_color,
        item.line_width, item.rotation, item.font_size, item.line_style,
        item.role, item.group_id,
    )


def _place_road_name_at_junction(
    item: ExcelObject,
    axis: LineString,
    anchors: list[tuple[Point, Point, LineString]],
    label_offset: float,
) -> ExcelObject:
    center_x, center_y = _object_center(item)
    center = Point(center_x, center_y)
    if anchors:
        nearest, context_point, _context_line = min(
            anchors, key=lambda candidate: candidate[2].distance(center)
        )
    else:
        nearest = axis.interpolate(axis.project(center))
        context_point = center
    dx, dy = context_point.x - nearest.x, context_point.y - nearest.y
    distance = hypot(dx, dy)
    if distance <= 1e-9:
        station = axis.project(nearest)
        step = max(min(axis.length * 0.001, 1.0), 0.01)
        before = axis.interpolate(max(0.0, station - step))
        after = axis.interpolate(min(axis.length, station + step))
        tangent_x, tangent_y = after.x - before.x, after.y - before.y
        tangent_length = max(hypot(tangent_x, tangent_y), 1e-9)
        dx, dy = -tangent_y / tangent_length, tangent_x / tangent_length
    else:
        dx, dy = dx / distance, dy / distance
    new_x = nearest.x + dx * label_offset
    new_y = nearest.y + dy * label_offset
    (left, top), (right, bottom) = item.points
    half_width, half_height = (right - left) / 2.0, (bottom - top) / 2.0
    return _replace_points(
        item,
        ((new_x - half_width, new_y - half_height),
         (new_x + half_width, new_y + half_height)),
    )


def _pole_boundary_indices(
    ordered_poles: list[str],
    pole_stations: dict[str, float],
    content: list[ExcelObject],
    axis: LineString,
    page_count: int,
) -> list[int]:
    """Choose real pole boundaries while avoiding side-road junctions."""
    last = len(ordered_poles) - 1
    junctions = [
        axis.project(Point(_object_center(item)))
        for item in content
        if item.role == "centerline" and item.kind == "line"
    ]
    result = [0]
    for page in range(1, page_count):
        target_station = axis.length * page / page_count
        ideal = min(
            range(last + 1),
            key=lambda index: abs(
                pole_stations[ordered_poles[index]] - target_station
            ),
        )
        lower = result[-1] + 1
        upper = last - (page_count - page)
        ideal = max(lower, min(ideal, upper))
        candidates = range(max(lower, ideal - 4), min(upper, ideal + 4) + 1)

        def score(index: int) -> tuple[float, float]:
            station = pole_stations[ordered_poles[index]]
            nearest_junction = min((abs(station - value) for value in junctions), default=float("inf"))
            previous_gap = abs(
                station - pole_stations[ordered_poles[max(0, index - 1)]]
            )
            next_gap = abs(
                pole_stations[ordered_poles[min(last, index + 1)]] - station
            )
            danger_distance = max((previous_gap + next_gap) * 0.75, 18.0)
            junction_penalty = max(0.0, danger_distance - nearest_junction) * 1000.0
            station_error = abs(station - target_station)
            return (junction_penalty + station_error, station_error)

        result.append(min(candidates, key=score))
    result.append(last)
    return result


def _main_route_axis(objects: list[ExcelObject]) -> LineString | None:
    groups: dict[str, list[ExcelObject]] = {}
    for item in objects:
        if item.role == "main_centerline" and item.kind == "line":
            groups.setdefault(item.group_id or "main", []).append(item)
    if not groups:
        return None
    segments = max(
        groups.values(),
        key=lambda items: sum(hypot(b[0] - a[0], b[1] - a[1]) for item in items for a, b in [item.points]),
    )
    points = [segments[0].points[0], *[item.points[1] for item in segments]]
    return LineString(points) if len(points) >= 2 else None


def _object_key(item: ExcelObject) -> int:
    return id(item)


def _object_center(item: ExcelObject) -> tuple[float, float]:
    xs = [x for x, _ in item.points]
    ys = [y for _, y in item.points]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _rotate_point(x: float, y: float, angle: float, origin_x: float, origin_y: float):
    theta = radians(angle)
    dx, dy = x - origin_x, y - origin_y
    return (
        origin_x + dx * cos(theta) - dy * sin(theta),
        origin_y + dx * sin(theta) + dy * cos(theta),
    )


def _rotate_object(
    item: ExcelObject, angle: float, origin_x: float, origin_y: float
) -> ExcelObject:
    if item.kind == "line":
        points = tuple(_rotate_point(x, y, angle, origin_x, origin_y) for x, y in item.points)
        rotation = item.rotation
    else:
        center_x, center_y = _object_center(item)
        new_x, new_y = _rotate_point(center_x, center_y, angle, origin_x, origin_y)
        (left, top), (right, bottom) = item.points
        half_width, half_height = (right - left) / 2, (bottom - top) / 2
        points = ((new_x - half_width, new_y - half_height), (new_x + half_width, new_y + half_height))
        rotation = 0.0 if item.kind == "text" else item.rotation + angle
    return ExcelObject(
        item.kind, points, item.text, item.line_color, item.fill_color, item.line_width,
        rotation, item.font_size, item.line_style, item.role, item.group_id
    )


def _clip_objects_to_x(
    objects: list[ExcelObject], left: float, right: float
) -> list[ExcelObject]:
    """Clip page geometry at the two match-pole positions."""
    clipped: list[ExcelObject] = []
    for item in objects:
        if item.kind != "line":
            center_x, _center_y = _object_center(item)
            if left - 1e-6 <= center_x <= right + 1e-6:
                clipped.append(item)
            continue
        (x1, y1), (x2, y2) = item.points
        if max(x1, x2) < left or min(x1, x2) > right:
            continue
        if abs(x2 - x1) < 1e-12:
            clipped.append(item)
            continue
        start_t = max(0.0, min(1.0, (left - x1) / (x2 - x1)))
        end_t = max(0.0, min(1.0, (right - x1) / (x2 - x1)))
        low_t, high_t = sorted((start_t, end_t))
        # When both endpoints are already inside, keep the original segment.
        if left <= x1 <= right and left <= x2 <= right:
            low_t, high_t = 0.0, 1.0
        points = (
            (x1 + (x2 - x1) * low_t, y1 + (y2 - y1) * low_t),
            (x1 + (x2 - x1) * high_t, y1 + (y2 - y1) * high_t),
        )
        clipped.append(
            ExcelObject(
                item.kind, points, item.text, item.line_color, item.fill_color,
                item.line_width, item.rotation, item.font_size, item.line_style,
                item.role, item.group_id,
            )
        )
    return clipped


def _paper_map_size(settings: ExcelExportSettings) -> tuple[float, float]:
    paper_w_mm, paper_h_mm = (
        (297.0, 210.0) if settings.paper_size == "A4" else (420.0, 297.0)
    )
    if settings.orientation == "portrait":
        paper_w_mm, paper_h_mm = paper_h_mm, paper_w_mm
    paper_w, paper_h = paper_w_mm * 72 / 25.4, paper_h_mm * 72 / 25.4
    margin, header = 28.0, 72.0
    return paper_w - 2 * margin, paper_h * 0.60 - (margin + header)


def _shared_page_scale(
    pages: list[list[ExcelObject]], settings: ExcelExportSettings
) -> float:
    """Use one affine display scale for the complete sheet set."""
    map_width, map_height = _paper_map_size(settings)
    candidates = []
    for objects in pages:
        coordinates = [
            point for item in objects if item.role != "road_name" for point in item.points
        ]
        if not coordinates:
            continue
        span_x = max(x for x, _ in coordinates) - min(x for x, _ in coordinates)
        span_y = max(y for _, y in coordinates) - min(y for _, y in coordinates)
        candidates.append(
            min(map_width / max(span_x, 1.0), map_height / max(span_y, 1.0))
        )
    return min(candidates, default=1.0)


def _prepare_pages_by_x(
    content: list[ExcelObject], settings: ExcelExportSettings, page_count: int
) -> list[list[ExcelObject]]:
    coordinates = [point for item in content for point in item.points]
    if not coordinates:
        return [[]]
    min_x, max_x = min(x for x, _ in coordinates), max(x for x, _ in coordinates)
    step = max(max_x - min_x, 1.0) / page_count
    pages = []
    for page_index in range(page_count):
        left, right = min_x + step * page_index, min_x + step * (page_index + 1)
        selected = [
            item for item in content
            if _object_belongs_to_page(item, left, right, page_index == page_count - 1)
        ]
        pages.append(_prepare_page(selected, settings, page_index + 1, page_count))
    return pages


def _object_belongs_to_page(
    item: ExcelObject, left: float, right: float, include_right: bool
) -> bool:
    xs = [point[0] for point in item.points]
    if not xs:
        return False
    if item.kind == "line":
        return max(xs) >= left and min(xs) <= right
    center = (min(xs) + max(xs)) / 2
    return left <= center <= right if include_right else left <= center < right


def _prepare_page(
    objects: list[ExcelObject],
    settings: ExcelExportSettings,
    page_number: int,
    page_count: int,
    content_rotation: float = 0.0,
    pole_records: list[tuple[int, str, str]] | None = None,
    scale_override: float | None = None,
) -> list[ExcelObject]:
    scale_objects = [item for item in objects if item.role != "road_name"]
    coordinates = [point for item in scale_objects for point in item.points]
    if not coordinates:
        return []
    min_x = min(x for x, _ in coordinates)
    min_y = min(y for _, y in coordinates)
    max_x = max(x for x, _ in coordinates)
    max_y = max(y for _, y in coordinates)
    paper_w_mm, paper_h_mm = ((297.0, 210.0) if settings.paper_size == "A4" else (420.0, 297.0))
    if settings.orientation == "portrait":
        paper_w_mm, paper_h_mm = paper_h_mm, paper_w_mm
    paper_w, paper_h = paper_w_mm * 72 / 25.4, paper_h_mm * 72 / 25.4
    margin, header, footer = 28.0, 72.0, 42.0
    map_left, map_right = margin, paper_w - margin
    map_top = margin + header
    map_bottom = paper_h * 0.60
    span_x, span_y = max(max_x - min_x, 1.0), max(max_y - min_y, 1.0)
    scale = scale_override or min(
        (map_right - map_left) / span_x, (map_bottom - map_top) / span_y
    )
    fitted_w, fitted_h = span_x * scale, span_y * scale
    origin_x = map_left + ((map_right - map_left) - fitted_w) / 2
    origin_y = map_top + ((map_bottom - map_top) - fitted_h) / 2
    drawing = [
        _apply_pole_size(
            ExcelObject(
                item.kind,
                tuple(((x - min_x) * scale + origin_x, (y - min_y) * scale + origin_y) for x, y in item.points),
                item.text, 0,
                0 if item.fill_color is not None or item.role == "pole" else None,
                settings.centerline_width if item.role in {"centerline", "main_centerline"} else settings.road_edge_width,
                item.rotation, item.font_size,
                "dashed" if item.role in {"centerline", "main_centerline"} else item.line_style,
                item.role,
                item.group_id,
            ),
            settings.pole_size_mm,
        )
        for item in objects
    ]
    pole_centers = {
        item.group_id: _object_center(item)
        for item in drawing
        if item.role == "pole" and item.group_id
    }
    sequences_by_center: dict[tuple[float, float], list[int]] = {}
    for sequence, group_id, _detail in pole_records or []:
        if group_id not in pole_centers:
            continue
        x, y = pole_centers[group_id]
        sequences_by_center.setdefault((round(x, 5), round(y, 5)), []).append(sequence)
    sequence_labels = []
    for (x, y), sequences in sequences_by_center.items():
        sequence_labels.append(
            ExcelObject(
                "text",
                ((x - 8, y - 22), (x + 16, y - 8)),
                "/".join(str(sequence) for sequence in sequences),
                fill_color=0,
                font_size=8.0,
                role="pole_sequence",
                group_id="/".join(str(sequence) for sequence in sequences),
            )
        )
    frame = _frame_objects(
        settings, paper_w, paper_h, margin, page_number, page_count, content_rotation
    )
    schedule = _pole_schedule_objects(
        pole_records or [], paper_w, paper_h, margin, map_bottom + 18, footer
    )
    return [
        *frame,
        *drawing,
        *sequence_labels,
        *schedule,
        *_continuation_objects(page_number, page_count, paper_w, paper_h, margin),
    ]


def _pole_schedule_objects(
    records: list[tuple[int, str, str]],
    paper_w: float,
    paper_h: float,
    margin: float,
    top: float,
    footer: float,
) -> list[ExcelObject]:
    """Build a compact two-column pole schedule below the map."""
    if not records:
        return []
    bottom = paper_h - margin - footer
    available_h = max(bottom - top, 36.0)
    column_count = 2 if len(records) > 8 else 1
    rows_per_column = (len(records) + column_count - 1) // column_count
    row_h = min(18.0, available_h / (rows_per_column + 1))
    column_w = (paper_w - 2 * margin) / column_count
    objects: list[ExcelObject] = []
    for column in range(column_count):
        left = margin + column * column_w
        right = left + column_w - 8
        first = column * rows_per_column
        chunk = records[first : first + rows_per_column]
        if not chunk:
            continue
        objects.extend(
            [
                ExcelObject("line", ((left, top), (right, top)), line_color=0, line_width=0.6, role="schedule"),
                ExcelObject("line", ((left, top + row_h), (right, top + row_h)), line_color=0, line_width=0.6, role="schedule"),
                ExcelObject("text", ((left + 3, top + 1), (left + 35, top + row_h)), "No.", fill_color=0, font_size=7.0, role="schedule"),
                ExcelObject("text", ((left + 38, top + 1), (right, top + row_h)), "Pole No. / Detail", fill_color=0, font_size=7.0, role="schedule"),
            ]
        )
        for row, (sequence, group_id, detail) in enumerate(chunk, start=1):
            y = top + row_h * row
            display_detail = detail
            prefix = f"{group_id} "
            if display_detail.startswith(prefix):
                display_detail = display_detail[len(prefix) :]
            objects.extend(
                [
                    ExcelObject("text", ((left + 3, y + 1), (left + 35, y + row_h)), str(sequence), fill_color=0, font_size=7.0, role="schedule", group_id=group_id),
                    ExcelObject("text", ((left + 38, y + 1), (right, y + row_h)), f"{group_id}  {display_detail}".strip(), fill_color=0, font_size=7.0, role="schedule", group_id=group_id),
                    ExcelObject("line", ((left, y + row_h), (right, y + row_h)), line_color=0, line_width=0.35, role="schedule"),
                ]
            )
        divider_x = left + 35
        table_bottom = top + row_h * (len(chunk) + 1)
        objects.extend(
            [
                ExcelObject("line", ((left, top), (left, table_bottom)), line_color=0, line_width=0.6, role="schedule"),
                ExcelObject("line", ((divider_x, top), (divider_x, table_bottom)), line_color=0, line_width=0.35, role="schedule"),
                ExcelObject("line", ((right, top), (right, table_bottom)), line_color=0, line_width=0.6, role="schedule"),
            ]
        )
    return objects


def _write_shapes(sheet, objects: list[ExcelObject]) -> None:
    for item in objects:
        if item.kind in {"line", "arrow"}:
            (x1, y1), (x2, y2) = item.points
            shape = sheet.Shapes.AddLine(x1, y1, x2, y2)
            _set_line(shape, item)
            if item.kind == "arrow":
                shape.Line.EndArrowheadStyle = 3
        elif item.kind == "text":
            left, top, width, height = _bounds(item.points)
            shape = sheet.Shapes.AddTextbox(1, left, top, max(width, 20), max(height, 14))
            shape.TextFrame2.TextRange.Text = item.text
            shape.TextFrame2.TextRange.Font.Size = item.font_size
            shape.TextFrame2.TextRange.Font.Fill.ForeColor.RGB = item.fill_color
            shape.TextFrame2.AutoSize = 1
            shape.Line.Visible = 0
            shape.Fill.Visible = 0
            shape.Rotation = item.rotation
        else:
            left, top, width, height = _bounds(item.points)
            shape_type = 1 if item.kind == "rectangle" else 9
            shape = sheet.Shapes.AddShape(shape_type, left, top, max(width, 1), max(height, 1))
            _set_line(shape, item)
            if item.fill_color is None:
                shape.Fill.Visible = 0
            else:
                shape.Fill.Visible = -1
                shape.Fill.ForeColor.RGB = item.fill_color
            shape.Rotation = item.rotation


def _set_line(shape, item: ExcelObject) -> None:
    shape.Line.Visible = -1
    shape.Line.ForeColor.RGB = item.line_color
    shape.Line.Weight = item.line_width
    if item.line_style == "dashed":
        shape.Line.DashStyle = 4


def _bounds(points: tuple[tuple[float, float], ...]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _rect_points(rect) -> tuple[tuple[float, float], ...]:
    return ((rect.left(), rect.top()), (rect.right(), rect.bottom()))


def _unrotated_scene_box(item: QGraphicsItem, rect: QRectF) -> QRectF:
    center = item.mapToScene(rect.center())
    left = item.mapToScene(QPointF(rect.left(), rect.center().y()))
    right = item.mapToScene(QPointF(rect.right(), rect.center().y()))
    top = item.mapToScene(QPointF(rect.center().x(), rect.top()))
    bottom = item.mapToScene(QPointF(rect.center().x(), rect.bottom()))
    width = hypot(right.x() - left.x(), right.y() - left.y())
    height = hypot(bottom.x() - top.x(), bottom.y() - top.y())
    return QRectF(center.x() - width / 2, center.y() - height / 2, width, height)


def _scene_rotation(item: QGraphicsItem) -> float:
    transform = item.sceneTransform()
    return degrees(atan2(transform.m12(), transform.m11()))


def _office_color(color: QColor) -> int:
    return color.red() + color.green() * 256 + color.blue() * 65536


def _frame_objects(
    settings: ExcelExportSettings,
    paper_w: float,
    paper_h: float,
    margin: float,
    page_number: int,
    page_count: int,
    north_rotation: float,
) -> list[ExcelObject]:
    if settings.frame_style == "none":
        return []
    black = 0
    objects = [
        ExcelObject(
            "rectangle",
            ((margin / 2, margin / 2), (paper_w - margin / 2, paper_h - margin / 2)),
            line_color=black,
            line_width=1.0,
            role="frame",
        ),
        ExcelObject(
            "text",
            ((margin, margin), (paper_w - margin, margin + 24)),
            settings.project_title or "PoleRoute Schematic",
            fill_color=black,
            font_size=14.0,
            role="title",
        ),
        ExcelObject(
            "text",
            ((margin, paper_h - margin - 20), (paper_w - margin, paper_h - margin)),
            _footer_text(settings, page_number, page_count),
            fill_color=black,
            font_size=8.0,
            role="footer",
        ),
    ]
    if settings.location:
        objects.append(
            ExcelObject(
                "text",
                ((margin, margin + 24), (paper_w - margin, margin + 42)),
                settings.location,
                fill_color=black,
                font_size=10.0,
                role="subtitle",
            )
        )
    if settings.work_description:
        objects.append(
            ExcelObject(
                "text",
                ((margin, margin + 42), (paper_w - margin, margin + 60)),
                settings.work_description,
                fill_color=black,
                font_size=10.0,
                role="work_description",
            )
        )
    if settings.show_compass:
        cx, cy = paper_w - margin - 24, margin + 30
        direction = radians(-90 + north_rotation)
        tip = (cx + cos(direction) * 32, cy + sin(direction) * 32)
        objects.extend(
            [
                ExcelObject(
                    "arrow",
                    ((cx, cy), tip),
                    line_color=black,
                    line_width=1.5,
                    role="compass",
                ),
                ExcelObject(
                    "text",
                    ((tip[0] - 6, tip[1] - 16), (tip[0] + 12, tip[1] + 2)),
                    "N",
                    fill_color=black,
                    font_size=10.0,
                    role="compass",
                ),
            ]
        )
    return objects


def _continuation_objects(
    page_number: int, page_count: int, paper_w: float, paper_h: float, margin: float
) -> list[ExcelObject]:
    objects = []
    y = paper_h - margin - 42
    if page_number > 1:
        objects.append(
            ExcelObject(
                "text", ((margin, y), (margin + 110, y + 18)),
                f"← Sheet {page_number - 1}", fill_color=0, font_size=8.0,
                role="continuation",
            )
        )
    if page_number < page_count:
        objects.append(
            ExcelObject(
                "text", ((paper_w - margin - 110, y), (paper_w - margin, y + 18)),
                f"Sheet {page_number + 1} →", fill_color=0, font_size=8.0,
                role="continuation",
            )
        )
    return objects


def _footer_text(settings: ExcelExportSettings, page_number: int, page_count: int) -> str:
    parts = ["NOT TO SCALE", f"Sheet {page_number} / {page_count}"]
    if settings.drawing_number:
        parts.insert(0, f"Drawing: {settings.drawing_number}")
    if settings.prepared_by:
        parts.insert(0, f"Prepared by: {settings.prepared_by}")
    return "    |    ".join(parts)


def _apply_pole_size(item: ExcelObject, size_mm: float) -> ExcelObject:
    if item.role != "pole" or item.kind != "rectangle":
        return item
    (left, top), (right, bottom) = item.points
    center_x, center_y = (left + right) / 2, (top + bottom) / 2
    size = size_mm * 72 / 25.4
    return ExcelObject(
        item.kind,
        ((center_x - size / 2, center_y - size / 2), (center_x + size / 2, center_y + size / 2)),
        item.text,
        item.line_color,
        item.fill_color,
        item.line_width,
        item.rotation,
        item.font_size,
        item.line_style,
        item.role,
        item.group_id,
    )
