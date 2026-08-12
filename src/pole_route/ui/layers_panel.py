"""Simple fixed layers for schematic editing."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QWidget,
)

LAYERS = (
    ("Roads", {"road"}),
    ("Poles", {"pole"}),
    ("Labels", {"label"}),
    ("Blocks", {"block"}),
    ("Annotations", {"drawing"}),
)


class LayersPanel(QWidget):
    visibilityChanged = Signal(str, bool)
    lockChanged = Signal(str, bool)
    selectRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.visibility_checks = {}
        self.lock_checks = {}
        layout = QGridLayout(self)
        layout.addWidget(QLabel("Layer"), 0, 0)
        layout.addWidget(QLabel("Show"), 0, 1)
        layout.addWidget(QLabel("Lock"), 0, 2)
        for row, (name, _types) in enumerate(LAYERS, start=1):
            select = QPushButton(name)
            select.clicked.connect(lambda _checked=False, layer=name: self.selectRequested.emit(layer))
            visible = QCheckBox()
            visible.setChecked(True)
            visible.toggled.connect(
                lambda checked, layer=name: self.visibilityChanged.emit(layer, checked)
            )
            locked = QCheckBox()
            locked.setChecked(name == "Roads")
            locked.toggled.connect(
                lambda checked, layer=name: self.lockChanged.emit(layer, checked)
            )
            self.visibility_checks[name] = visible
            self.lock_checks[name] = locked
            layout.addWidget(select, row, 0)
            layout.addWidget(visible, row, 1)
            layout.addWidget(locked, row, 2)
        layout.setRowStretch(len(LAYERS) + 1, 1)

    def reset_for_generated_scene(self) -> None:
        """Make every new layer visible and lock only the generated roads."""
        for name, visible in self.visibility_checks.items():
            visible.setChecked(True)
            self.lock_checks[name].setChecked(name == "Roads")


def layer_types(name: str) -> set[str]:
    return next(types for layer_name, types in LAYERS if layer_name == name)
