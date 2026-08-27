"""Read and update PoleRoute-owned geometry in a locked AutoCAD drawing."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, sin
from typing import Iterable, Protocol

from shapely.geometry import LineString, Point

from pole_route.domain.physical_pole import PhysicalPoleMapping
from pole_route.geometry.road_geometry import RoadNetworkGeometry


class CadReadbackError(RuntimeError):
    """The locked drawing cannot safely satisfy a requested CAD operation."""


@dataclass(frozen=True, slots=True)
class SimilarityTransform:
    """A validated 2D scale/rotation/translation transform."""

    scale: float
    rotation_radians: float
    translate_x: float
    translate_y: float

    @classmethod
    def from_control_points(
        cls,
        source_start: tuple[float, float],
        source_end: tuple[float, float],
        target_start: tuple[float, float],
        target_end: tuple[float, float],
    ) -> "SimilarityTransform":
        sx, sy = source_end[0] - source_start[0], source_end[1] - source_start[1]
        tx, ty = target_end[0] - target_start[0], target_end[1] - target_start[1]
        source_length, target_length = hypot(sx, sy), hypot(tx, ty)
        if source_length <= 1e-9 or target_length <= 1e-9:
            raise CadReadbackError("Two distinct start/end calibration points are required.")
        scale = target_length / source_length
        angle = atan2(ty, tx) - atan2(sy, sx)
        c, s = cos(angle), sin(angle)
        mapped_x = scale * (source_start[0] * c - source_start[1] * s)
        mapped_y = scale * (source_start[0] * s + source_start[1] * c)
        return cls(scale, angle, target_start[0] - mapped_x, target_start[1] - mapped_y)

    def apply(self, point: tuple[float, float]) -> tuple[float, float]:
        c, s = cos(self.rotation_radians), sin(self.rotation_radians)
        return (
            self.scale * (point[0] * c - point[1] * s) + self.translate_x,
            self.scale * (point[0] * s + point[1] * c) + self.translate_y,
        )

    def inverse(self, point: tuple[float, float]) -> tuple[float, float]:
        if self.scale <= 0:
            raise CadReadbackError("Calibration scale must be positive.")
        x = (point[0] - self.translate_x) / self.scale
        y = (point[1] - self.translate_y) / self.scale
        c, s = cos(self.rotation_radians), sin(self.rotation_radians)
        return (x * c + y * s, -x * s + y * c)


@dataclass(frozen=True, slots=True)
class CadManagedPole:
    block_name: str
    source_ids: tuple[str, ...]
    physical_ids: tuple[str, ...]
    p_labels: tuple[str, ...]
    x: float
    y: float
    rotation_degrees: float = 0.0


class CadGateway(Protocol):
    def polylines(self, layer: str) -> tuple[tuple[tuple[float, float], ...], ...]: ...
    def managed_poles(self) -> tuple[CadManagedPole, ...]: ...
    def replace_managed_poles(self, poles: tuple[CadManagedPole, ...]) -> None: ...


def read_latest_route(gateway: CadGateway) -> tuple[tuple[float, float], ...]:
    routes = gateway.polylines("MAIN_CENTERLINE")
    if not routes:
        raise CadReadbackError("The locked drawing has no MAIN_CENTERLINE polyline.")
    return max(routes, key=_polyline_length)


def read_latest_pole_offset(gateway: CadGateway) -> tuple[tuple[float, float], ...]:
    offsets = gateway.polylines("POLE_OFFSET")
    if not offsets:
        raise CadReadbackError("The locked drawing has no POLE_OFFSET polyline.")
    return max(offsets, key=_polyline_length)


def update_managed_poles(
    gateway: CadGateway, poles: Iterable[CadManagedPole]
) -> tuple[CadManagedPole, ...]:
    """Atomically replace only PRS-owned pole entities after validating the plan."""
    planned = tuple(poles)
    identities: set[str] = set()
    for pole in planned:
        if pole.block_name not in {"PRS_POLE", "PRS_TRANSFORMER_RACK"}:
            raise CadReadbackError(f"Unsupported managed pole block: {pole.block_name}")
        if not pole.physical_ids or any(not value for value in pole.physical_ids):
            raise CadReadbackError("Every managed pole requires a canonical physical identity.")
        overlap = identities.intersection(pole.physical_ids)
        if overlap:
            raise CadReadbackError(
                "Duplicate physical pole identity in update plan: " + ", ".join(sorted(overlap))
            )
        identities.update(pole.physical_ids)
    gateway.replace_managed_poles(planned)
    return planned


def read_managed_pole_positions(gateway: CadGateway) -> dict[str, tuple[float, float]]:
    """Return one CAD position per canonical physical identity."""
    result: dict[str, tuple[float, float]] = {}
    for pole in gateway.managed_poles():
        for physical_id in pole.physical_ids:
            if physical_id in result:
                raise CadReadbackError(
                    f"Physical pole identity appears more than once in CAD: {physical_id}"
                )
            result[physical_id] = (pole.x, pole.y)
    return result


def build_pole_overlay_plan(
    geometry: RoadNetworkGeometry,
    mapping: PhysicalPoleMapping,
    pole_offset: tuple[tuple[float, float], ...],
) -> tuple[CadManagedPole, ...]:
    """Build one stable CAD insert per canonical physical pole/rack.

    Source work records remain attached to their physical object.  Accessory-only
    records therefore contribute metadata but never create another pole insert.
    """
    if len(pole_offset) < 2:
        raise CadReadbackError("POLE_OFFSET requires at least two CAD points.")
    offset = LineString(pole_offset)
    if offset.length <= 1e-9:
        raise CadReadbackError("POLE_OFFSET has zero length.")
    projected_by_source = {
        item.pole.number: item for item in geometry.projected_poles
    }
    groups: dict[tuple[str, str], list] = {}
    for assignment in mapping.assignments:
        if assignment.transformer_rack_id:
            key = ("rack", assignment.transformer_rack_id)
        elif assignment.physical_pole_id:
            key = ("pole", assignment.physical_pole_id)
        else:
            # Accessory-only records without a physical parent cannot be drawn.
            continue
        groups.setdefault(key, []).append(assignment)

    planned = []
    for (kind, _identity), assignments in groups.items():
        source_items = [
            projected_by_source[item.source_pole_id]
            for item in assignments
            if item.source_pole_id in projected_by_source
        ]
        physical_items = [
            projected_by_source[item.physical_pole_id]
            for item in assignments
            if item.physical_pole_id in projected_by_source
        ]
        anchors = physical_items or source_items
        if not anchors:
            continue
        source_point = Point(
            sum(item.original.x for item in anchors) / len(anchors),
            sum(item.original.y for item in anchors) / len(anchors),
        )
        station = offset.project(source_point)
        snapped = offset.interpolate(station)
        planned.append(
            CadManagedPole(
                "PRS_TRANSFORMER_RACK" if kind == "rack" else "PRS_POLE",
                tuple(item.source_pole_id for item in assignments),
                tuple(dict.fromkeys(
                    item.physical_pole_id for item in assignments
                    if item.physical_pole_id is not None
                )),
                tuple(dict.fromkeys(
                    item.p_label for item in assignments if item.p_label is not None
                )),
                float(snapped.x),
                float(snapped.y),
                _line_angle_degrees(offset, station),
            )
        )
    return tuple(planned)


def _polyline_length(points: tuple[tuple[float, float], ...]) -> float:
    return sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def _line_angle_degrees(line: LineString, station: float) -> float:
    distance = min(max(line.length * 0.001, 0.05), line.length / 2.0)
    before = line.interpolate(max(0.0, station - distance))
    after = line.interpolate(min(line.length, station + distance))
    return degrees(atan2(after.y - before.y, after.x - before.x))
