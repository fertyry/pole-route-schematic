"""Portable JSON project files for PoleRoute Schematic."""

from __future__ import annotations

import json
import os
import tempfile
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

from pole_route.domain.context import (
    ContextFeature,
    ContextGeometryPart,
    ContextPlace,
    ContextRoad,
    FeatureProvenance,
    FetchCoverage,
    FetchCoverageStatus,
    OSMContext,
    OSMFeatureCategory,
    OSMGeometryKind,
)
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import (
    PEAPoleOrdering,
    PEAPoleReviewEntry,
    PoleQCStatus,
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
from pole_route.ui.scene_lifecycle import clear_scene, retain_scene_items
from pole_route.ui.schematic_renderer import EDITABLE_FLAGS

PROJECT_VERSION = 1


class ProjectFileError(RuntimeError):
    """Raised when a project cannot be saved or opened."""


def save_project_file(path: str | Path, payload: dict[str, Any]) -> None:
    document = {"format": "PoleRoute Schematic", "version": PROJECT_VERSION, **payload}
    destination = Path(path)
    temporary_path: Path | None = None
    try:
        serialized = json.dumps(document, ensure_ascii=False, indent=2)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    except (OSError, TypeError, ValueError) as error:
        raise ProjectFileError(f"Project could not be saved: {error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                # The destination has already been replaced successfully, or
                # the original save error is more useful than cleanup failure.
                pass


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
    # OSM Surround V2 is an additive field. Projects written before Phase 2.1
    # remain valid and expose an empty feature collection to callers.
    document.setdefault("osm_features", [])
    document.setdefault("surrounding_candidates", None)
    document.setdefault("pea_poles", [])
    document.setdefault("pea_pole_ordering", None)
    return document


def osm_context_to_data(context: OSMContext | None) -> dict[str, Any] | None:
    """Serialize the last fetched candidates independently of accepted context."""

    if context is None:
        return None
    return {
        "roads": [
            {
                "route": routes_to_data([ClassifiedRoute(
                    road.route, RouteType.ROAD, road.suggested_width_metres, None, False
                )])[0],
                "highway": road.highway,
                "suggested_width_metres": road.suggested_width_metres,
                "recommended": road.recommended,
                "recommendation": road.recommendation,
            }
            for road in context.roads
        ],
        "places": [
            {
                "name": place.name,
                "category": place.category,
                "point": [place.point.longitude, place.point.latitude, place.point.altitude],
            }
            for place in context.places
        ],
        "features": osm_features_to_data(context.features),
        "warnings": list(context.warnings),
        "metrics": [[key, value] for key, value in context.metrics],
        "coverage": [
            {
                "provider": item.provider,
                "station_start": item.station_start,
                "station_end": item.station_end,
                "status": item.status.value,
                "split_depth": item.split_depth,
                "attempts": item.attempts,
                "retries": item.retries,
                "failure_reason": item.failure_reason,
            }
            for item in context.coverage
        ],
    }


def osm_context_from_data(data: dict[str, Any] | None) -> OSMContext | None:
    """Restore fetched candidates; missing data keeps legacy projects compatible."""

    if not data:
        return None
    roads = []
    for item in data.get("roads", []):
        [classified] = routes_from_data([item["route"]])
        roads.append(ContextRoad(
            classified.route,
            str(item.get("highway", "")),
            float(item.get("suggested_width_metres", classified.width_metres or 6.0)),
            bool(item.get("recommended", True)),
            str(item.get("recommendation", "Connects to the Main route")),
        ))
    places = tuple(
        ContextPlace(
            str(item["name"]), str(item.get("category", "")), GeoPoint(*item["point"])
        )
        for item in data.get("places", [])
    )
    return OSMContext(
        tuple(roads), places,
        tuple(osm_features_from_data(data.get("features", []))),
        tuple(str(item) for item in data.get("warnings", [])),
        tuple((str(key), float(value)) for key, value in data.get("metrics", [])),
        tuple(
            FetchCoverage(
                provider=str(item["provider"]),
                station_start=float(item["station_start"]),
                station_end=float(item["station_end"]),
                status=FetchCoverageStatus(item["status"]),
                split_depth=int(item.get("split_depth", 0)),
                attempts=int(item.get("attempts", 1)),
                retries=int(item.get("retries", 0)),
                failure_reason=str(item.get("failure_reason", "")),
            )
            for item in data.get("coverage", [])
        ),
    )


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


def osm_features_to_data(
    features: list[ContextFeature] | tuple[ContextFeature, ...],
) -> list[dict[str, Any]]:
    """Convert portable OSM features to their JSON-compatible project shape."""

    return [
        {
            "osm_type": feature.osm_type,
            "osm_id": feature.osm_id,
            "category": feature.category.value,
            "geometry_kind": feature.geometry_kind.value,
            "parts": [
                {
                    "coordinates": [_geopoint_to_data(point) for point in part.coordinates],
                    "holes": [
                        [_geopoint_to_data(point) for point in ring]
                        for ring in part.holes
                    ],
                }
                for part in feature.parts
            ],
            "name": feature.name,
            "tags": {key: value for key, value in feature.tags},
            "recommended": feature.recommended,
            "recommendation": feature.recommendation,
            "source_path": feature.source_path,
            "source": feature.source,
            "source_id": feature.source_id,
            "source_release": feature.source_release,
            "source_version": feature.source_version,
            "provider": feature.provider,
            "dataset": feature.dataset,
            "resource": feature.resource,
            "record_id": feature.record_id,
            "update_time": feature.update_time,
            "confidence": feature.confidence,
            "source_license": feature.source_license,
            "provenance": [
                {
                    "source": item.source,
                    "source_id": item.source_id,
                    "provider": item.provider,
                    "dataset": item.dataset,
                    "resource": item.resource,
                    "record_id": item.record_id,
                    "release": item.release,
                    "version": item.version,
                    "update_time": item.update_time,
                    "confidence": item.confidence,
                    "license": item.license,
                }
                for item in feature.provenance
            ],
            "conflation_status": feature.conflation_status,
            "matched_source_ids": list(feature.matched_source_ids),
            "display_geometry_kind": (
                feature.display_geometry_kind.value
                if feature.display_geometry_kind is not None else None
            ),
            "display_parts": [
                {
                    "coordinates": [_geopoint_to_data(point) for point in part.coordinates],
                    "holes": [[_geopoint_to_data(point) for point in ring] for ring in part.holes],
                }
                for part in feature.display_parts
            ],
            "crosses_category": (
                feature.crosses_category.value if feature.crosses_category is not None else None
            ),
            "crosses_feature_key": feature.crosses_feature_key,
            "crosses_source_id": feature.crosses_source_id,
            "crosses_name": feature.crosses_name,
        }
        for feature in features
    ]


def osm_features_from_data(data: list[dict[str, Any]]) -> list[ContextFeature]:
    """Restore portable OSM features from project JSON data."""

    return [
        ContextFeature(
            osm_type=str(item["osm_type"]),
            osm_id=int(item["osm_id"]),
            category=OSMFeatureCategory(item["category"]),
            geometry_kind=OSMGeometryKind(item["geometry_kind"]),
            parts=tuple(
                ContextGeometryPart(
                    coordinates=tuple(
                        _geopoint_from_data(point) for point in part["coordinates"]
                    ),
                    holes=tuple(
                        tuple(_geopoint_from_data(point) for point in ring)
                        for ring in part.get("holes", [])
                    ),
                )
                for part in item["parts"]
            ),
            name=item.get("name"),
            tags=tuple(
                (str(key), str(value))
                for key, value in (item.get("tags") or {}).items()
            ),
            recommended=bool(item.get("recommended", True)),
            recommendation=str(item.get("recommendation", "")),
            source_path=str(item.get("source_path", "")),
            source=str(item.get("source", "")),
            source_id=str(item.get("source_id", "")),
            source_release=str(item.get("source_release", "")),
            source_version=str(item.get("source_version", "")),
            provider=str(item.get("provider", "")),
            dataset=str(item.get("dataset", "")),
            resource=str(item.get("resource", "")),
            record_id=str(item.get("record_id", "")),
            update_time=str(item.get("update_time", "")),
            confidence=(
                float(item["confidence"])
                if item.get("confidence") is not None else None
            ),
            source_license=str(item.get("source_license", "")),
            provenance=tuple(
                FeatureProvenance(
                    source=str(entry["source"]),
                    source_id=str(entry.get("source_id", "")),
                    provider=str(entry.get("provider", "")),
                    dataset=str(entry.get("dataset", "")),
                    resource=str(entry.get("resource", "")),
                    record_id=str(entry.get("record_id", "")),
                    release=str(entry.get("release", "")),
                    version=str(entry.get("version", "")),
                    update_time=str(entry.get("update_time", "")),
                    confidence=(
                        float(entry["confidence"])
                        if entry.get("confidence") is not None else None
                    ),
                    license=str(entry.get("license", "")),
                )
                for entry in item.get("provenance", [])
            ),
            conflation_status=str(item.get("conflation_status", "")),
            matched_source_ids=tuple(
                str(value) for value in item.get("matched_source_ids", [])
            ),
            display_geometry_kind=(
                OSMGeometryKind(item["display_geometry_kind"])
                if item.get("display_geometry_kind") else None
            ),
            display_parts=tuple(
                ContextGeometryPart(
                    coordinates=tuple(
                        _geopoint_from_data(point) for point in part["coordinates"]
                    ),
                    holes=tuple(
                        tuple(_geopoint_from_data(point) for point in ring)
                        for ring in part.get("holes", [])
                    ),
                )
                for part in item.get("display_parts", [])
            ),
            crosses_category=(
                OSMFeatureCategory(item["crosses_category"])
                if item.get("crosses_category") else None
            ),
            crosses_feature_key=str(item.get("crosses_feature_key", "")),
            crosses_source_id=str(item.get("crosses_source_id", "")),
            crosses_name=item.get("crosses_name"),
        )
        for item in data
    ]


def _geopoint_to_data(point: GeoPoint) -> list[float | None]:
    return [point.longitude, point.latitude, point.altitude]


def _geopoint_from_data(data: list[float | None]) -> GeoPoint:
    return GeoPoint(*data)


def poles_to_data(poles: list[Pole]) -> list[dict[str, Any]]:
    return [
        {
            "number": pole.number,
            "latitude": pole.latitude,
            "longitude": pole.longitude,
            "detail": pole.detail,
            "side": pole.side.value,
            "installed_quantity": pole.installed_quantity,
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
            int(item.get("installed_quantity", 1)),
        )
        for item in data
    ]


def pea_poles_to_data(records: list[PEAPoleRecord]) -> list[dict[str, Any]]:
    """Serialize source-preserving DS_Pole records additively in schema v1."""
    return [
        {
            "source_id": record.source_id,
            "source_sheet": record.source_sheet,
            "source_row": record.source_row,
            "latitude": record.latitude,
            "longitude": record.longitude,
            "raw_height": record.raw_height,
            "height_metres": record.height_metres,
            "raw_voltage": record.raw_voltage,
            "voltage_min_kv": record.voltage_min_kv,
            "voltage_max_kv": record.voltage_max_kv,
            "raw_attributes": dict(record.raw_attributes),
            "included_by_default": record.included_by_default,
            "qc_warnings": list(record.qc_warnings),
        }
        for record in records
    ]


def pea_poles_from_data(data: list[dict[str, Any]]) -> list[PEAPoleRecord]:
    return [
        PEAPoleRecord(
            source_id=str(item["source_id"]),
            source_sheet=str(item["source_sheet"]),
            source_row=int(item["source_row"]),
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            raw_height=item.get("raw_height"),
            height_metres=(
                float(item["height_metres"]) if item.get("height_metres") is not None else None
            ),
            raw_voltage=item.get("raw_voltage"),
            voltage_min_kv=(
                float(item["voltage_min_kv"])
                if item.get("voltage_min_kv") is not None else None
            ),
            voltage_max_kv=(
                float(item["voltage_max_kv"])
                if item.get("voltage_max_kv") is not None else None
            ),
            raw_attributes=dict(item.get("raw_attributes", {})),
            included_by_default=bool(item.get("included_by_default", False)),
            qc_warnings=tuple(str(value) for value in item.get("qc_warnings", [])),
        )
        for item in data
    ]


def pea_pole_ordering_to_data(ordering: PEAPoleOrdering | None) -> dict[str, Any] | None:
    if ordering is None:
        return None
    return {
        "schema_version": 1,
        "direction_reversed": ordering.direction_reversed,
        "manual_override": ordering.manual_override,
        "confirmed": ordering.confirmed,
        "entries": [
            {
                "source_key": entry.source_key,
                "source_id": entry.source_id,
                "station_metres": entry.station_metres,
                "offset_metres": entry.offset_metres,
                "projected_latitude": entry.projected_latitude,
                "projected_longitude": entry.projected_longitude,
                "auto_order": entry.auto_order,
                "review_order": entry.review_order,
                "confirmed_order": entry.confirmed_order,
                "included": entry.included,
                "qc_status": entry.qc_status.value,
                "qc_reasons": list(entry.qc_reasons),
            }
            for entry in ordering.entries
        ],
    }


def pea_pole_ordering_from_data(data: dict[str, Any] | None) -> PEAPoleOrdering | None:
    if not data:
        return None
    return PEAPoleOrdering(
        entries=tuple(
            PEAPoleReviewEntry(
                source_key=str(item["source_key"]),
                source_id=str(item["source_id"]),
                station_metres=float(item["station_metres"]),
                offset_metres=float(item["offset_metres"]),
                projected_latitude=float(item["projected_latitude"]),
                projected_longitude=float(item["projected_longitude"]),
                auto_order=(int(item["auto_order"]) if item.get("auto_order") is not None else None),
                review_order=(int(item["review_order"]) if item.get("review_order") is not None else None),
                confirmed_order=(
                    int(item["confirmed_order"])
                    if item.get("confirmed_order") is not None else None
                ),
                included=bool(item.get("included", False)),
                qc_status=PoleQCStatus(item.get("qc_status", PoleQCStatus.NORMAL.value)),
                qc_reasons=tuple(str(value) for value in item.get("qc_reasons", [])),
            )
            for item in data.get("entries", [])
        ),
        direction_reversed=bool(data.get("direction_reversed", False)),
        manual_override=bool(data.get("manual_override", False)),
        confirmed=bool(data.get("confirmed", False)),
    )


def scene_to_data(scene: QGraphicsScene) -> dict[str, Any]:
    """Serialize the exact editable scene hierarchy without rasterizing it."""
    # scene.items() may create the only live Python wrappers for C++ items. If
    # those temporary wrappers are collected when Save returns, PySide can also
    # remove their graphics objects from the live scene. Retain the same wrappers
    # after this read-only traversal; clear_scene() releases them before any later
    # intentional scene replacement.
    items = scene.items()
    try:
        top_level = [item for item in items if item.parentItem() is None]
        rect = scene.sceneRect()
        return {
            "rect": [rect.x(), rect.y(), rect.width(), rect.height()],
            "items": [_item_to_data(item) for item in reversed(top_level)],
        }
    finally:
        retain_scene_items(scene, items)


def restore_scene(
    scene: QGraphicsScene, data: dict[str, Any], undo_stack: QUndoStack
) -> None:
    clear_scene(scene)
    for item_data in data.get("items", []):
        item = _item_from_data(item_data, undo_stack, top_level=True)
        scene.addItem(item)
    rect = data.get("rect", [0, 0, 1000, 600])
    scene.setSceneRect(QRectF(*rect))
    retain_scene_items(scene)


def _item_to_data(item: QGraphicsItem) -> dict[str, Any]:
    common = {
        "pos": [item.pos().x(), item.pos().y()],
        "rotation": item.rotation(),
        "z": item.zValue(),
        "visible": item.isVisible(),
        "data": {
            str(index): _json_value(item.data(index))
            for index in range(9)
            if item.data(index) is not None
        },
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
