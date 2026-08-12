"""Editable Excel export settings and page preview."""

from PySide6.QtCore import QLocale, QRectF, Qt
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
    QLineEdit,
    QVBoxLayout,
)

from pole_route.exporters.excel_exporter import (
    ExcelExportSettings,
    ExcelObject,
    collect_scene_objects,
    prepare_excel_objects,
)


class ExcelExportDialog(QDialog):
    def __init__(self, source_scene, parent=None) -> None:
        super().__init__(parent)
        self.source_scene = source_scene
        self.source_objects = collect_scene_objects(source_scene)
        self.setWindowTitle("Excel export preview")
        self.resize(1150, 760)
        self.project_title = QLineEdit("PoleRoute Schematic")
        self.location = QLineEdit()
        self.prepared_by = QLineEdit()
        self.drawing_number = QLineEdit()
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

        form = QFormLayout()
        form.addRow("Project title", self.project_title)
        form.addRow("Location", self.location)
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

        self.preview_scene = QGraphicsScene(self)
        self.preview = QGraphicsView(self.preview_scene)
        self.preview.setBackgroundBrush(QBrush(QColor("#777777")))
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
        layout.addWidget(self.preview, 3)
        layout.addLayout(right, 1)
        for control in (
            self.project_title,
            self.location,
            self.prepared_by,
            self.drawing_number,
        ):
            control.textChanged.connect(self.refresh_preview)
        for control in (self.paper_size, self.orientation, self.frame_style, self.centerline):
            control.currentIndexChanged.connect(self.refresh_preview)
        self.pole_size.valueChanged.connect(self.refresh_preview)
        self.road_edge_width.valueChanged.connect(self.refresh_preview)
        self.centerline_width.valueChanged.connect(self.refresh_preview)
        self.compass.toggled.connect(self.refresh_preview)
        self.refresh_preview()

    def settings(self) -> ExcelExportSettings:
        return ExcelExportSettings(
            self.project_title.text().strip(),
            self.location.text().strip(),
            self.prepared_by.text().strip(),
            self.drawing_number.text().strip(),
            self.paper_size.currentText(),
            self.orientation.currentText().lower(),
            self.frame_style.currentData(),
            self.centerline.currentData(),
            self.pole_size.value(),
            self.compass.isChecked(),
            self.road_edge_width.value(),
            self.centerline_width.value(),
        )

    def refresh_preview(self) -> None:
        next_scene = QGraphicsScene(self)
        for item in prepare_excel_objects(self.source_objects, self.settings()):
            _draw_preview_object(next_scene, item)
        if not next_scene.items():
            return
        bounds = next_scene.itemsBoundingRect().adjusted(-12, -12, 12, 12)
        next_scene.setSceneRect(bounds)
        previous_scene = self.preview_scene
        self.preview_scene = next_scene
        self.preview.setScene(next_scene)
        self.preview.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        previous_scene.deleteLater()


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
