"""Lightweight viewer for project-local Surround benchmark history."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.diagnostics.fetch_benchmark import benchmark_log_path, read_fetch_records


class FetchDiagnosticsDialog(QDialog):
    """Show a compact newest-first summary without treating logs as project data."""

    HEADERS = (
        "Time", "Operation", "Route", "Length km", "Result", "Total", "OSM",
        "Buildings", "Places", "Requests", "Retries", "Splits", "Unresolved",
        "Roads", "Building Count", "Places Count", "Peak RAM",
    )

    def __init__(self, project_path: str | Path, parent=None) -> None:
        super().__init__(parent)
        self.project_path = Path(project_path)
        self.log_path = benchmark_log_path(project_path)
        self.setWindowTitle("Fetch Diagnostics")
        self.resize(1250, 480)
        records = read_fetch_records(project_path)
        note = QLabel(
            f"{len(records)} recorded network operation(s). Newest first.\n{self.log_path}"
        )
        note.setWordWrap(True)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setObjectName("fetchDiagnosticsTable")
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._populate(records)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        open_folder = QPushButton("Open diagnostics folder")
        open_folder.clicked.connect(self.open_diagnostics_folder)
        open_log = QPushButton("Open log file")
        open_log.setEnabled(self.log_path.exists())
        open_log.clicked.connect(self.open_log_file)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(open_folder, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(open_log, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def _populate(self, records) -> None:
        for record in reversed(records):
            route = record.get("route") or {}
            providers = record.get("providers") or {}
            osm = providers.get("OpenStreetMap") or {}
            buildings = providers.get("Overture Buildings") or {}
            places = providers.get("Overture Places") or {}
            categories = record.get("category_counts") or {}
            memory = record.get("memory") or {}
            values = (
                _time_label(record.get("completed_at")),
                str(record.get("operation", "")),
                str(route.get("name", "")),
                f"{float(route.get('length_metres') or 0) / 1000:.2f}",
                str(record.get("result", "")),
                _duration(record.get("total_elapsed_seconds")),
                _duration(osm.get("fetch_elapsed_seconds")),
                _duration(buildings.get("elapsed_seconds")),
                _duration(places.get("elapsed_seconds")),
                _number(osm.get("network_request_count")),
                _number(osm.get("retry_count")),
                _number(osm.get("adaptive_split_count")),
                _number(record.get("unresolved_final_interval_count")),
                _number(categories.get("roads_sois")),
                _number(categories.get("building")),
                _number(categories.get("poi")),
                _memory(memory.get("process_peak_rss_mb")),
            )
            row = self.table.rowCount()
            self.table.insertRow(row)
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def open_diagnostics_folder(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path.parent)))

    def open_log_file(self) -> None:
        if self.log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path)))


def _duration(value) -> str:
    seconds = float(value or 0)
    if seconds < 60:
        return f"{seconds:.1f} sec"
    minutes, remainder = divmod(round(seconds), 60)
    return f"{minutes}m {remainder:02d}s"


def _memory(value) -> str:
    if value is None:
        return "—"
    megabytes = float(value)
    return f"{megabytes / 1024:.2f} GB" if megabytes >= 1024 else f"{megabytes:.0f} MB"


def _number(value) -> str:
    return str(int(float(value or 0)))


def _time_label(value) -> str:
    return str(value or "").replace("T", " ").removesuffix("+00:00")
