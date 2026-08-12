"""Small selection-aware appearance panel for the canvas editor."""

from PySide6.QtCore import QLocale, Signal
from PySide6.QtWidgets import QDoubleSpinBox, QLabel, QPushButton, QVBoxLayout, QWidget


class PropertiesPanel(QWidget):
    colorRequested = Signal()
    lineWidthCommitted = Signal(float)
    rotationCommitted = Signal(float)
    bringForwardRequested = Signal()
    sendBackwardRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.summary = QLabel("No object selected")
        self.summary.setWordWrap(True)
        self.color = QPushButton("Choose color...")
        self.color.clicked.connect(self.colorRequested)
        self.width = QDoubleSpinBox()
        self.width.setLocale(QLocale.c())
        self.width.setRange(0.25, 20.0)
        self.width.setSingleStep(0.25)
        self.width.setSuffix(" px")
        self.width.editingFinished.connect(
            lambda: self.lineWidthCommitted.emit(self.width.value())
        )
        self.rotation = QDoubleSpinBox()
        self.rotation.setLocale(QLocale.c())
        self.rotation.setRange(-360.0, 360.0)
        self.rotation.setSingleStep(1.0)
        self.rotation.setSuffix(" deg")
        self.rotation.editingFinished.connect(
            lambda: self.rotationCommitted.emit(self.rotation.value())
        )
        self.forward = QPushButton("Bring forward")
        self.forward.clicked.connect(self.bringForwardRequested)
        self.backward = QPushButton("Send backward")
        self.backward.clicked.connect(self.sendBackwardRequested)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(QLabel("Color"))
        layout.addWidget(self.color)
        layout.addWidget(QLabel("Line width"))
        layout.addWidget(self.width)
        layout.addWidget(QLabel("Object rotation"))
        layout.addWidget(self.rotation)
        layout.addWidget(self.forward)
        layout.addWidget(self.backward)
        layout.addStretch(1)
        self.show_for_items([])

    def show_for_items(self, items) -> None:
        count = len(items)
        enabled = count > 0
        self.summary.setText(
            "No object selected" if not count else f"Selected: {count} object(s)"
        )
        for control in (self.color, self.width, self.rotation, self.forward, self.backward):
            control.setEnabled(enabled)
        if count:
            self.rotation.blockSignals(True)
            self.rotation.setValue(items[0].rotation())
            self.rotation.blockSignals(False)
