"""Review pole records whose source coordinates are identical or nearly identical."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pole_route.domain.pole import Pole

SAME_POLE = "same_pole"
TRANSFORMER_RACK = "transformer_rack"
SEPARATE_POLES = "separate_poles"
ACCESSORY = "accessory"

CHOICES = (
    ("One physical pole / multiple work items", SAME_POLE),
    ("Transformer rack / two physical poles", TRANSFORMER_RACK),
    ("Separate poles / coordinates need correction", SEPARATE_POLES),
    ("Accessory record on one physical pole", ACCESSORY),
)


def find_close_pole_groups(poles: list[Pole], tolerance_metres: float = 0.5) -> list[tuple[int, ...]]:
    """Return connected groups of records at or within the review tolerance."""
    parents = list(range(len(poles)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def join(left: int, right: int) -> None:
        left_root, right_root = root(left), root(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left in range(len(poles)):
        for right in range(left + 1, len(poles)):
            if _distance_metres(poles[left], poles[right]) <= tolerance_metres:
                join(left, right)
    groups: dict[int, list[int]] = {}
    for index in range(len(poles)):
        groups.setdefault(root(index), []).append(index)
    return [tuple(group) for group in groups.values() if len(group) > 1]


class DuplicatePoleDialog(QDialog):
    """Require an explicit physical interpretation for close pole records."""

    def __init__(self, poles: list[Pole], groups: list[tuple[int, ...]], parent=None) -> None:
        super().__init__(parent)
        self._poles = poles
        self._groups = groups
        self._choices: list[QComboBox] = []
        self.setWindowTitle("Review duplicate pole coordinates")
        self.resize(900, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "These records share the same or a very close coordinate. Choose what they "
            "represent physically; installed quantity alone does not determine pole count."
        ))
        table = QTableWidget(len(groups), 4)
        table.setHorizontalHeaderLabels(("Records", "Maximum separation", "Interpretation", "Result"))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for row, group in enumerate(groups):
            records = [poles[index] for index in group]
            table.setItem(row, 0, QTableWidgetItem(" / ".join(pole.number for pole in records)))
            maximum = max(
                (_distance_metres(left, right) for left in records for right in records),
                default=0.0,
            )
            table.setItem(row, 1, QTableWidgetItem(f"{maximum:.2f} m"))
            combo = QComboBox()
            for label, value in CHOICES:
                combo.addItem(label, value)
            if len(records) == 2 and any("/1" in pole.number for pole in records):
                combo.setCurrentIndex(1)
            combo.currentIndexChanged.connect(lambda _index, r=row: self._update_result(table, r))
            table.setCellWidget(row, 2, combo)
            self._choices.append(combo)
            self._update_result(table, row)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm pole interpretation")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def decisions(self) -> list[tuple[frozenset[str], str]]:
        return [
            (frozenset(self._poles[index].number for index in group), combo.currentData())
            for group, combo in zip(self._groups, self._choices, strict=True)
        ]

    def _update_result(self, table: QTableWidget, row: int) -> None:
        result = {
            SAME_POLE: "Draw one pole marker and keep every work-item label.",
            TRANSFORMER_RACK: "Draw two pole markers with a connecting rack symbol.",
            SEPARATE_POLES: "Keep separate markers and flag the source coordinates for correction.",
            ACCESSORY: "Draw one pole marker; retain the extra record as attached work.",
        }[self._choices[row].currentData()]
        item = QTableWidgetItem(result)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, 3, item)


def _distance_metres(left: Pole, right: Pole) -> float:
    radius = 6_371_008.8
    lat1, lat2 = radians(left.latitude), radians(right.latitude)
    dlat = lat2 - lat1
    dlon = radians(right.longitude - left.longitude)
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(min(1.0, value)))
