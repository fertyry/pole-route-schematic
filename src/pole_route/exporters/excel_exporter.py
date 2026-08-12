"""Export a Qt graphics scene as editable native Microsoft Excel Shapes."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path

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
) -> int:
    """Create one print-ready worksheet for each approved preview page."""
    if not pages or not any(pages):
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
        while workbook.Worksheets.Count < len(pages):
            workbook.Worksheets.Add(After=workbook.Worksheets(workbook.Worksheets.Count))
        while workbook.Worksheets.Count > len(pages):
            workbook.Worksheets(workbook.Worksheets.Count).Delete()
        for index, objects in enumerate(pages, start=1):
            sheet = workbook.Worksheets(index)
            sheet.Name = f"Sheet {index}"
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
    coordinates = [point for item in objects for point in item.points]
    if not coordinates:
        return objects
    min_x = min(point[0] for point in coordinates)
    min_y = min(point[1] for point in coordinates)
    paper_w_mm, paper_h_mm = ((297.0, 210.0) if settings.paper_size == "A4" else (420.0, 297.0))
    if settings.orientation == "portrait":
        paper_w_mm, paper_h_mm = paper_h_mm, paper_w_mm
    paper_w, paper_h = paper_w_mm * 72 / 25.4, paper_h_mm * 72 / 25.4
    margin, header, footer = 28.0, 54.0, 42.0
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
    """Split START-to-END along the tagged Main route and lay each section horizontally."""
    page_count = max(1, int(settings.page_count))
    if page_count == 1:
        return [prepare_excel_objects(objects, settings)]
    axis = _main_route_axis(objects)
    content = [
        item
        for item in objects
        if not (
            item.role in {"centerline", "main_centerline"}
            and settings.centerline_mode == "hide"
        )
    ]
    if axis is None:
        return _prepare_pages_by_x(content, settings, page_count)
    step = axis.length / page_count
    stations = {_object_key(item): axis.project(Point(_object_center(item))) for item in content}
    pole_stations = {
        item.group_id: stations[_object_key(item)]
        for item in content
        if item.role == "pole" and item.group_id
    }
    pages = []
    for page_index in range(page_count):
        start_station = step * page_index
        end_station = step * (page_index + 1)
        include_end = page_index == page_count - 1
        selected = []
        for item in content:
            station = pole_stations.get(item.group_id, stations[_object_key(item)])
            if item.kind == "line":
                line_stations = [axis.project(Point(point)) for point in item.points]
                belongs = max(line_stations) >= start_station and min(line_stations) <= end_station
            else:
                belongs = (
                    start_station <= station <= end_station
                    if include_end
                    else start_station <= station < end_station
                )
            if belongs:
                selected.append(item)
        start = axis.interpolate(start_station)
        end = axis.interpolate(end_station)
        angle = degrees(atan2(end.y - start.y, end.x - start.x))
        rotated = [_rotate_object(item, -angle, start.x, start.y) for item in selected]
        pages.append(
            _prepare_page(
                rotated,
                settings,
                page_index + 1,
                page_count,
                content_rotation=-angle,
            )
        )
    return pages


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
) -> list[ExcelObject]:
    coordinates = [point for item in objects for point in item.points]
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
    margin, header, footer = 28.0, 54.0, 42.0
    span_x, span_y = max(max_x - min_x, 1.0), max(max_y - min_y, 1.0)
    scale = min((paper_w - 2 * margin) / span_x, (paper_h - header - footer - 2 * margin) / span_y)
    drawing = [
        _apply_pole_size(
            ExcelObject(
                item.kind,
                tuple(((x - min_x) * scale + margin, (y - min_y) * scale + margin + header) for x, y in item.points),
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
    frame = _frame_objects(
        settings, paper_w, paper_h, margin, page_number, page_count, content_rotation
    )
    return [*frame, *drawing, *_continuation_objects(page_number, page_count, paper_w, paper_h, margin)]


def _write_shapes(sheet, objects: list[ExcelObject]) -> None:
    for item in objects:
        if item.kind == "line":
            (x1, y1), (x2, y2) = item.points
            shape = sheet.Shapes.AddLine(x1, y1, x2, y2)
            _set_line(shape, item)
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
    if settings.show_compass:
        cx, cy = paper_w - margin - 24, margin + 30
        direction = radians(-90 + north_rotation)
        tip = (cx + cos(direction) * 32, cy + sin(direction) * 32)
        objects.extend(
            [
                ExcelObject(
                    "line",
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
