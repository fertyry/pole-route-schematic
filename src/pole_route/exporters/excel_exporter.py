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


def collect_excel_objects(scene: QGraphicsScene) -> list[ExcelObject]:
    """Flatten visible scene graphics into editable Excel-shape descriptions."""
    objects: list[ExcelObject] = []
    items = [item for item in scene.items() if item.parentItem() is None and item.isVisible()]
    for item in reversed(items):
        _collect_item(item, objects)
    return _normalise(objects)


def export_scene_to_excel(scene: QGraphicsScene, path: str | Path) -> int:
    """Create an XLSX workbook containing editable Shapes from the current scene."""
    objects = collect_excel_objects(scene)
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
        sheet.PageSetup.Orientation = 2
        sheet.PageSetup.PaperSize = 8
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
    )


def _normalise(objects: list[ExcelObject]) -> list[ExcelObject]:
    coordinates = [point for item in objects for point in item.points]
    if not coordinates:
        return objects
    min_x = min(point[0] for point in coordinates)
    min_y = min(point[1] for point in coordinates)
    scale = 0.72
    margin = 24.0
    return [
        ExcelObject(
            item.kind,
            tuple(((x - min_x) * scale + margin, (y - min_y) * scale + margin) for x, y in item.points),
            item.text,
            item.line_color,
            item.fill_color,
            item.line_width,
            item.rotation,
            item.font_size,
        )
        for item in objects
    ]


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
