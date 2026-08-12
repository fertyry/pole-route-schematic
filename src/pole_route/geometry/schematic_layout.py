"""Create selectable non-scale schematic pole layouts."""

from enum import StrEnum

from pole_route.domain.pole import PoleSide
from pole_route.domain.schematic import SchematicLayout, SchematicPole
from pole_route.geometry.road_geometry import RoadGeometry

DEFAULT_POLE_SPACING = 150.0
ROAD_HALF_HEIGHT = 36.0
POLE_DISTANCE_FROM_EDGE = 72.0
HORIZONTAL_MARGIN = 120.0
VERTICAL_CENTER = 250.0
PROJECTED_LAYOUT_LENGTH = 1200.0


class PoleSpacingMode(StrEnum):
    EQUAL = "equal"
    PROJECTED_STATION = "projected_station"


def create_schematic_layout(
    geometry: RoadGeometry,
    spacing_mode: PoleSpacingMode = PoleSpacingMode.EQUAL,
) -> SchematicLayout:
    """Order poles by route station and apply the selected visual spacing."""
    ordered = sorted(
        geometry.projected_poles,
        key=lambda item: (geometry.centerline.project(item.original), item.pole.number),
    )
    pole_count = len(ordered)
    if spacing_mode is PoleSpacingMode.EQUAL:
        content_length = max(pole_count - 1, 0) * DEFAULT_POLE_SPACING
    else:
        content_length = PROJECTED_LAYOUT_LENGTH if pole_count > 1 else 0.0
    road_length = max(760.0, content_length + 240.0)
    width = road_length + 2 * HORIZONTAL_MARGIN
    road_left = HORIZONTAL_MARGIN
    road_right = width - HORIZONTAL_MARGIN
    road_top = VERTICAL_CENTER - ROAD_HALF_HEIGHT
    road_bottom = VERTICAL_CENTER + ROAD_HALF_HEIGHT
    first_x = (width - content_length) / 2
    if ordered:
        stations = [geometry.centerline.project(item.original) for item in ordered]
        station_min = min(stations)
        station_span = max(max(stations) - station_min, 1e-9)
    else:
        stations = []
        station_span = 1.0

    poles = []
    for index, projected in enumerate(ordered):
        side = projected.pole.side
        y = (
            road_top - POLE_DISTANCE_FROM_EDGE
            if side is PoleSide.LEFT
            else road_bottom + POLE_DISTANCE_FROM_EDGE
        )
        poles.append(
            SchematicPole(
                projected.pole.number,
                projected.pole.detail,
                side,
                (
                    first_x + index * DEFAULT_POLE_SPACING
                    if spacing_mode is PoleSpacingMode.EQUAL
                    else first_x + ((stations[index] - station_min) / station_span) * content_length
                ),
                y,
                geometry.centerline.project(projected.original),
            )
        )

    return SchematicLayout(
        width,
        500.0,
        road_left,
        road_right,
        road_top,
        road_bottom,
        tuple(poles),
    )
