"""Worksheet and header-row confirmation shared by pole and asset imports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.importers.tabular_source import (
    HeaderDetection,
    detect_header,
    list_worksheets,
    read_rows,
    unique_headers,
)


class TabularSourceDialog(QDialog):
    def __init__(self, path, aliases, required_fields, field_labels, parent=None) -> None:
        super().__init__(parent)
        self._path = Path(path)
        self._aliases = aliases
        self._required = required_fields
        self._field_labels = field_labels
        self._rows: list[tuple[object, ...]] = []
        self._detection: HeaderDetection | None = None
        self.setWindowTitle("Choose worksheet and header row")
        self.resize(840, 540)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.sheet_selector = QComboBox()
        sheets = list_worksheets(path)
        if sheets:
            for sheet in sheets:
                self.sheet_selector.addItem(sheet, sheet)
        else:
            self.sheet_selector.addItem("CSV", None)
        self.sheet_selector.currentIndexChanged.connect(self._load_sheet)
        form.addRow("Worksheet:", self.sheet_selector)
        self.header_row = QSpinBox()
        self.header_row.setMinimum(1)
        self.header_row.valueChanged.connect(self._refresh_preview)
        form.addRow("Header row:", self.header_row)
        self.confidence = QLabel()
        form.addRow("Detection confidence:", self.confidence)
        layout.addLayout(form)
        self.mapping_summary = QLabel()
        self.mapping_summary.setWordWrap(True)
        layout.addWidget(self.mapping_summary)
        self.preview = QTableWidget()
        self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.preview, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use worksheet/header")
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._load_sheet()

    def sheet_name(self) -> str | None:
        return self.sheet_selector.currentData()

    def header_row_number(self) -> int:
        return self.header_row.value()

    def _load_sheet(self) -> None:
        try:
            self._rows = read_rows(self._path, self.sheet_name())
            self._detection = detect_header(self._rows, self._aliases, self._required)
        except ValueError as error:
            QMessageBox.warning(self, "Worksheet inspection failed", str(error))
            self._rows = []
            self._detection = None
            return
        self.header_row.blockSignals(True)
        self.header_row.setMaximum(max(1, len(self._rows)))
        self.header_row.setValue(self._detection.row_number)
        self.header_row.blockSignals(False)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not self._rows:
            return
        index = self.header_row.value() - 1
        headers = unique_headers(self._rows[index])
        detection = detect_header([self._rows[index]], self._aliases, self._required)
        auto = self._detection is not None and index == self._detection.row_index
        self.confidence.setText(detection.confidence + (" (auto-detected)" if auto else " (manual)"))
        pairs = [
            f"{self._field_labels.get(field, field.replace('_', ' ').title())} → {headers[column]}"
            for field, column in detection.mapping.items()
            if column < len(headers)
        ]
        self.mapping_summary.setText("Detected mappings: " + (", ".join(pairs) or "None"))
        rows = self._rows[index + 1:index + 6]
        self.preview.setColumnCount(len(headers))
        self.preview.setHorizontalHeaderLabels(headers)
        self.preview.setRowCount(len(rows))
        for row_number, row in enumerate(rows):
            for column in range(len(headers)):
                value = row[column] if column < len(row) else None
                self.preview.setItem(row_number, column, QTableWidgetItem(str(value or "")))
        self.preview.resizeColumnsToContents()

    def _accept_selection(self) -> None:
        if not self._rows:
            return
        # An explicit user choice is authoritative even when the column names are
        # unfamiliar. The following mapping dialog still requires every mandatory
        # field before the import can continue.
        self.accept()
