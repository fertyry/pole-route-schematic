"""Review pole records whose source coordinates are identical or nearly identical."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
        self._rack_pole_a: list[QComboBox] = []
        self._rack_pole_b: list[QComboBox] = []
        self.setWindowTitle("Review duplicate pole coordinates")
        self.resize(1180, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "These records share the same or a very close coordinate. Choose what they "
            "represent physically; installed quantity alone does not determine pole count."
        ))
        table = QTableWidget(len(groups), 8)
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setHorizontalHeaderLabels((
            "Records",
            "Pole No. / Detail",
            "Installed Qty.",
            "Maximum separation",
            "Interpretation",
            "Rack Pole A",
            "Rack Pole B",
            "Result",
        ))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        for row, group in enumerate(groups):
            records = [poles[index] for index in group]
            table.setItem(row, 0, QTableWidgetItem(" / ".join(pole.number for pole in records)))
            table.setItem(
                row,
                1,
                QTableWidgetItem(
                    " / ".join(pole.detail or pole.number for pole in records)
                ),
            )
            table.setItem(
                row,
                2,
                QTableWidgetItem(" / ".join(str(pole.installed_quantity) for pole in records)),
            )
            maximum = max(
                (_distance_metres(left, right) for left in records for right in records),
                default=0.0,
            )
            table.setItem(row, 3, QTableWidgetItem(f"{maximum:.2f} m"))
            combo = QComboBox()

            for label, value in CHOICES:
                combo.addItem(label, value)

            rack_a = QComboBox()
            rack_b = QComboBox()

            # Default: not applicable unless this row is a transformer rack.
            rack_a.addItem("-", None)
            rack_b.addItem("-", None)

            for pole in records:
                rack_a.addItem(pole.number, pole.number)
                rack_b.addItem(pole.number, pole.number)

            rack_a.setEnabled(False)
            rack_b.setEnabled(False)

            table.setCellWidget(row, 5, rack_a)
            table.setCellWidget(row, 6, rack_b)

            self._rack_pole_a.append(rack_a)
            self._rack_pole_b.append(rack_b)

            combo.currentIndexChanged.connect(
                lambda _index, r=row: self._update_result(table, r)
            )

            table.setCellWidget(row, 4, combo)
            self._choices.append(combo)

            self._update_result(table, row)
        table.clearSelection()
        table.setCurrentItem(None)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm pole interpretation")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def decisions(
        self,
    ) -> list[tuple[frozenset[str], str, tuple[str, str] | None]]:
        results = []

        for group, combo, rack_a, rack_b in zip(
            self._groups,
            self._choices,
            self._rack_pole_a,
            self._rack_pole_b,
            strict=True,
        ):
            members = frozenset(
                self._poles[index].number
                for index in group
            )

            decision = combo.currentData()

            rack_pair = None

            if decision == TRANSFORMER_RACK:
                pole_a = rack_a.currentData()
                pole_b = rack_b.currentData()

                if pole_a != pole_b:
                    rack_pair = (pole_a, pole_b)

            results.append(
                (
                    members,
                    decision,
                    rack_pair,
                )
            )

        return results

    def accept(self) -> None:
        """Reject incomplete or ambiguous transformer-rack leg selections."""
        for row, (group, choice, rack_a, rack_b) in enumerate(zip(
            self._groups,
            self._choices,
            self._rack_pole_a,
            self._rack_pole_b,
            strict=True,
        )):
            if choice.currentData() != TRANSFORMER_RACK:
                continue
            members = {self._poles[index].number for index in group}
            pole_a, pole_b = rack_a.currentData(), rack_b.currentData()
            if pole_a is None or pole_b is None or pole_a == pole_b:
                rack_a.setFocus()
                return
            if pole_a not in members or pole_b not in members:
                rack_a.setFocus()
                return
        super().accept()

    def _update_result(self, table: QTableWidget, row: int) -> None:
        decision = self._choices[row].currentData()

        is_rack = decision == TRANSFORMER_RACK

        self._rack_pole_a[row].setEnabled(is_rack)
        self._rack_pole_b[row].setEnabled(is_rack)
        
        rack_a = self._rack_pole_a[row]
        rack_b = self._rack_pole_b[row]

        if is_rack:
            if rack_a.currentData() is None and rack_a.count() >= 3:
                rack_a.setCurrentIndex(1)
                rack_b.setCurrentIndex(2)
        else:
            rack_a.setCurrentIndex(0)
            rack_b.setCurrentIndex(0)

        result = {
            SAME_POLE: "Draw one pole marker and keep every work-item label.",
            TRANSFORMER_RACK: (
                "Draw two physical rack poles. Select Rack Pole A and Rack Pole B."
            ),
            SEPARATE_POLES: (
                "Keep separate markers and flag the source coordinates for correction."
            ),
            ACCESSORY: (
                "Draw one pole marker; retain the extra record as attached work."
            ),
        }[decision]

        item = QTableWidgetItem(result)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, 7, item)


def _distance_metres(left: Pole, right: Pole) -> float:
    radius = 6_371_008.8
    lat1, lat2 = radians(left.latitude), radians(right.latitude)
    dlat = lat2 - lat1
    dlon = radians(right.longitude - left.longitude)
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(min(1.0, value)))
