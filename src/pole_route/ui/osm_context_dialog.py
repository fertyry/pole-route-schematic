"""Review OpenStreetMap surroundings before adding them to a project."""

from functools import partial

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
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

from pole_route.domain.context import (
    ContextFeature,
    FetchCoverageStatus,
    OSMContext,
    OSMFeatureCategory,
    OSMGeometryKind,
)
from pole_route.domain.route import ClassifiedRoute, Route, RouteType
from pole_route.ui.scene_lifecycle import clear_scene

_CATEGORY_LABELS = {
    OSMFeatureCategory.ROAD_BRIDGE: "Road Bridge",
    OSMFeatureCategory.FOOTBRIDGE: "Footbridge",
    OSMFeatureCategory.RIVER: "River",
    OSMFeatureCategory.CANAL: "Canal",
    OSMFeatureCategory.BUILDING: "Building",
    OSMFeatureCategory.FUEL: "Fuel",
    OSMFeatureCategory.SHOP: "Shop",
    OSMFeatureCategory.POI: "POI",
}
_CATEGORY_COLORS = {
    OSMFeatureCategory.ROAD_BRIDGE: QColor("#9b51e0"),
    OSMFeatureCategory.FOOTBRIDGE: QColor("#bb6bd9"),
    OSMFeatureCategory.RIVER: QColor("#2d9cdb"),
    OSMFeatureCategory.CANAL: QColor("#56ccf2"),
    OSMFeatureCategory.BUILDING: QColor("#828282"),
    OSMFeatureCategory.FUEL: QColor("#eb5757"),
    OSMFeatureCategory.SHOP: QColor("#f2994a"),
    OSMFeatureCategory.POI: QColor("#f2c94c"),
}


class OSMContextDialog(QDialog):
    """Require explicit confirmation for discovered roads and OSM features."""

    def __init__(self, main_route: Route, context: OSMContext, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review surroundings")
        self.resize(1120, 800)
        self._main_route = main_route
        self._context = context
        self.feature_tables: dict[OSMFeatureCategory, QTableWidget] = {}
        self.category_toggles: dict[OSMFeatureCategory, QCheckBox] = {}

        intro = QLabel(
            "OpenStreetMap is the primary context source; Overture may supplement missing "
            "building footprints and useful landmarks. Review each category and confirm only the surroundings "
            "to add. Data © OpenStreetMap contributors and Overture Maps Foundation."
        )
        intro.setWordWrap(True)
        coverage_text = _coverage_summary(context)
        self.coverage_status = QLabel(coverage_text)
        self.coverage_status.setWordWrap(True)
        if coverage_text.startswith(("PARTIAL DATA", "FAILED DATA")):
            self.coverage_status.setStyleSheet(
                "QLabel { background: #fff3cd; color: #664d03; padding: 8px; "
                "border: 1px solid #ffecb5; }"
            )
        self.tabs = QTabWidget()
        bulk_controls = QHBoxLayout()
        self.select_all_categories_button = QPushButton("Select All Categories")
        self.select_all_categories_button.clicked.connect(
            lambda: self._set_all_categories(True)
        )
        self.clear_all_categories_button = QPushButton("Clear All Categories")
        self.clear_all_categories_button.clicked.connect(
            lambda: self._set_all_categories(False)
        )
        self.select_all_recommended_button = QPushButton("Select Recommended")
        self.select_all_recommended_button.clicked.connect(self._select_all_recommended)
        bulk_controls.addWidget(self.select_all_categories_button)
        bulk_controls.addWidget(self.clear_all_categories_button)
        bulk_controls.addWidget(self.select_all_recommended_button)
        bulk_controls.addStretch(1)
        self._add_roads_tab()
        for category in OSMFeatureCategory:
            self._add_feature_tab(category)

        self.scene = QGraphicsScene(self)
        self.preview = QGraphicsView(self.scene)
        self.preview.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.preview.setMinimumHeight(300)
        _draw_context_preview(self.scene, main_route, context, 1040, 300)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add selected surroundings")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        if coverage_text:
            layout.addWidget(self.coverage_status)
        layout.addLayout(bulk_controls)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(QLabel(
            "Preview: blue Main route, grey roads/sois, coloured OSM feature categories"
        ))
        layout.addWidget(self.preview)
        layout.addWidget(buttons)

    def _add_roads_tab(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        self.roads_table = QTableWidget(len(self._context.roads), 5)
        self.roads_table.setHorizontalHeaderLabels(
            ["Use", "Road / Soi", "OSM type", "Width", "Recommendation"]
        )
        for row, road in enumerate(self._context.roads):
            self.roads_table.setItem(row, 0, _check_item(road.recommended))
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
        controls = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_roads(True))
        self.clear_all_button = QPushButton("Clear all")
        self.clear_all_button.clicked.connect(lambda: self._set_all_roads(False))
        controls.addWidget(self.select_all_button)
        controls.addWidget(self.clear_all_button)
        controls.addStretch(1)
        page_layout.addLayout(controls)
        page_layout.addWidget(self.roads_table)
        self.tabs.addTab(page, f"Roads / Sois ({len(self._context.roads)})")

    def _add_feature_tab(self, category: OSMFeatureCategory) -> None:
        candidates = [item for item in self._context.features if item.category is category]
        page = QWidget()
        page_layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        master = QCheckBox(f"Select all {_CATEGORY_LABELS[category]}")
        master.toggled.connect(partial(self._set_feature_category, category))
        self.category_toggles[category] = master
        recommended = QPushButton("Select Recommended")
        recommended.clicked.connect(partial(self._select_recommended, category))
        clear = QPushButton("Clear Selection")
        clear.clicked.connect(partial(self._set_feature_category, category, False))
        controls.addWidget(master)
        controls.addWidget(recommended)
        controls.addWidget(clear)
        controls.addStretch(1)
        page_layout.addLayout(controls)

        table = QTableWidget(len(candidates), 8)
        table.setHorizontalHeaderLabels(
            ["Use", "Name", "Category", "Source", "Source ID", "Geometry", "Status", "Match"]
        )
        for row, feature in enumerate(candidates):
            table.setItem(row, 0, _check_item(False))
            table.setItem(row, 1, QTableWidgetItem(_feature_display_name(feature)))
            table.setItem(row, 2, QTableWidgetItem(_CATEGORY_LABELS[category]))
            table.setItem(row, 3, QTableWidgetItem(_feature_source(feature)))
            table.setItem(row, 4, QTableWidgetItem(feature.source_id))
            table.setItem(row, 5, QTableWidgetItem(feature.render_geometry_kind.value))
            table.setItem(row, 6, QTableWidgetItem(feature.recommendation))
            table.setItem(row, 7, QTableWidgetItem(feature.conflation_status))
        table.resizeColumnsToContents()
        table.itemChanged.connect(partial(self._sync_category_toggle, category))
        self.feature_tables[category] = table
        page_layout.addWidget(table)
        self.tabs.addTab(page, f"{_CATEGORY_LABELS[category]} ({len(candidates)})")

    def selected_routes(self) -> list[ClassifiedRoute]:
        selected = []
        for row, road in enumerate(self._context.roads):
            if self.roads_table.item(row, 0).checkState() != Qt.CheckState.Checked:
                continue
            selected.append(ClassifiedRoute(
                road.route, RouteType.ROAD,
                self.roads_table.cellWidget(row, 3).value(), None, False,
            ))
        return selected

    def selected_features(self) -> list[ContextFeature]:
        selected: list[ContextFeature] = []
        rows = {category: 0 for category in OSMFeatureCategory}
        for feature in self._context.features:
            row = rows[feature.category]
            rows[feature.category] += 1
            if self.feature_tables[feature.category].item(row, 0).checkState() == Qt.CheckState.Checked:
                selected.append(feature)
        return selected

    def _set_all_roads(self, selected: bool) -> None:
        state = Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked
        for row in range(self.roads_table.rowCount()):
            self.roads_table.item(row, 0).setCheckState(state)

    def _set_all_categories(self, selected: bool) -> None:
        self._set_all_roads(selected)
        for category in OSMFeatureCategory:
            self._set_feature_category(category, selected)

    def _select_all_recommended(self) -> None:
        for row, road in enumerate(self._context.roads):
            self.roads_table.item(row, 0).setCheckState(
                Qt.CheckState.Checked if road.recommended else Qt.CheckState.Unchecked
            )
        for category in OSMFeatureCategory:
            self._select_recommended(category)

    def _set_feature_category(self, category: OSMFeatureCategory, selected: bool) -> None:
        table = self.feature_tables[category]
        state = Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked
        table.blockSignals(True)
        try:
            for row in range(table.rowCount()):
                table.item(row, 0).setCheckState(state)
        finally:
            table.blockSignals(False)
        toggle = self.category_toggles[category]
        toggle.blockSignals(True)
        toggle.setChecked(selected and table.rowCount() > 0)
        toggle.blockSignals(False)

    def _select_recommended(self, category: OSMFeatureCategory) -> None:
        table = self.feature_tables[category]
        candidates = [item for item in self._context.features if item.category is category]
        table.blockSignals(True)
        try:
            for row, feature in enumerate(candidates):
                table.item(row, 0).setCheckState(
                    Qt.CheckState.Checked if feature.recommended else Qt.CheckState.Unchecked
                )
        finally:
            table.blockSignals(False)
        self._sync_category_toggle(category)

    def _sync_category_toggle(self, category: OSMFeatureCategory, *_args) -> None:
        table = self.feature_tables[category]
        all_selected = table.rowCount() > 0 and all(
            table.item(row, 0).checkState() == Qt.CheckState.Checked
            for row in range(table.rowCount())
        )
        toggle = self.category_toggles[category]
        toggle.blockSignals(True)
        toggle.setChecked(all_selected)
        toggle.blockSignals(False)


def _check_item(checked: bool) -> QTableWidgetItem:
    item = QTableWidgetItem()
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    return item


def _feature_display_name(feature: ContextFeature) -> str:
    if feature.name:
        return feature.name
    if feature.osm_type and feature.osm_id > 0:
        return f"{_CATEGORY_LABELS[feature.category]} — {feature.osm_type}/{feature.osm_id}"
    return f"Unnamed {_CATEGORY_LABELS[feature.category]}"


def _feature_source(feature: ContextFeature) -> str:
    sources = {feature.source, *(item.source for item in feature.provenance)}
    sources.discard("")
    if "OpenStreetMap" in sources and "Overture" in sources:
        return "OSM + Overture"
    if feature.source == "OpenStreetMap":
        return "OSM"
    return feature.source or "Unknown"


def _coverage_summary(context: OSMContext) -> str:
    if not context.coverage:
        return ""
    failed = [
        item for item in context.coverage
        if item.status is FetchCoverageStatus.FAILED
    ]
    if not failed:
        providers = sorted({item.provider for item in context.coverage})
        return "COMPLETE DATA\n" + "\n".join(f"{provider}: complete" for provider in providers)
    providers = sorted({item.provider for item in context.coverage})
    successful_providers = {
        item.provider for item in context.coverage
        if item.status is FetchCoverageStatus.SUCCESS
    }
    heading = "PARTIAL DATA" if successful_providers else "FAILED DATA"
    lines = [heading]
    for provider in providers:
        unresolved = [item for item in failed if item.provider == provider]
        if not unresolved:
            lines.append(f"{provider}: complete")
            continue
        intervals = ", ".join(
            f"{item.station_start:.0f}-{item.station_end:.0f} m" for item in unresolved
        )
        lines.append(f"{provider}: unresolved {intervals}")
    return "\n".join(lines)


def _draw_context_preview(
    scene: QGraphicsScene, main_route: Route, context: OSMContext,
    width: float, height: float,
) -> None:
    clear_scene(scene)
    margin = 24.0
    points = list(main_route.points)
    points.extend(point for road in context.roads for point in road.route.points)
    points.extend(place.point for place in context.places)
    points.extend(
        point for feature in context.features for part in feature.render_parts
        for point in (*part.coordinates, *(p for hole in part.holes for p in hole))
    )
    min_lon = min(point.longitude for point in points)
    max_lon = max(point.longitude for point in points)
    min_lat = min(point.latitude for point in points)
    max_lat = max(point.latitude for point in points)
    span_x = max(max_lon - min_lon, 1e-12)
    span_y = max(max_lat - min_lat, 1e-12)
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)

    def project(point):
        return (margin + (point.longitude - min_lon) * scale,
                margin + (max_lat - point.latitude) * scale)

    def make_path(coordinates) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(*project(coordinates[0]))
        for point in coordinates[1:]:
            path.lineTo(*project(point))
        return path

    for road in context.roads:
        scene.addPath(make_path(road.route.points), QPen(QColor("#bdbdbd"), 1.5))
    for feature in context.features:
        color = _CATEGORY_COLORS[feature.category]
        for part in feature.render_parts:
            if feature.render_geometry_kind is OSMGeometryKind.POINT:
                x, y = project(part.coordinates[0])
                scene.addEllipse(x - 4, y - 4, 8, 8, QPen(color), QBrush(color))
                continue
            path = make_path(part.coordinates)
            if feature.render_geometry_kind in {OSMGeometryKind.POLYGON, OSMGeometryKind.MULTIPOLYGON}:
                path.setFillRule(Qt.FillRule.OddEvenFill)
                for hole in part.holes:
                    path.addPath(make_path(hole))
                fill = QColor(color)
                fill.setAlpha(55)
                scene.addPath(path, QPen(color, 1.5), QBrush(fill))
            else:
                scene.addPath(path, QPen(color, 2.0))
    scene.addPath(make_path(main_route.points), QPen(QColor("#2f80ed"), 4.0))
    for place in context.places:
        x, y = project(place.point)
        scene.addEllipse(x - 3, y - 3, 6, 6, QPen(QColor("#f2994a")), QBrush(QColor("#f2994a")))
        label = scene.addText(place.name)
        label.setDefaultTextColor(QColor("#f2994a"))
        label.setPos(x + 5, y - 10)
    scene.setSceneRect(0, 0, width, height)
