"""Review suggested PEA asset-to-pole relationships without auto-confirming."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.domain.pea_asset import PEAAsset, PEAAssetMatch
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import PEAPoleOrdering
from pole_route.domain.route import Route
from pole_route.geometry.pea_asset_matching import match_pea_assets


class PEAAssetReviewDialog(QDialog):
    COLUMNS = (
        "Use", "Source", "Asset Type", "Asset ID", "Description", "Latitude",
        "Longitude", "Nearest Pole", "Distance (m)", "Pole Order", "Match Status",
        "Side Evidence", "QC", "Confirmed Pole",
    )

    def __init__(self, assets, matches, poles, ordering=None, main_route=None, parent=None):
        super().__init__(parent)
        self._assets: tuple[PEAAsset, ...] = tuple(assets)
        self._matches: dict[str, PEAAssetMatch] = {item.asset_id: item for item in matches}
        self._poles: tuple[PEAPoleRecord, ...] = tuple(poles)
        self._ordering: PEAPoleOrdering | None = ordering
        self._main_route: Route | None = main_route
        self._selectors: dict[str, QComboBox] = {}
        self.setWindowTitle("Review Assets")
        self.resize(1250, 620)
        layout = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Source:"))
        self.source_filter = QComboBox()
        self.source_filter.addItem("All", None)
        for source in sorted({asset.source_provider for asset in self._assets}):
            self.source_filter.addItem(source, source)
        self.source_filter.currentIndexChanged.connect(self._refresh)
        filter_row.addWidget(self.source_filter)
        filter_row.addWidget(QLabel("Asset type:"))
        self.type_filter = QComboBox()
        self.type_filter.addItem("All", None)
        for asset_type in sorted({asset.asset_type for asset in self._assets}, key=str):
            self.type_filter.addItem(asset_type.value.replace("_", " ").title(), asset_type.value)
        self.type_filter.currentIndexChanged.connect(self._refresh)
        filter_row.addWidget(self.type_filter)
        filter_row.addWidget(QLabel("Match state:"))
        self.state_filter = QComboBox()
        self.state_filter.addItem("All", None)
        for state in ("unmatched", "suggested", "ambiguous", "confirmed"):
            self.state_filter.addItem(state.title(), state)
        self.state_filter.currentIndexChanged.connect(self._refresh)
        filter_row.addWidget(self.state_filter)
        filter_row.addStretch()
        layout.addLayout(filter_row)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        for label, callback in (
            ("Confirm Selected", self._confirm_selected),
            ("Clear Match", self._clear_selected),
            ("Recompute Suggestions", self._recompute),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch(); layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Accept Review")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def matches(self) -> tuple[PEAAssetMatch, ...]:
        return tuple(self._matches[asset.stable_id] for asset in self._assets)

    def _selected_asset_id(self):
        row = self.table.currentRow()
        return self.table.item(row, 3).data(Qt.ItemDataRole.UserRole) if row >= 0 else None

    def _refresh(self):
        selected_type = self.type_filter.currentData()
        selected_source = self.source_filter.currentData()
        selected_state = self.state_filter.currentData()
        displayed = [
            asset
            for asset in self._assets
            if (selected_type is None or asset.asset_type.value == selected_type)
            and (selected_source is None or asset.source_provider == selected_source)
            and (
                selected_state is None
                or self._matches.get(asset.stable_id, PEAAssetMatch(asset.stable_id)).state.value
                == selected_state
            )
        ]
        self.table.setRowCount(len(displayed)); self._selectors.clear()
        for row, asset in enumerate(displayed):
            match = self._matches.get(asset.stable_id, PEAAssetMatch(asset.stable_id))
            nearest = match.candidates[0] if match.candidates else None
            values = (
                "", asset.source_provider, asset.asset_type.value,
                asset.source_asset_id or "(missing)", asset.name or "",
                "" if asset.latitude is None else f"{asset.latitude:.7f}",
                "" if asset.longitude is None else f"{asset.longitude:.7f}",
                nearest.pole_id if nearest else "", f"{nearest.distance_metres:.2f}" if nearest else "",
                nearest.pole_order if nearest and nearest.pole_order is not None else "",
                match.state.value,
                nearest.side_relation.value.replace("_", " ") if nearest else "uncertain",
                "; ".join(asset.qc_warnings), "",
            )
            for column, value in enumerate(values):
                if column == 0:
                    checkbox = QCheckBox(); checkbox.setChecked(match.included)
                    checkbox.toggled.connect(lambda enabled, key=asset.stable_id: self._set_included(key, enabled))
                    self.table.setCellWidget(row, column, checkbox)
                elif column != 13:
                    item = QTableWidgetItem(str(value))
                    if column == 3: item.setData(Qt.ItemDataRole.UserRole, asset.stable_id)
                    self.table.setItem(row, column, item)
            selector = QComboBox(); selector.addItem("Unmatched", None)
            for candidate in match.candidates:
                suffix = " [excluded]" if candidate.pole_included is False else ""
                selector.addItem(
                    f"{candidate.pole_id} — {candidate.distance_metres:.2f} m "
                    f"[{candidate.strength}]{suffix}",
                    candidate.pole_source_key,
                )
            selected = match.confirmed_pole_key or match.suggested_pole_key
            index = selector.findData(selected)
            selector.setCurrentIndex(max(0, index))
            self.table.setCellWidget(row, 13, selector); self._selectors[asset.stable_id] = selector
        self.table.resizeColumnsToContents()

    def _set_included(self, key, enabled):
        self._matches[key] = replace(self._matches[key], included=enabled)

    def _confirm_selected(self):
        key = self._selected_asset_id()
        if key:
            pole_key = self._selectors[key].currentData()
            if pole_key:
                self._matches[key] = self._matches[key].confirm(pole_key)
                self._refresh()

    def _clear_selected(self):
        key = self._selected_asset_id()
        if key:
            self._matches[key] = self._matches[key].clear(); self._refresh()

    def _recompute(self):
        computed = match_pea_assets(
            self._assets,
            self._poles,
            self._ordering,
            tuple(self._matches.values()),
            main_route=self._main_route,
        )
        self._matches = {item.asset_id: item for item in computed}; self._refresh()
