"""Route candidate selection and confirmation dialog."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
)

from pole_route.domain.route import Route


class RouteImportDialog(QDialog):
    """Let the user inspect and confirm one LineString candidate."""

    def __init__(self, routes: list[Route], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm road centerline")
        self.resize(760, 540)
        self._routes = routes

        intro = QLabel(
            "Select the KML/KMZ LineString to use as the road centerline, "
            "review its details, then confirm the import."
        )
        intro.setWordWrap(True)

        self.route_selector = QComboBox()
        for index, route in enumerate(routes):
            self.route_selector.addItem(route.name, index)
        self.route_selector.currentIndexChanged.connect(self._update_preview)

        self.details = QLabel()
        self.details.setWordWrap(True)

        self.scene = QGraphicsScene(self)
        self.preview = QGraphicsView(self.scene)
        self.preview.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.preview.setMinimumHeight(320)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm route")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(QLabel("LineString"))
        layout.addWidget(self.route_selector)
        layout.addWidget(self.details)
        layout.addWidget(QLabel("Geographic shape preview (not schematic and not to scale)"))
        layout.addWidget(self.preview, 1)
        layout.addWidget(buttons)
        self._update_preview()

    def selected_route(self) -> Route:
        return self._routes[self.route_selector.currentData()]

    def _update_preview(self) -> None:
        route = self.selected_route()
        first = route.points[0]
        last = route.points[-1]
        self.details.setText(
            f"{len(route.points)} points | "
            f"Start: {first.latitude:.6f}, {first.longitude:.6f} | "
            f"End: {last.latitude:.6f}, {last.longitude:.6f}"
        )
        draw_route_preview(self.scene, route, 680, 300)


def draw_route_preview(scene: QGraphicsScene, route: Route, width: float, height: float) -> None:
    """Draw a fitted geographic-shape preview without spatial calculations."""
    scene.clear()
    margin = 24.0
    longitudes = [point.longitude for point in route.points]
    latitudes = [point.latitude for point in route.points]
    longitude_span = max(max(longitudes) - min(longitudes), 1e-12)
    latitude_span = max(max(latitudes) - min(latitudes), 1e-12)
    scale = min((width - 2 * margin) / longitude_span, (height - 2 * margin) / latitude_span)

    def project(point):
        x = margin + (point.longitude - min(longitudes)) * scale
        y = margin + (max(latitudes) - point.latitude) * scale
        return x, y

    path = QPainterPath()
    start_x, start_y = project(route.points[0])
    path.moveTo(start_x, start_y)
    for point in route.points[1:]:
        x, y = project(point)
        path.lineTo(x, y)
    scene.addPath(path, QPen(QColor("#2f80ed"), 3.0, Qt.PenStyle.SolidLine))
    scene.setSceneRect(0, 0, width, height)
