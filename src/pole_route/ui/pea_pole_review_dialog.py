"""Review automatic station order and QC for imported PEA GIS poles."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import PEAPoleOrdering, PoleQCStatus
from pole_route.domain.route import Route
from pole_route.geometry.pea_linear_reference import reference_pea_poles


class PEAPoleReviewDialog(QDialog):
    COLUMNS = (
        "Order", "Pole ID", "Latitude", "Longitude", "Height", "Raw voltage",
        "Normalized voltage", "Station (m)", "Offset (m)", "QC", "Source row", "Included",
    )

    def __init__(
        self,
        records: list[PEAPoleRecord],
        main_route: Route,
        ordering: PEAPoleOrdering,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._records = records
        self._records_by_key = {record.source_key: record for record in records}
        self._main_route = main_route
        self._ordering = ordering
        self.setWindowTitle("Review PEA pole order and QC")
        self.resize(1180, 620)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        controls = QHBoxLayout()
        for label, callback in (
            ("Move Up", lambda: self._move(-1)),
            ("Move Down", lambda: self._move(1)),
            ("Reverse / change START", self._reverse),
            ("Exclude", lambda: self._include(False)),
            ("Restore / Include", lambda: self._include(True)),
            ("Restore Auto Sort", self._restore_auto),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Accept / Confirm")
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def ordering(self) -> PEAPoleOrdering:
        return self._ordering

    def _selected_key(self) -> str | None:
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 else None

    def _refresh(self) -> None:
        entries = sorted(
            self._ordering.entries,
            key=lambda entry: (
                0 if entry.included else 1,
                entry.review_order if entry.review_order is not None else entry.station_metres,
                entry.source_key,
            ),
        )
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            record = self._records_by_key[entry.source_key]
            voltage = (
                ""
                if record.voltage_min_kv is None
                else f"{record.voltage_min_kv:g}–{record.voltage_max_kv:g} kV"
            )
            values = (
                entry.review_order or "", record.source_id, f"{record.latitude:.7f}",
                f"{record.longitude:.7f}", record.height_metres or "", record.raw_voltage or "",
                voltage, f"{entry.station_metres:.2f}", f"{entry.offset_metres:.2f}",
                entry.qc_status.value, record.source_row, "Yes" if entry.included else "No",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry.source_key)
                item.setToolTip("\n".join(entry.qc_reasons))
                if entry.qc_status is PoleQCStatus.REVIEW:
                    item.setBackground(QColor("#fff3b0"))
                elif entry.qc_status is PoleQCStatus.STRONG_REVIEW:
                    item.setBackground(QColor("#ffb3b3"))
                if not entry.included:
                    item.setForeground(QColor("#777777"))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def _move(self, delta: int) -> None:
        key = self._selected_key()
        if key:
            self._ordering = self._ordering.move(key, delta)
            self._refresh()

    def _include(self, included: bool) -> None:
        key = self._selected_key()
        if key:
            self._ordering = self._ordering.set_included(key, included)
            self._refresh()

    def _reverse(self) -> None:
        self._ordering = reference_pea_poles(
            self._records,
            self._main_route,
            direction_reversed=not self._ordering.direction_reversed,
        )
        self._refresh()

    def _restore_auto(self) -> None:
        self._ordering = self._ordering.restore_auto_sort()
        self._refresh()

    def _confirm(self) -> None:
        self._ordering = self._ordering.confirm()
        self.accept()
