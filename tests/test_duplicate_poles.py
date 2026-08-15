from pole_route.domain.pole import Pole
from pole_route.ui.duplicate_pole_dialog import find_close_pole_groups


def test_find_close_pole_groups_detects_duplicate_coordinates() -> None:
    poles = [
        Pole("6", 13.811239, 100.650823),
        Pole("7", 13.811239, 100.650823),
        Pole("8", 13.811315, 100.650858),
    ]

    assert find_close_pole_groups(poles) == [(0, 1)]


def test_find_close_pole_groups_uses_connected_nearby_records() -> None:
    poles = [
        Pole("A", 13.0, 100.0),
        Pole("B", 13.000003, 100.0),
        Pole("C", 13.000006, 100.0),
    ]

    assert find_close_pole_groups(poles, tolerance_metres=0.5) == [(0, 1, 2)]
