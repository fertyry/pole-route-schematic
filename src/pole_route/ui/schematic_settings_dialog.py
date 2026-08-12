"""Confirm the pole-spacing strategy used for schematic generation."""

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from pole_route.geometry.schematic_layout import PoleSpacingMode, SchematicLayoutMode


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
        self.spacing.addItem(
            "Network layout (keep roads and junctions)",
            SchematicLayoutMode.NETWORK,
        )
        self.spacing.addItem(
            "Straight schematic - equal pole spacing",
            SchematicLayoutMode.STRAIGHT_EQUAL,
        )
        self.spacing.addItem(
            "Straight schematic - relative pole spacing",
            SchematicLayoutMode.STRAIGHT_RELATIVE,
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
        return (
            PoleSpacingMode.EQUAL
            if self.layout_mode() is SchematicLayoutMode.STRAIGHT_EQUAL
            else PoleSpacingMode.PROJECTED_STATION
        )

    def layout_mode(self) -> SchematicLayoutMode:
        return SchematicLayoutMode(self.spacing.currentData())

    def _update_explanation(self) -> None:
        if self.layout_mode() is SchematicLayoutMode.NETWORK:
            text = (
                "Keeps all imported roads, junctions, and pole positions in their shared topology."
            )
        elif self.layout_mode() is SchematicLayoutMode.STRAIGHT_EQUAL:
            text = "Straightens the main road and gives every physical pole the same visual gap."
        else:
            text = (
                "Straightens the main road while preserving relative projected gaps between poles."
            )
        self.explanation.setText(text)
