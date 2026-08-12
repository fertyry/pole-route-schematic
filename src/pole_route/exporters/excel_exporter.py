"""Export a Qt graphics scene as editable native Microsoft Excel Shapes."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot
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


def collect_excel_objects(
    scene: QGraphicsScene, settings: ExcelExportSettings | None = None
) -> list[ExcelObject]:
    """Flatten visible scene graphics into editable Excel-shape descriptions."""
    return prepare_excel_objects(collect_scene_objects(scene), settings or ExcelExportSettings())


def collect_scene_objects(scene: QGraphicsScene) -> list[ExcelObject]:
    """Snapshot visible scene objects without applying paper or plot styling."""
    objects: list[ExcelObject] = []
    items = [item for item in scene.items() if item.parentItem() is None and item.isVisible()]
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
    if not objects:
        raise ExcelExportError("The canvas has no objects to export.")
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
        role="centerline" if pen.style() is not Qt.PenStyle.SolidLine else "road_edge",
    )


def prepare_excel_objects(
    objects: list[ExcelObject], settings: ExcelExportSettings
) -> list[ExcelObject]:
    """Apply print styling, paper fit, frame, title block, and compass."""
    objects = [item for item in objects if not (item.role == "centerline" and settings.centerline_mode == "hide")]
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
            settings.centerline_width if item.role == "centerline" else settings.road_edge_width,
            item.rotation,
            item.font_size,
            "dashed" if item.role == "centerline" else item.line_style,
            item.role,
        ), settings.pole_size_mm)
        for item in objects
    ]
    frame = _frame_objects(settings, paper_w, paper_h, margin)
    return [*frame, *drawing]


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
    settings: ExcelExportSettings, paper_w: float, paper_h: float, margin: float
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
            _footer_text(settings),
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
        objects.extend(
            [
                ExcelObject(
                    "line",
                    ((cx, cy + 22), (cx, cy - 10)),
                    line_color=black,
                    line_width=1.5,
                    role="compass",
                ),
                ExcelObject(
                    "text",
                    ((cx - 6, cy - 28), (cx + 12, cy - 10)),
                    "N",
                    fill_color=black,
                    font_size=10.0,
                    role="compass",
                ),
            ]
        )
    return objects


def _footer_text(settings: ExcelExportSettings) -> str:
    parts = ["NOT TO SCALE", "Sheet 1 / 1"]
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
    )
