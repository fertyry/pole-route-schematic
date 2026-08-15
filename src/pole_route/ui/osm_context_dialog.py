"""Review OpenStreetMap roads and landmarks before adding them to a project."""

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pole_route.domain.context import OSMContext
from pole_route.domain.route import ClassifiedRoute, Route, RouteType


class OSMContextDialog(QDialog):
    """Require explicit confirmation for automatically discovered context."""

    def __init__(self, main_route: Route, context: OSMContext, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review surroundings from OpenStreetMap")
        self.resize(1050, 760)
        self._main_route = main_route
        self._context = context

        intro = QLabel(
            "OpenStreetMap suggestions are reference data. Review the roads before adding them; "
            "landmarks are shown for orientation and are not yet added to the schematic. "
            "Named local roads are preselected; major and unnamed roads require manual selection. "
            "Data © OpenStreetMap contributors."
        )
        intro.setWordWrap(True)

        tabs = QTabWidget()
        roads_page = QWidget()
        roads_layout = QVBoxLayout(roads_page)
        self.roads_table = QTableWidget(len(context.roads), 5)
        self.roads_table.setHorizontalHeaderLabels(
            ["Use", "Road / Soi", "OSM type", "Width", "Recommendation"]
        )
        for row, road in enumerate(context.roads):
            use = QTableWidgetItem()
            use.setFlags(use.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            use.setCheckState(
                Qt.CheckState.Checked if road.recommended else Qt.CheckState.Unchecked
            )
            self.roads_table.setItem(row, 0, use)
            self.roads_table.setItem(row, 1, QTableWidgetItem(road.route.name))
            self.roads_table.setItem(row, 2, QTableWidgetItem(road.highway))
            width = QDoubleSpinBox()
            width.setLocale(QLocale.c())
            width.setRange(1.0, 100.0)
            width.setDecimals(2)
            width.setSuffix(" m")
            width.setValue(road.suggested_width_metres)
            self.roads_table.setCellWidget(row, 3, width)
            self.roads_table.setItem(row, 4, QTableWidgetItem(road.recommendation))
        self.roads_table.resizeColumnsToContents()
        selection_buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_roads(True))
        self.clear_all_button = QPushButton("Clear all")
        self.clear_all_button.clicked.connect(lambda: self._set_all_roads(False))
        selection_buttons.addWidget(self.select_all_button)
        selection_buttons.addWidget(self.clear_all_button)
        selection_buttons.addStretch(1)
        roads_layout.addLayout(selection_buttons)
        roads_layout.addWidget(self.roads_table)
        tabs.addTab(roads_page, f"Roads / Sois ({len(context.roads)})")

        places_page = QWidget()
        places_layout = QVBoxLayout(places_page)
        self.places_table = QTableWidget(len(context.places), 2)
        self.places_table.setHorizontalHeaderLabels(["Place", "Category"])
        for row, place in enumerate(context.places):
            self.places_table.setItem(row, 0, QTableWidgetItem(place.name))
            self.places_table.setItem(row, 1, QTableWidgetItem(place.category))
        self.places_table.resizeColumnsToContents()
        places_layout.addWidget(self.places_table)
        tabs.addTab(places_page, f"Named places ({len(context.places)})")

        self.scene = QGraphicsScene(self)
        self.preview = QGraphicsView(self.scene)
        self.preview.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.preview.setMinimumHeight(320)
        _draw_context_preview(self.scene, main_route, context, 980, 320)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add selected surroundings")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(tabs, 1)
        layout.addWidget(QLabel("Preview: blue Main route, grey roads/sois, orange named places"))
        layout.addWidget(self.preview)
        layout.addWidget(buttons)

    def selected_routes(self) -> list[ClassifiedRoute]:
        selected = []
        for row, road in enumerate(self._context.roads):
            if self.roads_table.item(row, 0).checkState() != Qt.CheckState.Checked:
                continue
            selected.append(
                ClassifiedRoute(
                    road.route,
                    RouteType.ROAD,
                    self.roads_table.cellWidget(row, 3).value(),
                    None,
                    False,
                )
            )
        return selected

    def _set_all_roads(self, selected: bool) -> None:
        state = Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked
        for row in range(self.roads_table.rowCount()):
            self.roads_table.item(row, 0).setCheckState(state)


def _draw_context_preview(
    scene: QGraphicsScene,
    main_route: Route,
    context: OSMContext,
    width: float,
    height: float,
) -> None:
    scene.clear()
    margin = 24.0
    points = list(main_route.points)
    points.extend(point for road in context.roads for point in road.route.points)
    points.extend(place.point for place in context.places)
    min_lon = min(point.longitude for point in points)
    max_lon = max(point.longitude for point in points)
    min_lat = min(point.latitude for point in points)
    max_lat = max(point.latitude for point in points)
    span_x = max(max_lon - min_lon, 1e-12)
    span_y = max(max_lat - min_lat, 1e-12)
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)

    def project(point):
        return (
            margin + (point.longitude - min_lon) * scale,
            margin + (max_lat - point.latitude) * scale,
        )

    def add_route(route: Route, color: QColor, thickness: float) -> None:
        path = QPainterPath()
        path.moveTo(*project(route.points[0]))
        for point in route.points[1:]:
            path.lineTo(*project(point))
        scene.addPath(path, QPen(color, thickness))

    for road in context.roads:
        add_route(road.route, QColor("#bdbdbd"), 1.5)
    add_route(main_route, QColor("#2f80ed"), 4.0)
    for place in context.places:
        x, y = project(place.point)
        scene.addEllipse(x - 3, y - 3, 6, 6, QPen(QColor("#f2994a")), QBrush(QColor("#f2994a")))
        label = scene.addText(place.name)
        label.setDefaultTextColor(QColor("#f2994a"))
        label.setPos(x + 5, y - 10)
    scene.setSceneRect(0, 0, width, height)
