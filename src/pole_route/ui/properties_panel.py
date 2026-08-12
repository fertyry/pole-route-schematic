"""Selection-aware controls for editing schematic object appearance."""

from PySide6.QtCore import QLocale, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PropertiesPanel(QWidget):
    textCommitted = Signal(str)
    colorRequested = Signal()
    lineWidthCommitted = Signal(float)
    lineStyleCommitted = Signal(str)
    fontSizeCommitted = Signal(int)
    rotationCommitted = Signal(float)
    bringForwardRequested = Signal()
    sendBackwardRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.kind = QLabel("No object selected")
        self.kind.setWordWrap(True)

        self.text = QLineEdit()
        self.text.editingFinished.connect(lambda: self.textCommitted.emit(self.text.text()))
        self.color = QPushButton("Choose color...")
        self.color.clicked.connect(self.colorRequested)
        self.line_width = QDoubleSpinBox()
        self.line_width.setLocale(QLocale.c())
        self.line_width.setRange(0.25, 20.0)
        self.line_width.setSingleStep(0.25)
        self.line_width.editingFinished.connect(
            lambda: self.lineWidthCommitted.emit(self.line_width.value())
        )
        self.line_style = QComboBox()
        self.line_style.addItem("Solid", "solid")
        self.line_style.addItem("Dashed", "dash")
        self.line_style.currentIndexChanged.connect(
            lambda: self.lineStyleCommitted.emit(self.line_style.currentData())
        )
        self.font_size = QSpinBox()
        self.font_size.setLocale(QLocale.c())
        self.font_size.setRange(6, 96)
        self.font_size.editingFinished.connect(
            lambda: self.fontSizeCommitted.emit(self.font_size.value())
        )
        self.rotation = QDoubleSpinBox()
        self.rotation.setLocale(QLocale.c())
        self.rotation.setRange(-360.0, 360.0)
        self.rotation.setDecimals(1)
        self.rotation.setSuffix("°")
        self.rotation.editingFinished.connect(
            lambda: self.rotationCommitted.emit(self.rotation.value())
        )
        self.forward = QPushButton("Bring forward")
        self.forward.clicked.connect(self.bringForwardRequested)
        self.backward = QPushButton("Send backward")
        self.backward.clicked.connect(self.sendBackwardRequested)

        self.form = QFormLayout()
        self.form.addRow("Text", self.text)
        self.form.addRow("Color", self.color)
        self.form.addRow("Line width", self.line_width)
        self.form.addRow("Line style", self.line_style)
        self.form.addRow("Font size", self.font_size)
        self.form.addRow("Object rotation", self.rotation)

        layout = QVBoxLayout(self)
        layout.addWidget(self.kind)
        layout.addLayout(self.form)
        layout.addWidget(self.forward)
        layout.addWidget(self.backward)
        layout.addStretch(1)
        self.show_for_item(None)

    def show_for_items(self, items) -> None:
        """Show only controls supported by the selected graphics item."""
        items = list(items)
        item = items[0] if items else None
        has_item = item is not None
        item_type = item.data(0) if has_item else None
        is_text = has_item and hasattr(item, "text") and hasattr(item, "setText")
        has_pen = has_item and (
            hasattr(item, "pen") or any(hasattr(child, "pen") for child in item.childItems())
        )
        self.kind.setText(
            (
                f"Selected: {len(items)} objects"
                if len(items) > 1
                else f"Selected: {str(item_type).replace('_', ' ').title()}"
            )
            if has_item
            else "No object selected"
        )
        self.text.setVisible(is_text)
        self.font_size.setVisible(is_text)
        self.form.labelForField(self.text).setVisible(is_text)
        self.form.labelForField(self.font_size).setVisible(is_text)
        self.color.setEnabled(has_item)
        self.line_width.setVisible(has_pen)
        self.line_style.setVisible(has_pen)
        self.form.labelForField(self.line_width).setVisible(has_pen)
        self.form.labelForField(self.line_style).setVisible(has_pen)
        self.forward.setEnabled(has_item)
        self.backward.setEnabled(has_item)
        self.rotation.setEnabled(has_item)
        rotations = {round(selected.rotation(), 3) for selected in items}
        self.rotation.setSpecialValueText("Mixed" if len(rotations) > 1 else "")
        if rotations:
            self.rotation.setValue(next(iter(rotations)) if len(rotations) == 1 else -360.0)

        if is_text:
            self.text.blockSignals(True)
            self.text.setText(item.text())
            self.text.blockSignals(False)
            self.font_size.setValue(max(1, round(item.font().pointSizeF())))
        pen_item = _first_pen_item(item) if has_pen else None
        if pen_item is not None:
            self.line_width.setValue(pen_item.pen().widthF())
            style = "dash" if pen_item.pen().style().value != 1 else "solid"
            self.line_style.blockSignals(True)
            self.line_style.setCurrentIndex(self.line_style.findData(style))
            self.line_style.blockSignals(False)

    def show_for_item(self, item) -> None:
        self.show_for_items([] if item is None else [item])


def _first_pen_item(item):
    if item is None:
        return None
    if hasattr(item, "pen"):
        return item
    return next((child for child in item.childItems() if hasattr(child, "pen")), None)
