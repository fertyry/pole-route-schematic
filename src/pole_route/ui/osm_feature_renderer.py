"""Render accepted OSM features as non-road reference graphics."""

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsScene

from pole_route.domain.context import ContextFeature, OSMFeatureCategory, OSMGeometryKind
from pole_route.domain.route import GeoPoint


FEATURE_COLORS = {
    OSMFeatureCategory.ROAD_BRIDGE: QColor("#f2994a"),
    OSMFeatureCategory.FOOTBRIDGE: QColor("#f2c94c"),
    OSMFeatureCategory.RIVER: QColor("#2d9cdb"),
    OSMFeatureCategory.CANAL: QColor("#56ccf2"),
    OSMFeatureCategory.BUILDING: QColor("#9b9b9b"),
    OSMFeatureCategory.FUEL: QColor("#eb5757"),
    OSMFeatureCategory.SHOP: QColor("#bb6bd9"),
    OSMFeatureCategory.POI: QColor("#6fcf97"),
}


def render_osm_features(
    scene: QGraphicsScene,
    features: Iterable[ContextFeature],
    project: Callable[[GeoPoint], tuple[float, float]],
) -> None:
    """Add portable OSM geometry without clearing or changing road state."""
    for feature in features:
        color = FEATURE_COLORS[feature.category]
        pen = QPen(color, 1.5, Qt.PenStyle.SolidLine)
        anchors: list[tuple[float, float]] = []
        if feature.render_geometry_kind is OSMGeometryKind.POINT:
            for part in feature.render_parts:
                for coordinate in part.coordinates:
                    x, y = project(coordinate)
                    item = scene.addEllipse(x - 5, y - 5, 10, 10, pen, QBrush(color))
                    _tag(item, feature)
                    anchors.append((x, y))
        else:
            for part in feature.render_parts:
                exterior = tuple(project(point) for point in part.coordinates)
                if exterior:
                    item = scene.addPath(
                        _path(exterior, feature.render_geometry_kind in {
                            OSMGeometryKind.POLYGON, OSMGeometryKind.MULTIPOLYGON
                        }), pen
                    )
                    _tag(item, feature)
                    anchors.extend(exterior)
                for hole in part.holes:
                    points = tuple(project(point) for point in hole)
                    if points:
                        item = scene.addPath(_path(points, True), pen)
                        _tag(item, feature)
        if feature.name and anchors:
            x = sum(point[0] for point in anchors) / len(anchors)
            y = sum(point[1] for point in anchors) / len(anchors)
            label = scene.addText(feature.name)
            label.setDefaultTextColor(color)
            label.setPos(x + 4, y + 4)
            _tag(label, feature)


def _path(points: tuple[tuple[float, float], ...], closed: bool) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    if closed:
        path.closeSubpath()
    return path


def _tag(item, feature: ContextFeature) -> None:
    item.setData(0, "osm_feature")
    item.setData(1, f"{feature.osm_type}/{feature.osm_id}")
    item.setData(3, feature.category.value)
    item.setZValue(-10.0)
