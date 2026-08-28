from __future__ import annotations

import pytest

from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import PoleQCStatus
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.pea_linear_reference import reference_pea_poles


def _route() -> Route:
    return Route(
        "Main",
        "test.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )


def _record(source_id: str, row: int, longitude: float, latitude: float = 13.0, *, included=True):
    return PEAPoleRecord(
        source_id, "DS_Pole", row, latitude, longitude,
        included_by_default=included,
    )


def test_station_offset_projection_and_deterministic_order() -> None:
    records = [_record("B", 3, 100.008), _record("A", 2, 100.002)]
    ordering = reference_pea_poles(records, _route())

    assert [entry.source_id for entry in ordering.ordered_included()] == ["A", "B"]
    assert ordering.ordered_included()[0].station_metres < ordering.ordered_included()[1].station_metres
    assert ordering.ordered_included()[0].offset_metres == pytest.approx(0.0, abs=0.02)
    assert ordering.ordered_included()[0].projected_latitude == pytest.approx(13.0)


def test_offset_qc_thresholds_are_centralized() -> None:
    # At this latitude, roughly 0.0001 degree latitude is about 11 metres.
    review = reference_pea_poles([_record("A", 2, 100.005, 13.0001)], _route()).entries[0]
    strong = reference_pea_poles([_record("B", 3, 100.005, 13.0002)], _route()).entries[0]
    assert review.qc_status is PoleQCStatus.REVIEW
    assert strong.qc_status is PoleQCStatus.STRONG_REVIEW


def test_equal_station_uses_source_identity_and_marks_review() -> None:
    records = [_record("B", 3, 100.005), _record("A", 2, 100.005)]
    entries = reference_pea_poles(records, _route()).ordered_included()
    assert [entry.source_id for entry in entries] == ["A", "B"]
    assert all(entry.qc_status is PoleQCStatus.REVIEW for entry in entries)
    assert all("Equal or near-equal station" in entry.qc_reasons for entry in entries)


def test_manual_move_exclude_restore_and_confirm_are_durable_state() -> None:
    ordering = reference_pea_poles(
        [_record("A", 2, 100.002), _record("B", 3, 100.008)], _route()
    )
    moved = ordering.move(ordering.ordered_included()[1].source_key, -1)
    assert [entry.source_id for entry in moved.ordered_included()] == ["B", "A"]
    assert moved.manual_override
    excluded = moved.set_included(moved.ordered_included()[0].source_key, False)
    assert [entry.source_id for entry in excluded.ordered_included()] == ["A"]
    restored = excluded.set_included(next(e.source_key for e in excluded.entries if e.source_id == "B"), True)
    confirmed = restored.confirm()
    assert confirmed.confirmed
    assert [entry.confirmed_order for entry in confirmed.ordered_included()] == [1, 2]
    automatic = confirmed.restore_auto_sort()
    assert [entry.source_id for entry in automatic.ordered_included()] == ["A", "B"]
    assert not automatic.manual_override


def test_reverse_changes_start_and_rebuilds_auto_proposal() -> None:
    records = [_record("A", 2, 100.002), _record("B", 3, 100.008)]
    reversed_order = reference_pea_poles(records, _route(), direction_reversed=True)
    assert reversed_order.direction_reversed
    assert [entry.source_id for entry in reversed_order.ordered_included()] == ["B", "A"]
    assert not reversed_order.manual_override
    assert not reversed_order.confirmed


def test_excluded_source_record_is_retained_with_measurements() -> None:
    ordering = reference_pea_poles([_record("X", 5, 100.004, included=False)], _route())
    assert len(ordering.entries) == 1
    assert not ordering.entries[0].included
    assert ordering.entries[0].auto_order is None
