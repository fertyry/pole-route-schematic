"""Portable JSON project files for PoleRoute Schematic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
)

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.ui.editor_commands import (
    EditableEllipseItem,
    EditableItemGroup,
    EditableLineItem,
    EditableRectItem,
    EditableTextItem,
)
from pole_route.ui.schematic_renderer import EDITABLE_FLAGS

PROJECT_VERSION = 1


class ProjectFileError(RuntimeError):
    """Raised when a project cannot be saved or opened."""


def save_project_file(path: str | Path, payload: dict[str, Any]) -> None:
    document = {"format": "PoleRoute Schematic", "version": PROJECT_VERSION, **payload}
    try:
        Path(path).write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, TypeError, ValueError) as error:
        raise ProjectFileError(f"Project could not be saved: {error}") from error


def load_project_file(path: str | Path) -> dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectFileError(f"Project could not be opened: {error}") from error
    if document.get("format") != "PoleRoute Schematic":
        raise ProjectFileError("This is not a PoleRoute Schematic project file.")
    if document.get("version") != PROJECT_VERSION:
        raise ProjectFileError(
            f"Project version {document.get('version')} is not supported by this app."
        )
    return document


def routes_to_data(routes: list[ClassifiedRoute]) -> list[dict[str, Any]]:
    return [
        {
            "name": item.route.name,
            "source_path": item.route.source_path,
            "points": [
                [point.longitude, point.latitude, point.altitude]
                for point in item.route.points
            ],
            "type": item.type.value,
            "width_metres": item.width_metres,
            "pole_offset_metres": item.pole_offset_metres,
            "create_pole_line": item.create_pole_line,
        }
        for item in routes
    ]


def routes_from_data(data: list[dict[str, Any]]) -> list[ClassifiedRoute]:
    return [
        ClassifiedRoute(
            Route(
                item["name"],
                item.get("source_path", ""),
                tuple(GeoPoint(*point) for point in item["points"]),
            ),
            RouteType(item["type"]),
            item.get("width_metres"),
            item.get("pole_offset_metres"),
            item.get("create_pole_line", True),
        )
        for item in data
    ]


def poles_to_data(poles: list[Pole]) -> list[dict[str, Any]]:
    return [
        {
            "number": pole.number,
            "latitude": pole.latitude,
            "longitude": pole.longitude,
            "detail": pole.detail,
            "side": pole.side.value,
        }
        for pole in poles
    ]


def poles_from_data(data: list[dict[str, Any]]) -> list[Pole]:
    return [
        Pole(
            item["number"],
            float(item["latitude"]),
            float(item["longitude"]),
            item.get("detail", ""),
            PoleSide(item.get("side", PoleSide.UNKNOWN.value)),
        )
        for item in data
    ]


def scene_to_data(scene: QGraphicsScene) -> dict[str, Any]:
    """Serialize the exact editable scene hierarchy without rasterizing it."""
    scene._pole_route_item_refs = scene.items()
    top_level = [item for item in scene._pole_route_item_refs if item.parentItem() is None]
    rect = scene.sceneRect()
    return {
        "rect": [rect.x(), rect.y(), rect.width(), rect.height()],
        "items": [_item_to_data(item) for item in reversed(top_level)],
    }


def restore_scene(
    scene: QGraphicsScene, data: dict[str, Any], undo_stack: QUndoStack
) -> None:
    scene.clear()
    retained: list[QGraphicsItem] = []
    for item_data in data.get("items", []):
        item = _item_from_data(item_data, undo_stack, top_level=True)
        scene.addItem(item)
        retained.extend([item, *item.childItems()])
    rect = data.get("rect", [0, 0, 1000, 600])
    scene.setSceneRect(QRectF(*rect))
    scene._pole_route_item_refs = retained


def _item_to_data(item: QGraphicsItem) -> dict[str, Any]:
    common = {
        "pos": [item.pos().x(), item.pos().y()],
        "rotation": item.rotation(),
        "z": item.zValue(),
        "visible": item.isVisible(),
        "data": {str(index): _json_value(item.data(index)) for index in range(7)},
    }
    if isinstance(item, QGraphicsItemGroup):
        return {"kind": "group", **common, "children": [_item_to_data(x) for x in item.childItems()]}
    if isinstance(item, QGraphicsPathItem):
        path = item.path()
        elements = []
        for index in range(path.elementCount()):
            element = path.elementAt(index)
            elements.append([int(element.type.value), element.x, element.y])
        return {"kind": "path", **common, "path": elements, "pen": _pen_data(item.pen())}
    if isinstance(item, QGraphicsLineItem):
        line = item.line()
        return {
            "kind": "line", **common,
            "line": [line.x1(), line.y1(), line.x2(), line.y2()],
            "pen": _pen_data(item.pen()),
        }
    if isinstance(item, QGraphicsSimpleTextItem):
        font = item.font()
        return {
            "kind": "text", **common, "text": item.text(),
            "brush": _brush_data(item.brush()),
            "font": [font.family(), font.pointSizeF(), font.bold(), font.italic()],
        }
    if isinstance(item, QGraphicsTextItem):
        font = item.font()
        return {
            "kind": "document_text",
            **common,
            "text": item.toPlainText(),
            "color": item.defaultTextColor().name(QColor.NameFormat.HexArgb),
            "font": [font.family(), font.pointSizeF(), font.bold(), font.italic()],
        }
    if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
        rect = item.rect()
        return {
            "kind": "rectangle" if isinstance(item, QGraphicsRectItem) else "ellipse",
            **common,
            "rect": [rect.x(), rect.y(), rect.width(), rect.height()],
            "pen": _pen_data(item.pen()),
            "brush": _brush_data(item.brush()),
        }
    raise ProjectFileError(f"Unsupported canvas object: {type(item).__name__}")


def _item_from_data(
    data: dict[str, Any], undo_stack: QUndoStack, *, top_level: bool = False
) -> QGraphicsItem:
    kind = data["kind"]
    if kind == "group":
        item = EditableItemGroup(undo_stack) if top_level else QGraphicsItemGroup()
        for child_data in data.get("children", []):
            item.addToGroup(_item_from_data(child_data, undo_stack))
    elif kind == "path":
        path = QPainterPath()
        for element_type, x, y in data["path"]:
            if element_type == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        item = QGraphicsPathItem(path)
        item.setPen(_pen_from_data(data["pen"]))
    elif kind == "line":
        item = (
            EditableLineItem(QLineF(*data["line"]), undo_stack=undo_stack)
            if top_level
            else QGraphicsLineItem(QLineF(*data["line"]))
        )
        item.setPen(_pen_from_data(data["pen"]))
    elif kind == "text":
        item = (
            EditableTextItem(data["text"], undo_stack)
            if top_level
            else QGraphicsSimpleTextItem(data["text"])
        )
        item.setBrush(_brush_from_data(data["brush"]))
        family, size, bold, italic = data["font"]
        font = QFont(family)
        font.setPointSizeF(size)
        font.setBold(bold)
        font.setItalic(italic)
        item.setFont(font)
    elif kind == "document_text":
        item = QGraphicsTextItem(data["text"])
        item.setDefaultTextColor(QColor(data["color"]))
        family, size, bold, italic = data["font"]
        font = QFont(family)
        font.setPointSizeF(size)
        font.setBold(bold)
        font.setItalic(italic)
        item.setFont(font)
    elif kind in {"rectangle", "ellipse"}:
        rect = QRectF(*data["rect"])
        if kind == "rectangle":
            item = EditableRectItem(rect, undo_stack=undo_stack) if top_level else QGraphicsRectItem(rect)
        else:
            item = EditableEllipseItem(rect, undo_stack=undo_stack) if top_level else QGraphicsEllipseItem(rect)
        item.setPen(_pen_from_data(data["pen"]))
        item.setBrush(_brush_from_data(data["brush"]))
    else:
        raise ProjectFileError(f"Unsupported saved canvas object: {kind}")

    item.setPos(QPointF(*data.get("pos", [0, 0])))
    item.setRotation(float(data.get("rotation", 0)))
    item.setZValue(float(data.get("z", 0)))
    item.setVisible(data.get("visible", True))
    for key, value in data.get("data", {}).items():
        item.setData(int(key), _qt_value(value))
    if top_level:
        item.setFlags(EDITABLE_FLAGS)
    return item


def _pen_data(pen: QPen) -> list[Any]:
    return [pen.color().name(QColor.NameFormat.HexArgb), pen.widthF(), int(pen.style().value)]


def _pen_from_data(data: list[Any]) -> QPen:
    return QPen(QColor(data[0]), float(data[1]), Qt.PenStyle(data[2]))


def _brush_data(brush: QBrush) -> list[Any]:
    return [brush.color().name(QColor.NameFormat.HexArgb), int(brush.style().value)]


def _brush_from_data(data: list[Any]) -> QBrush:
    return QBrush(QColor(data[0]), Qt.BrushStyle(data[1]))


def _json_value(value: Any) -> Any:
    if isinstance(value, QPointF):
        return {"$point": [value.x(), value.y()]}
    if isinstance(value, tuple):
        return {"$tuple": list(value)}
    return value


def _qt_value(value: Any) -> Any:
    if isinstance(value, dict) and "$point" in value:
        return QPointF(*value["$point"])
    if isinstance(value, dict) and "$tuple" in value:
        return tuple(value["$tuple"])
    return value
