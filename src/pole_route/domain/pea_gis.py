"""Source-preserving PEA GIS records and reusable review predicates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class PEAPoleRecord:
    """A DS_Pole row normalized without losing its source audit values."""

    source_id: str
    source_sheet: str
    source_row: int
    latitude: float
    longitude: float
    raw_height: Any = None
    height_metres: float | None = None
    raw_voltage: Any = None
    voltage_min_kv: float | None = None
    voltage_max_kv: float | None = None
    raw_attributes: Mapping[str, Any] = field(default_factory=dict)
    included_by_default: bool = False
    qc_warnings: tuple[str, ...] = ()

    @property
    def source_key(self) -> str:
        """Stable identity for review, persistence, and deterministic sorting."""
        return f"{self.source_sheet}:{self.source_row}:{self.source_id}"


@dataclass(frozen=True, slots=True)
class VoltageFilter:
    """Extensible voltage-band predicate for the later review UI."""

    minimum_kv: float | None = None
    maximum_kv: float | None = None

    def matches(self, record: PEAPoleRecord) -> bool:
        if record.voltage_min_kv is None or record.voltage_max_kv is None:
            return False
        if self.minimum_kv is not None and record.voltage_max_kv < self.minimum_kv:
            return False
        if self.maximum_kv is not None and record.voltage_min_kv > self.maximum_kv:
            return False
        return True
