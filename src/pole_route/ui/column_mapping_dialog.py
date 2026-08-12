"""Dialog for matching source columns to PoleRoute fields."""

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

from pole_route.importers.pole_importer import (
    FIELD_LABELS,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    PoleTable,
)


class ColumnMappingDialog(QDialog):
    """Collect a valid mapping while previewing source rows."""

    def __init__(
        self,
        table: PoleTable,
        suggested_mapping: dict[str, str | None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Match Excel columns")
        self.resize(760, 500)
        self._table = table
        self._selectors: dict[str, QComboBox] = {}

        intro = QLabel(
            f"Header detected on row {table.header_row}. "
            "Match the file columns to the information used by PoleRoute Schematic."
        )
        intro.setWordWrap(True)

        form = QFormLayout()
        for field in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS):
            selector = QComboBox()
            if field in OPTIONAL_FIELDS:
                selector.addItem("(Not provided)", None)
            else:
                selector.addItem("(Choose a column)", None)
            for header in table.headers:
                selector.addItem(header, header)
            suggested = suggested_mapping.get(field)
            if suggested:
                selector.setCurrentIndex(selector.findData(suggested))
            label = FIELD_LABELS[field] + (" *" if field in REQUIRED_FIELDS else "")
            form.addRow(label, selector)
            self._selectors[field] = selector

        preview = QTableWidget(min(5, len(table.rows)), len(table.headers))
        preview.setHorizontalHeaderLabels(table.headers)
        preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row_index, row in enumerate(table.rows[:5]):
            for column_index, value in enumerate(row):
                preview.setItem(row_index, column_index, QTableWidgetItem(str(value or "")))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(QLabel("Preview (first 5 data rows)"))
        layout.addWidget(preview, 1)
        layout.addWidget(buttons)

    def mapping(self) -> dict[str, str | None]:
        return {field: selector.currentData() for field, selector in self._selectors.items()}

    def _validate_and_accept(self) -> None:
        mapping = self.mapping()
        missing = [FIELD_LABELS[field] for field in REQUIRED_FIELDS if not mapping[field]]
        selected = [column for column in mapping.values() if column]
        if missing:
            QMessageBox.warning(self, "Mapping incomplete", "Choose columns for: " + ", ".join(missing))
            return
        if len(selected) != len(set(selected)):
            QMessageBox.warning(self, "Mapping invalid", "Each source column can be used only once")
            return
        self.accept()

