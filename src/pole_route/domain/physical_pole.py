"""Canonical mapping from source work records to physical utility poles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class PhysicalPoleAssignment:
    """One source record's assignment to a visible physical-pole identity."""

    source_pole_id: str
    physical_pole_id: str | None
    p_label: str | None
    transformer_rack_id: str | None = None

    @property
    def display_label(self) -> str:
        return self.p_label or "-"


@dataclass(frozen=True, slots=True)
class PhysicalPoleMapping:
    """Stable, reusable assignments ordered by station along the Main Route."""

    assignments: tuple[PhysicalPoleAssignment, ...]

    def assignment_for(self, source_pole_id: str) -> PhysicalPoleAssignment:
        for assignment in self.assignments:
            if assignment.source_pole_id == source_pole_id:
                return assignment
        return PhysicalPoleAssignment(source_pole_id, source_pole_id, None)

    def label_for(self, source_pole_id: str) -> str:
        return self.assignment_for(source_pole_id).display_label


def build_physical_pole_mapping(
    ordered_source_ids: Iterable[str],
    same_pole_groups: Iterable[frozenset[str]] = (),
    transformer_rack_groups: Iterable[frozenset[str]] = (),
    transformer_rack_leg_pairs: Iterable[tuple[str, str]] = (),
) -> PhysicalPoleMapping:
    """Enumerate actual physical poles continuously as P1, P2, ... ."""
    ordered = tuple(dict.fromkeys(str(value) for value in ordered_source_ids))
    same_groups = tuple(same_pole_groups)
    rack_groups = tuple(transformer_rack_groups)
    rack_pairs = tuple(transformer_rack_leg_pairs)
    assignment_by_id: dict[str, PhysicalPoleAssignment] = {}
    next_number = 1

    for source_id in ordered:
        if source_id in assignment_by_id:
            continue
        rack_group = next((group for group in rack_groups if source_id in group), None)
        if rack_group is not None:
            pair = next(
                (pair for pair in rack_pairs if set(pair).issubset(rack_group)), None
            )
            rack_id = " / ".join(sorted(rack_group))
            if pair is None:
                for member in rack_group:
                    assignment_by_id[member] = PhysicalPoleAssignment(
                        member, None, None, rack_id
                    )
                continue
            for leg in pair:
                label = f"P{next_number}"
                next_number += 1
                assignment_by_id[leg] = PhysicalPoleAssignment(
                    leg, leg, label, rack_id
                )
            for member in rack_group:
                assignment_by_id.setdefault(
                    member, PhysicalPoleAssignment(member, None, None, rack_id)
                )
            continue

        same_group = next((group for group in same_groups if source_id in group), None)
        members = same_group or frozenset({source_id})
        physical_id = next((item for item in ordered if item in members), source_id)
        label = f"P{next_number}"
        next_number += 1
        for member in members:
            assignment_by_id[member] = PhysicalPoleAssignment(
                member, physical_id, label
            )

    assignments = tuple(
        assignment_by_id.get(item, PhysicalPoleAssignment(item, item, None))
        for item in ordered
    )
    return PhysicalPoleMapping(assignments)
