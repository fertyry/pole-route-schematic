from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.geometry.road_geometry import build_road_network_geometry
from pole_route.geometry.schematic_layout import create_schematic_layout
from pole_route.project.storage import (
    load_project_file,
    poles_from_data,
    poles_to_data,
    restore_scene,
    routes_from_data,
    routes_to_data,
    save_project_file,
    scene_to_data,
)
from pole_route.ui.editor_commands import EditableTextItem
from pole_route.ui.schematic_renderer import EDITABLE_FLAGS, render_schematic


def _project_inputs():
    routes = [
        ClassifiedRoute(
            Route(
                "Main",
                "original.kml",
                (GeoPoint(100, 13), GeoPoint(100.01, 13.01)),
            ),
            RouteType.MAIN_ROUTE,
            6.0,
            2.0,
        )
    ]
    poles = [Pole("P-1", 13.005, 100.005, "Transformer", PoleSide.RIGHT)]
    return routes, poles


def test_project_inputs_round_trip_without_source_files(tmp_path) -> None:
    routes, poles = _project_inputs()
    path = tmp_path / "portable.prs"

    save_project_file(
        path,
        {"routes": routes_to_data(routes), "poles": poles_to_data(poles)},
    )
    document = load_project_file(path)

    assert routes_from_data(document["routes"]) == routes
    assert poles_from_data(document["poles"]) == poles


def test_editable_canvas_round_trip_preserves_objects_and_positions(qapp) -> None:
    routes, poles = _project_inputs()
    source = QGraphicsScene()
    source_stack = QUndoStack()
    layout = create_schematic_layout(build_road_network_geometry(routes, poles))
    render_schematic(source, layout, source_stack)
    pole = next(item for item in source.items() if item.data(0) == "pole")
    pole.setPos(pole.pos() + QPointF(25, -10))
    note = EditableTextItem("Site note", source_stack)
    note.setData(0, "drawing")
    note.setData(2, QPointF(300, 200))
    note.setPos(300, 200)
    note.setFlags(EDITABLE_FLAGS)
    source.addItem(note)

    saved = scene_to_data(source)
    restored = QGraphicsScene()
    restore_scene(restored, saved, QUndoStack())

    roles = [item.data(0) for item in restored.items() if item.parentItem() is None]
    restored_pole = next(item for item in restored.items() if item.data(0) == "pole")
    restored_note = next(item for item in restored.items() if item.data(0) == "drawing")
    assert set(roles) >= {"road", "pole", "label", "drawing"}
    assert restored_pole.pos() == pole.pos()
    assert restored_note.pos() == QPointF(300, 200)
    assert restored.sceneRect() == source.sceneRect()
