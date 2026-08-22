"""Distance-based route batches shared by online surroundings sources."""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString
from shapely.ops import substring

from pole_route.domain.route import Route
from pole_route.geometry.projection import MetricProjection

SURROUND_BATCH_METRES = 3000.0
SURROUND_BATCH_OVERLAP_METRES = 150.0


@dataclass(frozen=True, slots=True)
class RouteBatch:
    index: int
    count: int
    start_metres: float
    end_metres: float
    route: Route


def split_route_by_distance(
    route: Route,
    batch_metres: float = SURROUND_BATCH_METRES,
    overlap_metres: float = SURROUND_BATCH_OVERLAP_METRES,
) -> tuple[RouteBatch, ...]:
    """Split a route by metric length with overlap at internal boundaries."""
    if batch_metres <= 0:
        raise ValueError("Batch distance must be greater than zero")
    if overlap_metres < 0 or overlap_metres >= batch_metres:
        raise ValueError("Batch overlap must be non-negative and smaller than batch distance")
    projection = MetricProjection.for_points(route.points)
    line = LineString(projection.to_metric(point) for point in route.points)
    if line.length <= batch_metres:
        return (RouteBatch(1, 1, 0.0, line.length, route),)
    core_ranges: list[tuple[float, float]] = []
    start = 0.0
    while start < line.length:
        end = min(line.length, start + batch_metres)
        core_ranges.append((start, end))
        start = end
    count = len(core_ranges)
    batches: list[RouteBatch] = []
    for index, (core_start, core_end) in enumerate(core_ranges, 1):
        fetch_start = max(0.0, core_start - (overlap_metres if index > 1 else 0.0))
        fetch_end = min(
            line.length, core_end + (overlap_metres if index < count else 0.0)
        )
        part = substring(line, fetch_start, fetch_end)
        points = tuple(
            projection.to_geographic(float(x), float(y)) for x, y in part.coords
        )
        batches.append(RouteBatch(
            index, count, core_start, core_end,
            Route(f"{route.name} [{index}/{count}]", route.source_path, points),
        ))
    return tuple(batches)
