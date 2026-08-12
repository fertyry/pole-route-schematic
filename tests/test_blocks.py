import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsScene

from pole_route.domain.blocks import BLOCK_CATALOG, BlockType
from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.road_geometry import build_road_geometry
from pole_route.geometry.schematic_layout import create_schematic_layout
from pole_route.ui.block_renderer import create_block_item
from pole_route.ui.drawing_view import DrawingMode, DrawingView, nearest_road_point
from pole_route.ui.editor_commands import AddItemCommand
from pole_route.ui.schematic_renderer import render_schematic


@pytest.mark.parametrize("definition", BLOCK_CATALOG)
def test_catalog_blocks_create_semantic_editable_groups(definition, qapp) -> None:
    stack = QUndoStack()
    item = create_block_item(
        definition.type,
        QPointF(100, 200),
        QPointF(300, 120),
        stack,
    )

    assert item.data(0) == "block"
    assert item.data(1) == definition.type.value
    assert item.data(3) == (100.0, 200.0)
    assert item.data(4) == (300.0, 120.0)
    assert item.childItems()
    assert item.flags() & item.GraphicsItemFlag.ItemIsSelectable
    assert item.flags() & item.GraphicsItemFlag.ItemIsMovable


@pytest.mark.parametrize(
    "block_type",
    [BlockType.SIDE_ROAD, BlockType.T_JUNCTION, BlockType.CROSSROAD],
)
def test_junction_blocks_include_non_destructive_mouth_mask(block_type, qapp) -> None:
    item = create_block_item(
        block_type,
        QPointF(100, 200),
        QPointF(300, 120),
        QUndoStack(),
    )

    masks = [child for child in item.childItems() if isinstance(child, QGraphicsEllipseItem)]
    assert len(masks) == 1


def test_block_creation_is_undoable(qapp) -> None:
    scene = QGraphicsScene()
    stack = QUndoStack()
    item = create_block_item(
        BlockType.SIDE_ROAD,
        QPointF(100, 200),
        QPointF(300, 120),
        stack,
    )
    scene.addItem(item)

    stack.push(AddItemCommand(scene, item))
    stack.undo()
    assert item.scene() is None
    stack.redo()
    assert item.scene() is scene


def test_block_anchor_snaps_to_nearest_main_road(qapp) -> None:
    route = Route("Road", "route.kml", (GeoPoint(100, 13), GeoPoint(100.01, 13)))
    poles = [Pole("P1", 13.0001, 100.005, side=PoleSide.LEFT)]
    geometry = build_road_geometry(route, poles, 6, 2)
    layout = create_schematic_layout(geometry)
    scene = QGraphicsScene()
    render_schematic(scene, layout, QUndoStack())

    road = next(item for item in scene.items() if item.data(0) == "road")
    road_line = road.childItems()[0]
    midpoint = road_line.mapToScene(road_line.line().pointAt(0.5))
    candidate = QPointF(midpoint.x() + 8, midpoint.y() + 6)
    snapped = nearest_road_point(scene, candidate, 28)

    assert snapped is not None
    assert snapped.y() == pytest.approx(midpoint.y())


def test_crossroad_extends_on_both_sides_of_anchor(qapp) -> None:
    item = create_block_item(
        BlockType.CROSSROAD,
        QPointF(100, 100),
        QPointF(200, 100),
        QUndoStack(),
    )
    child_bounds = item.childrenBoundingRect()

    assert child_bounds.left() < 100
    assert child_bounds.right() > 100


def test_block_mode_starts_without_creating_zero_length_item(qtbot) -> None:
    scene = QGraphicsScene()
    view = DrawingView(scene, QUndoStack())
    qtbot.addWidget(view)

    view.set_block_mode(BlockType.SIDE_ROAD)

    assert view.mode is DrawingMode.BLOCK
    assert not scene.items()
