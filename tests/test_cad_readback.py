from dataclasses import dataclass, field

import pytest

from pole_route.cad.readback import (
    CadManagedPole,
    CadReadbackError,
    SimilarityTransform,
    build_pole_overlay_plan,
    read_latest_pole_offset,
    read_latest_route,
    read_managed_pole_positions,
    update_managed_poles,
)
from pole_route.domain.physical_pole import build_physical_pole_mapping
from pole_route.domain.pole import Pole, PoleSide
from pole_route.domain.route import ClassifiedRoute, GeoPoint, Route, RouteType
from pole_route.geometry.road_geometry import build_road_network_geometry


@dataclass
class FakeGateway:
    lines: dict[str, tuple] = field(default_factory=dict)
    poles: tuple[CadManagedPole, ...] = ()
    replace_count: int = 0

    def polylines(self, layer):
        return self.lines.get(layer, ())

    def managed_poles(self):
        return self.poles

    def replace_managed_poles(self, poles):
        self.poles = poles
        self.replace_count += 1


def test_two_point_calibration_round_trips_scale_rotation_translation() -> None:
    transform = SimilarityTransform.from_control_points((0, 0), (10, 0), (100, 200), (100, 220))
    mapped = transform.apply((5, 2))
    assert transform.inverse(mapped) == pytest.approx((5, 2))
    assert transform.scale == pytest.approx(2.0)


def test_calibration_rejects_incomplete_degenerate_control_points() -> None:
    with pytest.raises(CadReadbackError, match="distinct"):
        SimilarityTransform.from_control_points((0, 0), (0, 0), (1, 1), (2, 2))


def test_reads_longest_latest_route_and_pole_offset() -> None:
    gateway = FakeGateway({
        "MAIN_CENTERLINE": (((0, 0), (1, 0)), ((0, 0), (4, 0))),
        "POLE_OFFSET": (((0, 1), (3, 1)),),
    })
    assert read_latest_route(gateway) == ((0, 0), (4, 0))
    assert read_latest_pole_offset(gateway) == ((0, 1), (3, 1))


def test_update_is_idempotent_and_preserves_canonical_identity() -> None:
    gateway = FakeGateway()
    planned = (
        CadManagedPole("PRS_POLE", ("6", "7"), ("6",), ("P1",), 10, 20),
        CadManagedPole("PRS_TRANSFORMER_RACK", ("20", "20/1"), ("20", "20/1"), ("P2", "P3"), 30, 40),
    )
    update_managed_poles(gateway, planned)
    update_managed_poles(gateway, planned)
    assert gateway.poles == planned
    assert gateway.replace_count == 2
    assert read_managed_pole_positions(gateway) == {"6": (10, 20), "20": (30, 40), "20/1": (30, 40)}


def test_invalid_update_plan_never_calls_gateway() -> None:
    gateway = FakeGateway()
    with pytest.raises(CadReadbackError, match="Duplicate"):
        update_managed_poles(gateway, (
            CadManagedPole("PRS_POLE", ("1",), ("P1",), ("P1",), 0, 0),
            CadManagedPole("PRS_POLE", ("2",), ("P1",), ("P1",), 1, 0),
        ))
    assert gateway.replace_count == 0


def test_overlay_plan_snaps_canonical_poles_and_keeps_accessory_as_metadata() -> None:
    route = ClassifiedRoute(
        Route("main", "test.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.001, 13.0))),
        RouteType.MAIN_ROUTE,
        width_metres=6.0,
        pole_offset_metres=2.0,
    )
    poles = [
        Pole("1", 13.0001, 100.0002, "pole", PoleSide.LEFT),
        Pole("1A", 13.0001, 100.0002, "accessory", PoleSide.LEFT),
        Pole("2", 13.0001, 100.0007, "pole", PoleSide.LEFT),
    ]
    geometry = build_road_network_geometry([route], poles)
    mapping = build_physical_pole_mapping(
        ["1", "1A", "2"], (frozenset({"1", "1A"}),)
    )
    offset = tuple(geometry.roads[0].left_pole_line.coords)

    plan = build_pole_overlay_plan(geometry, mapping, offset)

    assert len(plan) == 2
    first = next(item for item in plan if item.physical_ids == ("1",))
    assert first.source_ids == ("1", "1A")
    assert first.p_labels == ("P1",)
    assert first.block_name == "PRS_POLE"


def test_overlay_plan_creates_one_explicit_transformer_rack_object() -> None:
    route = ClassifiedRoute(
        Route("main", "test.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.001, 13.0))),
        RouteType.MAIN_ROUTE,
        width_metres=6.0,
        pole_offset_metres=2.0,
    )
    poles = [
        Pole("6", 13.0001, 100.0005, side=PoleSide.LEFT),
        Pole("7", 13.0001, 100.00052, side=PoleSide.LEFT),
        Pole("TX", 13.0001, 100.00051, "transformer", PoleSide.LEFT),
    ]
    geometry = build_road_network_geometry([route], poles)
    rack = frozenset({"6", "7", "TX"})
    mapping = build_physical_pole_mapping(
        ["6", "7", "TX"], transformer_rack_groups=(rack,),
        transformer_rack_leg_pairs=(("6", "7"),),
    )

    plan = build_pole_overlay_plan(
        geometry, mapping, tuple(geometry.roads[0].left_pole_line.coords)
    )

    assert len(plan) == 1
    assert plan[0].block_name == "PRS_TRANSFORMER_RACK"
    assert plan[0].physical_ids == ("6", "7")
    assert plan[0].p_labels == ("P1", "P2")
    assert plan[0].source_ids == ("6", "7", "TX")
