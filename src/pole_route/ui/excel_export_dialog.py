"""Editable Excel export settings and page preview."""

from PySide6.QtCore import QLocale, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from pole_route.exporters.excel_exporter import (
    ExcelExportSettings,
    ExcelObject,
    prepare_excel_objects,
    prepare_excel_pages,
)


class ExcelExportDialog(QDialog):
    def __init__(
        self,
        source_objects: list[ExcelObject],
        parent=None,
        initial_settings: ExcelExportSettings | None = None,
    ) -> None:
        super().__init__(parent)
        initial_settings = initial_settings or ExcelExportSettings()
        self.source_objects = list(source_objects)
        self.setWindowTitle("Excel export preview")
        self.resize(1150, 760)
        self._project_title = initial_settings.project_title
        self._location = initial_settings.location
        self._work_description = initial_settings.work_description
        self.prepared_by = QLineEdit(initial_settings.prepared_by)
        self.drawing_number = QLineEdit(initial_settings.drawing_number)
        self.paper_size = QComboBox()
        self.paper_size.addItems(["A4", "A3"])
        self.orientation = QComboBox()
        self.orientation.addItems(["Landscape", "Portrait"])
        self.frame_style = QComboBox()
        self.frame_style.addItem("Standard", "standard")
        self.frame_style.addItem("No frame", "none")
        self.centerline = QComboBox()
        self.centerline.addItem("Thin dashed", "dashed")
        self.centerline.addItem("Hide", "hide")
        self.pole_size = QDoubleSpinBox()
        self.pole_size.setLocale(QLocale.c())
        self.pole_size.setRange(2.0, 10.0)
        self.pole_size.setValue(4.0)
        self.pole_size.setSuffix(" mm")
        self.road_edge_width = QDoubleSpinBox()
        self.road_edge_width.setLocale(QLocale.c())
        self.road_edge_width.setRange(0.25, 5.0)
        self.road_edge_width.setValue(1.0)
        self.road_edge_width.setSuffix(" pt")
        self.centerline_width = QDoubleSpinBox()
        self.centerline_width.setLocale(QLocale.c())
        self.centerline_width.setRange(0.1, 3.0)
        self.centerline_width.setValue(0.4)
        self.centerline_width.setSuffix(" pt")
        self.compass = QCheckBox("Show north arrow")
        self.compass.setChecked(True)
        self.page_count = QSpinBox()
        self.page_count.setLocale(QLocale.c())
        self.page_count.setRange(1, 20)
        self.paper_size.setCurrentText(initial_settings.paper_size)
        self.orientation.setCurrentText(initial_settings.orientation.title())
        self.frame_style.setCurrentIndex(
            max(0, self.frame_style.findData(initial_settings.frame_style))
        )
        self.centerline.setCurrentIndex(
            max(0, self.centerline.findData(initial_settings.centerline_mode))
        )
        self.pole_size.setValue(initial_settings.pole_size_mm)
        self.road_edge_width.setValue(initial_settings.road_edge_width)
        self.centerline_width.setValue(initial_settings.centerline_width)
        self.compass.setChecked(initial_settings.show_compass)
        self.page_count.setValue(initial_settings.page_count)
        self.current_page = 0
        self._refreshing = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self.refresh_preview)

        form = QFormLayout()
        form.addRow("Prepared by", self.prepared_by)
        form.addRow("Drawing number", self.drawing_number)
        form.addRow("Paper size", self.paper_size)
        form.addRow("Orientation", self.orientation)
        form.addRow("Frame", self.frame_style)
        form.addRow("Centerline", self.centerline)
        form.addRow("Road edge width", self.road_edge_width)
        form.addRow("Centerline width", self.centerline_width)
        form.addRow("Pole size", self.pole_size)
        form.addRow("Compass", self.compass)
        form.addRow("Number of sheets", self.page_count)

        self.preview_scene = QGraphicsScene(self)
        self.preview = QGraphicsView(self.preview_scene)
        self.preview.setBackgroundBrush(QBrush(QColor("#777777")))
        self.previous_page = QPushButton("Previous")
        self.next_page = QPushButton("Next")
        self.page_label = QLabel("Sheet 1 / 1")
        page_navigation = QHBoxLayout()
        page_navigation.addWidget(self.previous_page)
        page_navigation.addWidget(self.page_label, 1, Qt.AlignmentFlag.AlignCenter)
        page_navigation.addWidget(self.next_page)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Confirm export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        right = QVBoxLayout()
        right.addLayout(form)
        right.addStretch(1)
        right.addWidget(buttons)
        layout = QHBoxLayout(self)
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(self.preview, 1)
        preview_layout.addLayout(page_navigation)
        layout.addLayout(preview_layout, 3)
        layout.addLayout(right, 1)
        for control in (
            self.prepared_by,
            self.drawing_number,
        ):
            control.textChanged.connect(self.schedule_preview_refresh)
        for control in (self.paper_size, self.orientation, self.frame_style, self.centerline):
            control.currentIndexChanged.connect(self.schedule_preview_refresh)
        self.pole_size.valueChanged.connect(self.schedule_preview_refresh)
        self.road_edge_width.valueChanged.connect(self.schedule_preview_refresh)
        self.centerline_width.valueChanged.connect(self.schedule_preview_refresh)
        self.compass.toggled.connect(self.schedule_preview_refresh)
        self.page_count.valueChanged.connect(self._page_count_changed)
        self.previous_page.clicked.connect(lambda: self._change_page(-1))
        self.next_page.clicked.connect(lambda: self._change_page(1))
        self.refresh_preview()

    def settings(self) -> ExcelExportSettings:
        return ExcelExportSettings(
            project_title=self._project_title,
            location=self._location,
            prepared_by=self.prepared_by.text().strip(),
            drawing_number=self.drawing_number.text().strip(),
            paper_size=self.paper_size.currentText(),
            orientation=self.orientation.currentText().lower(),
            frame_style=self.frame_style.currentData(),
            centerline_mode=self.centerline.currentData(),
            pole_size_mm=self.pole_size.value(),
            show_compass=self.compass.isChecked(),
            road_edge_width=self.road_edge_width.value(),
            centerline_width=self.centerline_width.value(),
            page_count=self.page_count.value(),
            work_description=self._work_description,
        )

    def _page_count_changed(self) -> None:
        self.current_page = min(self.current_page, self.page_count.value() - 1)
        self.refresh_preview()

    def _change_page(self, offset: int) -> None:
        self.current_page = max(
            0, min(self.current_page + offset, self.page_count.value() - 1)
        )
        self.refresh_preview()

    def schedule_preview_refresh(self) -> None:
        """Coalesce rapid setting changes into one redraw for large projects."""
        self._refresh_timer.start()

    def refresh_preview(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._refresh_timer.stop()
            pages = prepare_excel_pages(self.source_objects, self.settings())
            self.current_page = min(self.current_page, len(pages) - 1)
            self.preview.setUpdatesEnabled(False)
            self.preview_scene.clear()
            for item in pages[self.current_page]:
                _draw_preview_object(self.preview_scene, item)
            if self.preview_scene.items():
                bounds = self.preview_scene.itemsBoundingRect().adjusted(-12, -12, 12, 12)
                self.preview_scene.setSceneRect(bounds)
                self.preview.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
            self.page_label.setText(f"Sheet {self.current_page + 1} / {len(pages)}")
            self.previous_page.setEnabled(self.current_page > 0)
            self.next_page.setEnabled(self.current_page < len(pages) - 1)
        finally:
            self.preview.setUpdatesEnabled(True)
            self._refreshing = False

    def export_objects(self) -> list[ExcelObject]:
        """Return the exact styled snapshot currently represented by the preview."""
        return prepare_excel_objects(self.source_objects, self.settings())

    def export_pages(self) -> list[list[ExcelObject]]:
        """Return every styled sheet represented by the review."""
        return prepare_excel_pages(self.source_objects, self.settings())


def _draw_preview_object(scene: QGraphicsScene, item: ExcelObject) -> None:
    pen = QPen(QColor("black"), item.line_width)
    if item.line_style == "dashed":
        pen.setStyle(Qt.PenStyle.DashLine)
    if item.kind == "line":
        (x1, y1), (x2, y2) = item.points
        scene.addLine(x1, y1, x2, y2, pen)
    elif item.kind == "text":
        text = scene.addText(item.text)
        text.setDefaultTextColor(QColor("black"))
        font = text.font()
        font.setPointSizeF(item.font_size)
        text.setFont(font)
        text.setPos(*item.points[0])
        text.setRotation(item.rotation)
    else:
        (left, top), (right, bottom) = item.points
        rect = QRectF(left, top, right - left, bottom - top)
        brush = QBrush(QColor("black")) if item.fill_color is not None else QBrush(Qt.BrushStyle.NoBrush)
        shape = scene.addRect(rect, pen, brush) if item.kind == "rectangle" else scene.addEllipse(rect, pen, brush)
        shape.setTransformOriginPoint(rect.center())
        shape.setRotation(item.rotation)
