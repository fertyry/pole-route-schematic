"""Confirmation dialog for an edited PoleRoute CAD Master."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.importers.edited_dxf_importer import EditedDxfInspection


class EditedDxfDialog(QDialog):
    def __init__(self, inspection: EditedDxfInspection, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review edited CAD Master")
        self.resize(900, 620)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"Found {len(inspection.pole_blocks)} physical pole block(s) and "
                f"{len(inspection.sheet_breaks)} sheet break(s). Confirm before "
                "using edited positions for sheet cutting."
            )
        )
        problems = []
        if inspection.missing_pole_ids:
            problems.append("Missing: " + ", ".join(inspection.missing_pole_ids))
        if inspection.unexpected_pole_ids:
            problems.append("Unexpected: " + ", ".join(inspection.unexpected_pole_ids))
        if inspection.duplicate_pole_ids:
            problems.append("Duplicated in CAD: " + ", ".join(inspection.duplicate_pole_ids))
        status = QLabel("\n".join(problems) if problems else "Pole identity check passed.")
        status.setObjectName("editedDxfValidationStatus")
        layout.addWidget(status)

        table = QTableWidget(len(inspection.pole_blocks), 7)
        table.setObjectName("editedDxfPoleTable")
        table.setHorizontalHeaderLabels(
            ["Block", "Pole ID(s)", "Quantity", "X", "Y", "Rotation", "Station"]
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, block in enumerate(inspection.pole_blocks):
            values = (
                block.block_name,
                " / ".join(block.pole_ids),
                " / ".join(str(value) for value in block.quantities),
                f"{block.x:.3f}",
                f"{block.y:.3f}",
                f"{block.rotation:.2f} deg",
                f"{block.station_metres:.2f} m",
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use edited CAD Master")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(inspection.is_valid)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
