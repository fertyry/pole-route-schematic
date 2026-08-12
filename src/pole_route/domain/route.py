"""Route data contract for future KML/KMZ import work."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Route:
    """A named road-centerline source awaiting geometry implementation."""

    name: str
    source_path: str

