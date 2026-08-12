"""Settings confirmation for metric road and pole geometry."""

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)


class GeometrySettingsDialog(QDialog):
    """Collect road width and offset outside each road edge."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Build road geometry")
        self.resize(440, 220)

        intro = QLabel(
            "Road width is the total edge-to-edge width. Pole offset is measured outward "
            "from each road edge. Review the values before building the metric preview."
        )
        intro.setWordWrap(True)

        self.road_width = QDoubleSpinBox()
        self.road_width.setLocale(QLocale.c())
        self.road_width.setRange(0.1, 1000.0)
        self.road_width.setDecimals(2)
        self.road_width.setSuffix(" m")
        self.road_width.setValue(6.0)

        self.pole_offset = QDoubleSpinBox()
        self.pole_offset.setLocale(QLocale.c())
        self.pole_offset.setRange(0.0, 1000.0)
        self.pole_offset.setDecimals(2)
        self.pole_offset.setSuffix(" m")
        self.pole_offset.setValue(2.0)

        form = QFormLayout()
        form.addRow("Road width", self.road_width)
        form.addRow("Pole offset from road edge", self.pole_offset)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Build geometry")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)
