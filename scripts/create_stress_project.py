"""Create a local high-volume project from an existing PoleRoute project."""

from __future__ import annotations

import argparse

from PySide6.QtWidgets import QApplication, QGraphicsScene
from shapely.geometry import LineString

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import RouteType
from pole_route.geometry.road_geometry import build_road_network_geometry
from pole_route.project.storage import (
    load_project_file,
    poles_to_data,
    routes_from_data,
    routes_to_data,
    save_project_file,
    scene_to_data,
)
from pole_route.ui.geometry_renderer import render_road_geometry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    if args.count < 1:
        raise ValueError("count must be at least 1")

    source = load_project_file(args.source)
    routes = routes_from_data(source["routes"])
    main_route = next(item.route for item in routes if item.type is RouteType.MAIN_ROUTE)
    geographic_line = LineString(
        (point.longitude, point.latitude) for point in main_route.points
    )
    poles = []
    for index in range(args.count):
        ratio = (index + 0.5) / args.count
        point = geographic_line.interpolate(ratio, normalized=True)
        poles.append(
            Pole(
                f"TEST-{index + 1:04d}",
                point.y,
                point.x,
                f"Stress test pole {index + 1}",
                PoleSide.LEFT if index % 2 == 0 else PoleSide.RIGHT,
            )
        )

    geometry = build_road_network_geometry(routes, poles)
    app = QApplication.instance() or QApplication([])
    scene = QGraphicsScene()
    render_road_geometry(scene, geometry)
    save_project_file(
        args.destination,
        {
            "routes": routes_to_data(routes),
            "poles": poles_to_data(poles),
            "same_pole_groups": [],
            "canvas": scene_to_data(scene),
            "workspace_note": (
                f"Synthetic stress-test metric preview with {args.count} poles."
            ),
            "has_schematic": False,
        },
    )
    print(
        f"Created {args.destination}: {len(routes)} routes, {len(poles)} poles, "
        f"{len(scene.items())} canvas items"
    )
    del app


if __name__ == "__main__":
    main()
