"""Render metric road geometry into a Qt graphics scene."""

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsScene
from shapely.geometry import LineString, Point

from pole_route.domain.pole import PoleSide
from pole_route.geometry.road_geometry import RoadGeometry


def render_road_geometry(
    scene: QGraphicsScene,
    geometry: RoadGeometry,
    width: float = 960,
    height: float = 540,
) -> None:
    """Draw scaled metric geometry while preserving its aspect ratio."""
    scene.clear()
    lines = (
        geometry.centerline,
        geometry.left_edge,
        geometry.right_edge,
        geometry.left_pole_line,
        geometry.right_pole_line,
    )
    extra_points = tuple(
        point
        for projected in geometry.projected_poles
        for point in (projected.original, projected.snapped)
    )
    transform = _SceneTransform.from_geometry(lines, extra_points, width, height)

    _draw_line(scene, geometry.left_pole_line, transform, QColor("#f2c94c"), 2, dashed=True)
    _draw_line(scene, geometry.right_pole_line, transform, QColor("#f2c94c"), 2, dashed=True)
    _draw_line(scene, geometry.left_edge, transform, QColor("#bdbdbd"), 2)
    _draw_line(scene, geometry.right_edge, transform, QColor("#bdbdbd"), 2)
    _draw_line(scene, geometry.centerline, transform, QColor("#2f80ed"), 2, dashed=True)

    for projected in geometry.projected_poles:
        original_x, original_y = transform.point(projected.original)
        snapped_x, snapped_y = transform.point(projected.snapped)
        connector = QPen(QColor("#666666"), 1, Qt.PenStyle.DotLine)
        scene.addLine(original_x, original_y, snapped_x, snapped_y, connector)
        scene.addEllipse(
            original_x - 2,
            original_y - 2,
            4,
            4,
            QPen(QColor("#777777")),
            QBrush(QColor("#777777")),
        )
        color = QColor("#27ae60" if projected.pole.side is PoleSide.LEFT else "#eb5757")
        scene.addEllipse(
            snapped_x - 5,
            snapped_y - 5,
            10,
            10,
            QPen(color, 2),
            QBrush(QColor("#202020")),
        )
        label = scene.addText(projected.pole.number)
        label.setDefaultTextColor(color)
        label.setPos(snapped_x + 7, snapped_y - 12)

    scene.setSceneRect(0, 0, width, height)


def _draw_line(
    scene: QGraphicsScene,
    line: LineString,
    transform: "_SceneTransform",
    color: QColor,
    thickness: float,
    dashed: bool = False,
) -> None:
    path = QPainterPath()
    first_x, first_y = transform.xy(*line.coords[0])
    path.moveTo(first_x, first_y)
    for coordinate in line.coords[1:]:
        x, y = transform.xy(*coordinate)
        path.lineTo(x, y)
    style = Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine
    scene.addPath(path, QPen(color, thickness, style))


class _SceneTransform:
    def __init__(self, min_x, max_y, scale, offset_x, offset_y) -> None:
        self.min_x = min_x
        self.max_y = max_y
        self.scale = scale
        self.offset_x = offset_x
        self.offset_y = offset_y

    @classmethod
    def from_geometry(
        cls,
        lines: Iterable[LineString],
        points: Iterable[Point],
        width: float,
        height: float,
    ) -> "_SceneTransform":
        coordinates = [coordinate for line in lines for coordinate in line.coords]
        coordinates.extend((point.x, point.y) for point in points)
        min_x = min(x for x, _ in coordinates)
        max_x = max(x for x, _ in coordinates)
        min_y = min(y for _, y in coordinates)
        max_y = max(y for _, y in coordinates)
        margin = 30.0
        span_x = max(max_x - min_x, 1e-9)
        span_y = max(max_y - min_y, 1e-9)
        scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)
        drawn_width = span_x * scale
        drawn_height = span_y * scale
        offset_x = (width - drawn_width) / 2
        offset_y = (height - drawn_height) / 2
        return cls(min_x, max_y, scale, offset_x, offset_y)

    def xy(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.offset_x + (x - self.min_x) * self.scale,
            self.offset_y + (self.max_y - y) * self.scale,
        )

    def point(self, point: Point) -> tuple[float, float]:
        return self.xy(point.x, point.y)

