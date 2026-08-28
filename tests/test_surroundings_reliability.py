from __future__ import annotations

from threading import Event

import pytest

from pole_route.domain.context import (
    ContextFeature,
    ContextGeometryPart,
    FetchCoverage,
    FetchCoverageStatus,
    OSMContext,
    OSMFeatureCategory,
    OSMGeometryKind,
    ProviderFetchState,
)
from pole_route.domain.route import GeoPoint, Route
from pole_route.importers.surroundings import (
    OSMAdaptivePolicy,
    SurroundFetchCancelled,
    fetch_surroundings_context,
    retry_failed_surroundings_context,
)
from pole_route.project.storage import (
    load_project_file,
    osm_context_from_data,
    osm_context_to_data,
    save_project_file,
)


def _route(delta_latitude: float = 0.09) -> Route:
    return Route(
        "Long",
        "long.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.0 + delta_latitude)),
    )


def _feature(osm_id: int) -> ContextFeature:
    return ContextFeature(
        "node",
        osm_id,
        OSMFeatureCategory.POI,
        OSMGeometryKind.POINT,
        (ContextGeometryPart((GeoPoint(100.0, 13.01),)),),
        name=f"POI {osm_id}",
    )


def test_success_uses_large_primary_intervals_without_split() -> None:
    calls: list[str] = []

    def fetch(route: Route) -> OSMContext:
        calls.append(route.name)
        return OSMContext(features=(_feature(len(calls)),))

    result = fetch_surroundings_context(
        _route(), include_overture=False, osm_fetcher=fetch
    )
    metrics = dict(result.metrics)

    assert metrics["batch_count"] == 4
    assert metrics["osm_network_requests"] == 4
    assert metrics["osm_adaptive_splits"] == 0
    assert len(calls) == 4
    assert result.provider_state("OpenStreetMap") is ProviderFetchState.COMPLETE


def test_timeout_splits_only_failed_parent_and_recovers_children() -> None:
    calls: list[str] = []

    def fetch(route: Route) -> OSMContext:
        calls.append(route.name)
        if "[3000-6000 m]" in route.name:
            raise TimeoutError("provider timeout")
        return OSMContext(features=(_feature(len(calls)),))

    result = fetch_surroundings_context(
        _route(), include_overture=False, osm_fetcher=fetch
    )
    metrics = dict(result.metrics)

    assert calls.count("Long [0-3000 m]") == 1
    assert calls.count("Long [3000-6000 m]") == 2
    assert "Long [3000-4500 m]" in calls
    assert "Long [4500-6000 m]" in calls
    assert metrics["osm_adaptive_splits"] == 1
    assert metrics["osm_failed_intervals"] == 0
    assert result.provider_state("OpenStreetMap") is ProviderFetchState.COMPLETE


def test_only_failed_child_splits_further_and_order_is_deterministic() -> None:
    calls: list[str] = []

    def fetch(route: Route) -> OSMContext:
        calls.append(route.name)
        if "[3000-6000 m]" in route.name or "[4500-6000 m]" in route.name:
            raise TimeoutError("transient")
        return OSMContext()

    result = fetch_surroundings_context(
        _route(), include_overture=False, osm_fetcher=fetch
    )
    intervals = [
        (item.station_start, item.station_end)
        for item in result.coverage if 3000 <= item.station_start < 6000
    ]

    assert intervals == [(3000, 4500), (4500, 5250), (5250, 6000)]
    assert calls.count("Long [3000-4500 m]") == 1
    assert dict(result.metrics)["osm_adaptive_splits"] == 2


def test_minimum_interval_and_max_depth_bound_requests() -> None:
    policy = OSMAdaptivePolicy(
        primary_interval_metres=3000,
        attempts_per_interval=1,
        minimum_interval_metres=750,
        maximum_split_depth=2,
    )
    calls = 0

    def fail(_route: Route) -> OSMContext:
        nonlocal calls
        calls += 1
        raise TimeoutError("still unavailable")

    previous = OSMContext(coverage=(FetchCoverage(
        "OpenStreetMap", 0, 3000, FetchCoverageStatus.FAILED,
        failure_reason="timeout",
    ),))
    result = retry_failed_surroundings_context(
        _route(), previous, osm_fetcher=fail, osm_policy=policy
    )

    assert calls == 7
    assert len(result.coverage) == 4
    assert all(item.split_depth == 2 for item in result.coverage)
    assert result.provider_state("OpenStreetMap") is ProviderFetchState.FAILED


def test_non_retryable_validation_error_is_not_retried_or_split() -> None:
    calls = 0

    def fail(_route: Route) -> OSMContext:
        nonlocal calls
        calls += 1
        raise ValueError("unsupported deterministic response")

    result = fetch_surroundings_context(
        _route(0.01), include_overture=False, osm_fetcher=fail
    )

    assert calls == 1
    assert len(result.coverage) == 1
    assert result.coverage[0].status is FetchCoverageStatus.FAILED
    assert result.coverage[0].split_depth == 0


def test_cancellation_stops_before_any_request() -> None:
    cancel = Event()
    cancel.set()
    with pytest.raises(SurroundFetchCancelled):
        fetch_surroundings_context(
            _route(),
            include_overture=False,
            osm_fetcher=lambda _route: pytest.fail("must not request"),
            cancel_event=cancel,
        )


def test_retry_queries_only_unresolved_interval_and_preserves_candidates() -> None:
    previous = OSMContext(
        features=(_feature(1),),
        coverage=(
            FetchCoverage(
                "OpenStreetMap", 0, 3000, FetchCoverageStatus.SUCCESS
            ),
            FetchCoverage(
                "OpenStreetMap", 3000, 6000, FetchCoverageStatus.FAILED,
                failure_reason="timeout",
            ),
            FetchCoverage(
                "OpenStreetMap", 6000, 9000, FetchCoverageStatus.SUCCESS
            ),
        ),
    )
    calls: list[str] = []

    def recover(route: Route) -> OSMContext:
        calls.append(route.name)
        return OSMContext(features=(_feature(2),))

    result = retry_failed_surroundings_context(
        _route(), previous, osm_fetcher=recover
    )

    assert calls == ["Long [3000-6000 m]"]
    assert {item.osm_id for item in result.features} == {1, 2}
    assert result.provider_state("OpenStreetMap") is ProviderFetchState.COMPLETE


def test_provider_partial_state_and_coverage_round_trip(tmp_path) -> None:
    context = OSMContext(
        coverage=(
            FetchCoverage(
                "OpenStreetMap", 0, 1500, FetchCoverageStatus.SUCCESS, 1, 2, 1
            ),
            FetchCoverage(
                "OpenStreetMap", 1500, 3000, FetchCoverageStatus.FAILED,
                1, 2, 1, "timeout",
            ),
            FetchCoverage(
                "Overture Buildings", 0, 3000, FetchCoverageStatus.SUCCESS
            ),
        )
    )
    path = tmp_path / "coverage.prs"
    save_project_file(path, {"surrounding_candidates": osm_context_to_data(context)})
    restored = osm_context_from_data(load_project_file(path)["surrounding_candidates"])

    assert restored == context
    assert restored.provider_state("OpenStreetMap") is ProviderFetchState.PARTIAL
    assert restored.provider_state("Overture Buildings") is ProviderFetchState.COMPLETE
