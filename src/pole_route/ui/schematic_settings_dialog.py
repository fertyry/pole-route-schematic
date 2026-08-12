"""Confirm the pole-spacing strategy used for schematic generation."""

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from pole_route.geometry.schematic_layout import PoleSpacingMode


class SchematicSettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate schematic")
        self.resize(520, 230)

        intro = QLabel(
            "Choose how pole positions should be distributed along the schematic road. "
            "You can regenerate later using the other mode."
        )
        intro.setWordWrap(True)

        self.spacing = QComboBox()
        self.spacing.addItem("Equal spacing (clear diagram)", PoleSpacingMode.EQUAL)
        self.spacing.addItem(
            "Projected station spacing (preserve relative gaps)",
            PoleSpacingMode.PROJECTED_STATION,
        )
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        self.spacing.currentIndexChanged.connect(self._update_explanation)

        form = QFormLayout()
        form.addRow("Pole placement", self.spacing)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generate schematic")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.explanation)
        layout.addWidget(buttons)
        self._update_explanation()

    def spacing_mode(self) -> PoleSpacingMode:
        return self.spacing.currentData()

    def _update_explanation(self) -> None:
        if self.spacing_mode() is PoleSpacingMode.EQUAL:
            text = "Every pole receives the same visual gap, regardless of its measured location."
        else:
            text = (
                "Gaps follow each pole's nearest projected station on the route. "
                "Close structures remain close and larger crossings remain wider."
            )
        self.explanation.setText(text)
