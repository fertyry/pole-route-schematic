"""Pole data used by imports and the user interface."""

from dataclasses import dataclass
from enum import StrEnum


class PoleSide(StrEnum):
    """Supported pole positions relative to the route direction."""

    LEFT = "Left"
    RIGHT = "Right"
    UNKNOWN = "Unknown"

    @classmethod
    def from_text(cls, value: object) -> "PoleSide":
        normalized = str(value or "").strip().casefold()
        aliases = {
            "left": cls.LEFT,
            "l": cls.LEFT,
            "ซ้าย": cls.LEFT,
            "right": cls.RIGHT,
            "r": cls.RIGHT,
            "ขวา": cls.RIGHT,
            "": cls.UNKNOWN,
            "unknown": cls.UNKNOWN,
        }
        if normalized not in aliases:
            raise ValueError(f"unsupported Side value: {value!r}")
        return aliases[normalized]


@dataclass(frozen=True, slots=True)
class Pole:
    """A utility pole at its source geographic coordinate."""

    number: str
    latitude: float
    longitude: float
    detail: str = ""
    side: PoleSide = PoleSide.UNKNOWN

    def __post_init__(self) -> None:
        if not self.number.strip():
            raise ValueError("Pole No. is required")
        if not -90 <= self.latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180")

