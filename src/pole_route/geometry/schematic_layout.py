"""Create a deliberately non-scale, uniformly spaced schematic layout."""

from pole_route.domain.pole import PoleSide
from pole_route.domain.schematic import SchematicLayout, SchematicPole
from pole_route.geometry.road_geometry import RoadGeometry

DEFAULT_POLE_SPACING = 150.0
ROAD_HALF_HEIGHT = 36.0
POLE_DISTANCE_FROM_EDGE = 72.0
HORIZONTAL_MARGIN = 120.0
VERTICAL_CENTER = 250.0


def create_schematic_layout(geometry: RoadGeometry) -> SchematicLayout:
    """Order poles by source station and place them at equal visual spacing."""
    ordered = sorted(
        geometry.projected_poles,
        key=lambda item: (geometry.centerline.project(item.original), item.pole.number),
    )
    pole_count = len(ordered)
    road_length = max(760.0, (max(pole_count - 1, 0) * DEFAULT_POLE_SPACING) + 240.0)
    width = road_length + 2 * HORIZONTAL_MARGIN
    road_left = HORIZONTAL_MARGIN
    road_right = width - HORIZONTAL_MARGIN
    road_top = VERTICAL_CENTER - ROAD_HALF_HEIGHT
    road_bottom = VERTICAL_CENTER + ROAD_HALF_HEIGHT
    first_x = (width - max(pole_count - 1, 0) * DEFAULT_POLE_SPACING) / 2

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
                first_x + index * DEFAULT_POLE_SPACING,
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

