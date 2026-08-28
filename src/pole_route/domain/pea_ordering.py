"""Review state and deterministic operations for PEA GIS pole ordering."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class PoleQCStatus(StrEnum):
    NORMAL = "Normal"
    REVIEW = "Review"
    STRONG_REVIEW = "Strong review"


@dataclass(frozen=True, slots=True)
class PoleOffsetQCPolicy:
    review_metres: float = 10.0
    strong_review_metres: float = 15.0

    def status(self, offset_metres: float) -> PoleQCStatus:
        if offset_metres > self.strong_review_metres:
            return PoleQCStatus.STRONG_REVIEW
        if offset_metres > self.review_metres:
            return PoleQCStatus.REVIEW
        return PoleQCStatus.NORMAL


@dataclass(frozen=True, slots=True)
class PEAPoleReviewEntry:
    source_key: str
    source_id: str
    station_metres: float
    offset_metres: float
    projected_latitude: float
    projected_longitude: float
    auto_order: int | None
    review_order: int | None
    confirmed_order: int | None
    included: bool
    qc_status: PoleQCStatus
    qc_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PEAPoleOrdering:
    entries: tuple[PEAPoleReviewEntry, ...]
    direction_reversed: bool = False
    manual_override: bool = False
    confirmed: bool = False

    def ordered_included(self) -> tuple[PEAPoleReviewEntry, ...]:
        return tuple(
            sorted(
                (entry for entry in self.entries if entry.included),
                key=lambda entry: (
                    entry.review_order if entry.review_order is not None else 10**9,
                    entry.source_key,
                ),
            )
        )

    def _renumber(self, entries: list[PEAPoleReviewEntry], *, manual: bool) -> "PEAPoleOrdering":
        included = sorted(
            (entry for entry in entries if entry.included),
            key=lambda entry: (
                entry.review_order if entry.review_order is not None else 10**9,
                entry.source_key,
            ),
        )
        order = {entry.source_key: index for index, entry in enumerate(included, 1)}
        return replace(
            self,
            entries=tuple(
                replace(entry, review_order=order.get(entry.source_key), confirmed_order=None)
                for entry in entries
            ),
            manual_override=manual,
            confirmed=False,
        )

    def move(self, source_key: str, delta: int) -> "PEAPoleOrdering":
        included = list(self.ordered_included())
        index = next((i for i, item in enumerate(included) if item.source_key == source_key), None)
        if index is None:
            return self
        target = max(0, min(len(included) - 1, index + delta))
        if target == index:
            return self
        included[index], included[target] = included[target], included[index]
        rank = {entry.source_key: i for i, entry in enumerate(included, 1)}
        return replace(
            self,
            entries=tuple(
                replace(entry, review_order=rank.get(entry.source_key), confirmed_order=None)
                for entry in self.entries
            ),
            manual_override=True,
            confirmed=False,
        )

    def set_included(self, source_key: str, included: bool) -> "PEAPoleOrdering":
        entries = [
            replace(entry, included=included) if entry.source_key == source_key else entry
            for entry in self.entries
        ]
        return self._renumber(entries, manual=True)

    def restore_auto_sort(self) -> "PEAPoleOrdering":
        entries = tuple(
            replace(
                entry,
                review_order=entry.auto_order if entry.included else None,
                confirmed_order=None,
            )
            for entry in self.entries
        )
        return replace(self, entries=entries, manual_override=False, confirmed=False)

    def confirm(self) -> "PEAPoleOrdering":
        return replace(
            self,
            entries=tuple(
                replace(entry, confirmed_order=entry.review_order if entry.included else None)
                for entry in self.entries
            ),
            confirmed=True,
        )
