"""Explicit selection of supported PEA GIS workbook sheets."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.importers.pea_gis import PEAWorkbookDiscovery


class PEASheetSelectionDialog(QDialog):
    def __init__(self, discovery: PEAWorkbookDiscovery, parent=None) -> None:
        super().__init__(parent)
        self._discovery = discovery
        self._checks: dict[str, QCheckBox] = {}
        self.setWindowTitle("Choose PEA GIS sheets")
        self.resize(720, 430)
        layout = QVBoxLayout(self)
        note = QLabel(
            "PoleRoute detected the workbook profiles. Choose supported sheets to import; "
            "excluded and unsupported sheets remain visible for audit."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTableWidget(len(discovery.sheets), 4)
        table.setHorizontalHeaderLabels(("Import", "Worksheet", "Detected profile", "Status"))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, sheet in enumerate(discovery.sheets):
            check = QCheckBox()
            check.setChecked(sheet.supported)
            check.setEnabled(sheet.supported)
            table.setCellWidget(row, 0, check)
            self._checks[sheet.name] = check
            table.setItem(row, 1, QTableWidgetItem(sheet.name))
            table.setItem(row, 2, QTableWidgetItem(sheet.profile or ""))
            status = (
                "Supported"
                if sheet.supported
                else sheet.exclusion_reason or "Unsupported / retained for audit"
            )
            item = QTableWidgetItem(status)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 3, item)
        table.resizeColumnsToContents()
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import selected sheets")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_sheet_names(self) -> set[str]:
        return {
            name for name, check in self._checks.items() if check.isEnabled() and check.isChecked()
        }
