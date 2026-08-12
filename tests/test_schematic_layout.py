import pytest
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.road_geometry import build_road_geometry
from pole_route.geometry.schematic_layout import (
    DEFAULT_POLE_SPACING,
    PoleSpacingMode,
    create_schematic_layout,
)
from pole_route.ui.schematic_renderer import render_schematic


def _geometry_with_irregular_poles():
    route = Route(
        "Road",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.02, 13.0)),
    )
    poles = [
        Pole("P-3", 13.0001, 100.018, side=PoleSide.LEFT),
        Pole("P-1", 13.0001, 100.001, side=PoleSide.LEFT),
        Pole("P-2", 12.9999, 100.004, side=PoleSide.RIGHT),
    ]
    return build_road_geometry(route, poles, 6.0, 2.0)


def test_schematic_orders_by_station_with_uniform_visual_spacing() -> None:
    layout = create_schematic_layout(_geometry_with_irregular_poles())

    assert [pole.number for pole in layout.poles] == ["P-1", "P-2", "P-3"]
    visual_spans = [
        layout.poles[index + 1].x - layout.poles[index].x
        for index in range(len(layout.poles) - 1)
    ]
    source_spans = [
        layout.poles[index + 1].source_station_metres - layout.poles[index].source_station_metres
        for index in range(len(layout.poles) - 1)
    ]
    assert visual_spans == [DEFAULT_POLE_SPACING, DEFAULT_POLE_SPACING]
    assert source_spans[0] != pytest.approx(source_spans[1])
    assert layout.poles[0].y < layout.road_top
    assert layout.poles[1].y > layout.road_bottom


def test_projected_station_spacing_preserves_relative_source_gaps() -> None:
    layout = create_schematic_layout(
        _geometry_with_irregular_poles(),
        PoleSpacingMode.PROJECTED_STATION,
    )
    visual_spans = [
        layout.poles[index + 1].x - layout.poles[index].x
        for index in range(len(layout.poles) - 1)
    ]
    source_spans = [
        layout.poles[index + 1].source_station_metres - layout.poles[index].source_station_metres
        for index in range(len(layout.poles) - 1)
    ]

    assert visual_spans[1] / visual_spans[0] == pytest.approx(
        source_spans[1] / source_spans[0], rel=1e-6
    )
    assert visual_spans[0] != pytest.approx(visual_spans[1])


def test_rendered_schematic_objects_are_selectable_and_movable(qapp) -> None:
    layout = create_schematic_layout(_geometry_with_irregular_poles())
    scene = QGraphicsScene()

    render_schematic(scene, layout, QUndoStack())

    typed_items = [item for item in scene.items() if item.data(0) in {"road", "pole", "label"}]
    assert len(typed_items) == 1 + len(layout.poles) * 2
    for item in typed_items:
        assert item.flags() & item.GraphicsItemFlag.ItemIsSelectable
        assert item.flags() & item.GraphicsItemFlag.ItemIsMovable
