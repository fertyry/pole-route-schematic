"""Linear-reference PEA GIS poles against one authoritative Main Route."""

from __future__ import annotations

from dataclasses import replace

from shapely.geometry import LineString, Point

from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import (
    PEAPoleOrdering,
    PEAPoleReviewEntry,
    PoleOffsetQCPolicy,
    PoleQCStatus,
)
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.projection import MetricProjection

NEAR_STATION_TOLERANCE_METRES = 0.05


def reference_pea_poles(
    records: list[PEAPoleRecord],
    main_route: Route,
    *,
    direction_reversed: bool = False,
    policy: PoleOffsetQCPolicy = PoleOffsetQCPolicy(),
) -> PEAPoleOrdering:
    projection = MetricProjection.for_points(main_route.points)
    line = LineString([projection.to_metric(point) for point in main_route.points])
    measured: list[tuple[PEAPoleRecord, float, float, GeoPoint, PoleQCStatus, list[str]]] = []
    for record in records:
        point = Point(projection.to_metric(GeoPoint(record.longitude, record.latitude)))
        source_station = float(line.project(point))
        station = float(line.length - source_station if direction_reversed else source_station)
        projected = line.interpolate(source_station)
        projected_geo = projection.to_geographic(projected.x, projected.y)
        offset = float(point.distance(projected))
        status = policy.status(offset)
        reasons = list(record.qc_warnings)
        if status is PoleQCStatus.REVIEW:
            reasons.append(f"Offset exceeds {policy.review_metres:g} m")
        elif status is PoleQCStatus.STRONG_REVIEW:
            reasons.append(f"Offset exceeds {policy.strong_review_metres:g} m")
        measured.append((record, station, offset, projected_geo, status, reasons))

    measured.sort(key=lambda item: (item[1], item[0].source_key))
    for index in range(1, len(measured)):
        if abs(measured[index][1] - measured[index - 1][1]) <= NEAR_STATION_TOLERANCE_METRES:
            for target in (index - 1, index):
                record, station, offset, projected, status, reasons = measured[target]
                if "Equal or near-equal station" not in reasons:
                    reasons.append("Equal or near-equal station")
                measured[target] = (
                    record, station, offset, projected,
                    PoleQCStatus.REVIEW if status is PoleQCStatus.NORMAL else status,
                    reasons,
                )

    selected = [item for item in measured if item[0].included_by_default]
    auto_orders = {item[0].source_key: index for index, item in enumerate(selected, 1)}
    entries = tuple(
        PEAPoleReviewEntry(
            source_key=record.source_key,
            source_id=record.source_id,
            station_metres=station,
            offset_metres=offset,
            projected_latitude=projected.latitude,
            projected_longitude=projected.longitude,
            auto_order=auto_orders.get(record.source_key),
            review_order=auto_orders.get(record.source_key),
            confirmed_order=None,
            included=record.included_by_default,
            qc_status=status,
            qc_reasons=tuple(reasons),
        )
        for record, station, offset, projected, status, reasons in measured
    )
    return PEAPoleOrdering(entries, direction_reversed=direction_reversed)


def reverse_pea_ordering(records: list[PEAPoleRecord], main_route: Route) -> PEAPoleOrdering:
    """Rebuild the automatic proposal with station measured from the other endpoint."""
    return reference_pea_poles(records, main_route, direction_reversed=True)
