"""Classify and confirm multiple KML/KMZ LineStrings."""

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.domain.route import ClassifiedRoute, Route, RouteType


class RouteImportDialog(QDialog):
    """Assign a type and optional width to each source LineString."""

    def __init__(self, routes: list[Route], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Classify KML LineStrings")
        self.resize(980, 700)
        self._routes = routes

        intro = QLabel(
            "Choose every LineString to import, assign its meaning, and set road widths. "
            "One or more used lines may be Main routes. Pole offset 0 m places the pole "
            "projection line on the road edge; it does not disable pole projection."
        )
        intro.setWordWrap(True)

        self.table = QTableWidget(len(routes), 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Use",
                "LineString",
                "Type",
                "Road width",
                "Create pole line",
                "Pole offset",
                "Reverse",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for row, route in enumerate(routes):
            use_item = QTableWidgetItem()
            use_item.setFlags(use_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            use_item.setCheckState(Qt.CheckState.Checked if row == 0 else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, use_item)
            self.table.setItem(row, 1, QTableWidgetItem(route.name))

            route_type = QComboBox()
            for item_type in RouteType:
                route_type.addItem(item_type.value, item_type.value)
            route_type.setCurrentText(
                RouteType.MAIN_ROUTE.value if row == 0 else RouteType.ROAD.value
            )
            route_type.currentTextChanged.connect(
                lambda _text, selected_row=row: self._update_width_state(selected_row)
            )
            self.table.setCellWidget(row, 2, route_type)

            width = QDoubleSpinBox()
            width.setLocale(QLocale.c())
            width.setRange(0.5, 1000.0)
            width.setDecimals(2)
            width.setSuffix(" m")
            width.setValue(6.0)
            self.table.setCellWidget(row, 3, width)

            create_pole_line = QTableWidgetItem()
            create_pole_line.setFlags(
                create_pole_line.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            create_pole_line.setCheckState(
                Qt.CheckState.Checked if row == 0 else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 4, create_pole_line)

            pole_offset = QDoubleSpinBox()
            pole_offset.setLocale(QLocale.c())
            pole_offset.setRange(0.0, 1000.0)
            pole_offset.setDecimals(2)
            pole_offset.setSuffix(" m")
            pole_offset.setValue(2.0)
            self.table.setCellWidget(row, 5, pole_offset)

            reverse = QTableWidgetItem()
            reverse.setFlags(reverse.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            reverse.setCheckState(Qt.CheckState.Unchecked)
            reverse.setToolTip("Reverse this LineString's START and END before import")
            self.table.setItem(row, 6, reverse)
            self._update_width_state(row)

        self.table.itemChanged.connect(self._handle_item_changed)

        self.details = QLabel()
        self.scene = QGraphicsScene(self)
        self.preview = QGraphicsView(self.scene)
        self.preview.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.preview.setMinimumHeight(300)

        self.preview_all_button = QPushButton("Preview selected routes")
        self.preview_all_button.clicked.connect(self._preview_selected_routes)

        self.table.resizeColumnsToContents()
        self.table.itemSelectionChanged.connect(self._update_preview)
        self.table.selectRow(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm routes")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table)
        layout.addWidget(self.details)
        layout.addWidget(QLabel("Selected LineString preview (geographic shape, not to scale)"))
        layout.addWidget(self.preview, 1)
        buttons.addButton(
            self.preview_all_button,
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        layout.addWidget(buttons)
        self._update_preview()

    def classified_routes(self) -> list[ClassifiedRoute]:
        selections = []
        for row, _source_route in enumerate(self._routes):
            if self.table.item(row, 0).checkState() != Qt.CheckState.Checked:
                continue
            route_type = RouteType(self.table.cellWidget(row, 2).currentData())
            if route_type is RouteType.IGNORE:
                continue
            width = self.table.cellWidget(row, 3)
            width_value = width.value() if width.isEnabled() else None
            create_pole_line = (
                self.table.item(row, 4).checkState() == Qt.CheckState.Checked
            )
            offset = self.table.cellWidget(row, 5)
            offset_value = offset.value() if create_pole_line and offset.isEnabled() else None
            selections.append(
                ClassifiedRoute(
                    self._route_for_row(row),
                    route_type,
                    width_value,
                    offset_value,
                    create_pole_line,
                )
            )
        return selections

    def selected_route(self) -> Route:
        """Compatibility helper returning the confirmed main route."""
        return next(item.route for item in self.classified_routes() if item.type is RouteType.MAIN_ROUTE)

    def _validate_and_accept(self) -> None:
        try:
            selections = self.classified_routes()
        except ValueError as error:
            QMessageBox.warning(self, "Route classification invalid", str(error))
            return
        main_count = sum(item.type is RouteType.MAIN_ROUTE for item in selections)
        if main_count < 1:
            QMessageBox.warning(
                self,
                "Route classification incomplete",
                "Select and use at least one Main route.",
            )
            return
        self.accept()

    def _update_width_state(self, row: int) -> None:
        route_type = RouteType(self.table.cellWidget(row, 2).currentData())
        enabled = route_type in {RouteType.MAIN_ROUTE, RouteType.ROAD, RouteType.BRIDGE}
        self.table.cellWidget(row, 3).setEnabled(enabled)
        self.table.cellWidget(row, 5).setEnabled(
            enabled and self.table.item(row, 4).checkState() == Qt.CheckState.Checked
        )

    def _handle_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 4:
            self._update_width_state(item.row())
        if item.column() == 6 and item.row() == self.table.currentRow():
            self._update_preview()

    def _route_for_row(self, row: int) -> Route:
        route = self._routes[row]
        if self.table.item(row, 6).checkState() != Qt.CheckState.Checked:
            return route
        return Route(route.name, route.source_path, tuple(reversed(route.points)))

    def _update_preview(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        route = self._route_for_row(row)
        first, last = route.points[0], route.points[-1]
        self.details.setText(
            f"{route.name}: {len(route.points)} points | "
            f"Start {first.latitude:.6f}, {first.longitude:.6f} | "
            f"End {last.latitude:.6f}, {last.longitude:.6f}"
        )
        draw_route_preview(self.scene, route, 860, 280, show_direction=True)

    def _preview_selected_routes(self) -> None:
        rows = [
            row
            for row in range(len(self._routes))
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
            and RouteType(self.table.cellWidget(row, 2).currentData()) is not RouteType.IGNORE
        ]
        if not rows:
            QMessageBox.information(self, "Nothing to preview", "Select at least one route to use.")
            return
        routes_with_types = [
            (
                self._route_for_row(row),
                RouteType(self.table.cellWidget(row, 2).currentData()),
            )
            for row in rows
        ]
        draw_classified_routes_preview(self.scene, routes_with_types, 860, 280)
        counts: dict[RouteType, int] = {}
        for _route, route_type in routes_with_types:
            counts[route_type] = counts.get(route_type, 0) + 1
        legend = " | ".join(f"{route_type.value}: {count}" for route_type, count in counts.items())
        self.details.setText(f"Previewing {len(routes_with_types)} selected routes | {legend}")


def draw_route_preview(
    scene: QGraphicsScene,
    route: Route,
    width: float,
    height: float,
    *,
    show_direction: bool = False,
) -> None:
    scene.clear()
    margin = 24.0
    longitudes = [point.longitude for point in route.points]
    latitudes = [point.latitude for point in route.points]
    span_x = max(max(longitudes) - min(longitudes), 1e-12)
    span_y = max(max(latitudes) - min(latitudes), 1e-12)
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)

    def project(point):
        return (
            margin + (point.longitude - min(longitudes)) * scale,
            margin + (max(latitudes) - point.latitude) * scale,
        )

    path = QPainterPath()
    path.moveTo(*project(route.points[0]))
    for point in route.points[1:]:
        path.lineTo(*project(point))
    scene.addPath(path, QPen(QColor("#2f80ed"), 3.0))
    if show_direction:
        _add_direction_labels(scene, project(route.points[0]), project(route.points[-1]))
    scene.setSceneRect(0, 0, width, height)


ROUTE_TYPE_COLORS = {
    RouteType.MAIN_ROUTE: QColor("#2f80ed"),
    RouteType.ROAD: QColor("#bdbdbd"),
    RouteType.BRIDGE: QColor("#f2c94c"),
    RouteType.FOOTBRIDGE: QColor("#f2994a"),
    RouteType.CANAL: QColor("#56ccf2"),
    RouteType.RAILWAY: QColor("#a67c52"),
    RouteType.REFERENCE: QColor("#9b51e0"),
}


def draw_classified_routes_preview(
    scene: QGraphicsScene,
    routes_with_types: list[tuple[Route, RouteType]],
    width: float,
    height: float,
) -> None:
    """Fit and draw all selected routes in one shared geographic preview."""
    scene.clear()
    margin = 24.0
    points = [point for route, _route_type in routes_with_types for point in route.points]
    min_longitude = min(point.longitude for point in points)
    max_longitude = max(point.longitude for point in points)
    min_latitude = min(point.latitude for point in points)
    max_latitude = max(point.latitude for point in points)
    span_x = max(max_longitude - min_longitude, 1e-12)
    span_y = max(max_latitude - min_latitude, 1e-12)
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)

    def project(point):
        return (
            margin + (point.longitude - min_longitude) * scale,
            margin + (max_latitude - point.latitude) * scale,
        )

    for route, route_type in routes_with_types:
        path = QPainterPath()
        path.moveTo(*project(route.points[0]))
        for point in route.points[1:]:
            path.lineTo(*project(point))
        thickness = 4.0 if route_type is RouteType.MAIN_ROUTE else 2.5
        scene.addPath(path, QPen(ROUTE_TYPE_COLORS[route_type], thickness))
        if route_type is RouteType.MAIN_ROUTE:
            _add_direction_labels(scene, project(route.points[0]), project(route.points[-1]))
    scene.setSceneRect(0, 0, width, height)


def _add_direction_labels(scene: QGraphicsScene, start, end) -> None:
    for text, point, color in (
        ("START", start, QColor("#27ae60")),
        ("END", end, QColor("#eb5757")),
    ):
        label = scene.addText(text)
        label.setDefaultTextColor(color)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        label.setPos(point[0] + 5, point[1] - 20)
