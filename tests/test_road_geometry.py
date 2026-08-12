import pytest

from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.road_geometry import RoadGeometryError, build_road_geometry


def test_builds_road_and_pole_offsets_in_metres() -> None:
    route = Route(
        "Eastbound",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )

    geometry = build_road_geometry(route, [], road_width_metres=6.0, pole_offset_metres=2.0)

    assert geometry.centerline.distance(geometry.left_edge) == pytest.approx(3.0, abs=0.02)
    assert geometry.centerline.distance(geometry.right_edge) == pytest.approx(3.0, abs=0.02)
    assert geometry.centerline.distance(geometry.left_pole_line) == pytest.approx(5.0, abs=0.02)
    assert geometry.centerline.distance(geometry.right_pole_line) == pytest.approx(5.0, abs=0.02)
    assert "UTM zone 47N" in geometry.projection.name


def test_projects_poles_to_their_selected_side() -> None:
    route = Route(
        "Road",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )
    poles = [
        Pole("L-1", 13.0001, 100.005, side=PoleSide.LEFT),
        Pole("R-1", 12.9999, 100.006, side=PoleSide.RIGHT),
        Pole("U-1", 13.0, 100.007, side=PoleSide.UNKNOWN),
    ]

    geometry = build_road_geometry(route, poles, 6.0, 2.0)

    assert [item.pole.number for item in geometry.projected_poles] == ["L-1", "R-1"]
    assert [pole.number for pole in geometry.unplaced_poles] == ["U-1"]
    left, right = geometry.projected_poles
    assert left.snapped.distance(geometry.left_pole_line) < 1e-8
    assert right.snapped.distance(geometry.right_pole_line) < 1e-8


@pytest.mark.parametrize(
    ("road_width", "pole_offset", "message"),
    [(0, 2, "Road width"), (6, -1, "Pole offset")],
)
def test_rejects_invalid_geometry_settings(road_width, pole_offset, message) -> None:
    route = Route("Road", "route.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)))

    with pytest.raises(RoadGeometryError, match=message):
        build_road_geometry(route, [], road_width, pole_offset)
