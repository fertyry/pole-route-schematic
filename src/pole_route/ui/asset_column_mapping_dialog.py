"""Mapping and preview dialog for source-neutral GIS asset files."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.importers.asset_importer import (
    FIELD_LABELS,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    AssetTable,
)


class AssetColumnMappingDialog(QDialog):
    def __init__(self, table: AssetTable, suggested_mapping, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Match asset columns")
        self.resize(820, 580)
        self._selectors: dict[str, QComboBox] = {}
        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Header detected on row {table.header_row}. Match source columns to GIS asset fields."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        for field in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS):
            selector = QComboBox()
            selector.addItem(
                "(Not provided)" if field in OPTIONAL_FIELDS else "(Choose a column)", None
            )
            for header in table.headers:
                selector.addItem(header, header)
            suggested = suggested_mapping.get(field)
            if suggested:
                selector.setCurrentIndex(selector.findData(suggested))
            form.addRow(FIELD_LABELS[field] + (" *" if field in REQUIRED_FIELDS else ""), selector)
            self._selectors[field] = selector
        layout.addLayout(form)
        preview = QTableWidget(min(5, len(table.rows)), len(table.headers))
        preview.setHorizontalHeaderLabels(table.headers)
        preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row_index, row in enumerate(table.rows[:5]):
            for column_index, value in enumerate(row):
                preview.setItem(row_index, column_index, QTableWidgetItem(str(value or "")))
        layout.addWidget(QLabel("Preview (first 5 data rows)"))
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm import")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mapping(self):
        return {field: selector.currentData() for field, selector in self._selectors.items()}

    def _validate_and_accept(self):
        mapping = self.mapping()
        missing = [FIELD_LABELS[field] for field in REQUIRED_FIELDS if not mapping[field]]
        selected = [value for value in mapping.values() if value]
        if missing:
            QMessageBox.warning(self, "Mapping incomplete", "Choose columns for: " + ", ".join(missing))
            return
        if len(selected) != len(set(selected)):
            QMessageBox.warning(self, "Mapping invalid", "Each source column can be used only once")
            return
        self.accept()
