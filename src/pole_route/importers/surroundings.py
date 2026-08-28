"""Coordinate primary OSM context with optional supplemental sources."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from urllib.error import HTTPError, URLError

from pole_route.domain.context import FetchCoverage, FetchCoverageStatus, OSMContext
from pole_route.domain.route import Route
from pole_route.importers.osm_context import OSMContextError, fetch_osm_context
from pole_route.importers.overture_buildings import (
    OvertureBuildingsError,
    OvertureFetchResult,
    conflate_buildings,
    fetch_overture_buildings,
)
from pole_route.importers.overture_places import (
    OverturePlacesResult,
    fetch_overture_places,
)
from pole_route.importers.route_batches import (
    SURROUND_BATCH_METRES,
    SURROUND_BATCH_OVERLAP_METRES,
    route_interval,
    split_route_by_distance,
)

OSM_BATCH_ATTEMPTS = 2


class SurroundFetchCancelled(RuntimeError):
    """The user cancelled a surroundings fetch without changing accepted state."""


@dataclass(frozen=True, slots=True)
class FetchProgress:
    message: str
    completed: int
    total: int


def _cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise SurroundFetchCancelled("Surroundings fetch cancelled")


def _emit(callback, message: str, completed: int, total: int) -> None:
    if callback is not None:
        callback(FetchProgress(message, completed, total))


def _merge_osm(contexts: list[OSMContext], warnings: list[str]) -> OSMContext:
    roads = {road.route.source_path: road for context in contexts for road in context.roads}
    places = {
        (place.name, place.category, round(place.point.longitude, 7), round(place.point.latitude, 7)): place
        for context in contexts for place in context.places
    }
    features = {
        feature.feature_key: feature for context in contexts for feature in context.features
    }
    metrics: dict[str, float] = {}
    for context in contexts:
        for key, value in context.metrics:
            metrics[key] = metrics.get(key, 0.0) + value
    return OSMContext(
        tuple(roads.values()), tuple(places.values()), tuple(features.values()),
        (*[warning for context in contexts for warning in context.warnings], *warnings),
        tuple(metrics.items()),
    )


def _legacy_fetch_surroundings_context(
    route: Route, *, include_overture: bool = True,
    osm_fetcher: Callable[[Route], OSMContext] = fetch_osm_context,
    overture_fetcher: Callable[[Route], OvertureFetchResult] = fetch_overture_buildings,
    progress_callback: Callable[[FetchProgress], None] | None = None,
    cancel_event: Event | None = None,
) -> OSMContext:
    """Fetch distance batches and preserve successful sources after partial failures."""
    started = time.perf_counter()
    batches = split_route_by_distance(route)
    total_steps = len(batches) * (2 if include_overture else 1) + 2
    _emit(progress_callback, "Preparing route...", 0, total_steps)
    osm_contexts: list[OSMContext] = []
    warnings: list[str] = []
    osm_errors: list[tuple[int, float, float, Exception]] = []
    retries = 0
    failed_osm_batches = 0
    for batch in batches:
        _cancelled(cancel_event)
        _emit(progress_callback, f"Fetching OSM {batch.index}/{batch.count}",
              batch.index - 1, total_steps)
        last_error: Exception | None = None
        for attempt in range(OSM_BATCH_ATTEMPTS):
            try:
                osm_contexts.append(osm_fetcher(batch.route))
                last_error = None
                break
            except SurroundFetchCancelled:
                raise
            except Exception as error:  # noqa: BLE001 - legacy provider boundary
                last_error = error
                if attempt + 1 < OSM_BATCH_ATTEMPTS:
                    retries += 1
        if last_error is not None:
            failed_osm_batches += 1
            osm_errors.append((
                batch.index, batch.start_metres, batch.end_metres, last_error
            ))
            warnings.append(
                f"PARTIAL: OSM batch {batch.index}/{batch.count} "
                f"({batch.start_metres:.0f}-{batch.end_metres:.0f} m) failed: {last_error}"
            )
    if not osm_contexts:
        details = "; ".join(
            f"batch {index}/{len(batches)} ({start:.0f}-{end:.0f} m): {error}"
            for index, start, end, error in osm_errors
        )
        raise OSMContextError(f"All OpenStreetMap route batches failed: {details}")
    osm = _merge_osm(osm_contexts, warnings)
    osm_elapsed = time.perf_counter() - started
    if not include_overture:
        _cancelled(cancel_event)
        _emit(progress_callback, "Preparing review...", total_steps - 1, total_steps)
        result = OSMContext(
            osm.roads, osm.places, osm.features, osm.warnings,
            (*osm.metrics, ("route_length_metres", batches[-1].end_metres),
             ("batch_count", float(len(batches))),
             ("osm_seconds", osm_elapsed), ("osm_retries", float(retries)),
             ("osm_failed_batches", float(failed_osm_batches)),
             ("total_seconds", time.perf_counter() - started)),
        )
        _emit(progress_callback, "Surroundings ready", total_steps, total_steps)
        return result
    overture_results: list[OvertureFetchResult] = []
    overture_errors: list[tuple[int, float, float, Exception]] = []
    for batch in batches:
        _cancelled(cancel_event)
        _emit(progress_callback, f"Fetching Overture Buildings {batch.index}/{batch.count}",
              len(batches) + batch.index - 1, total_steps)
        try:
            result = overture_fetcher(batch.route)
            overture_results.append(result)
            if result.cache_hit:
                _emit(
                    progress_callback,
                    f"Loaded cached Overture Buildings {batch.index}/{batch.count}",
                    len(batches) + batch.index,
                    total_steps,
                )
        except SurroundFetchCancelled:
            raise
        except Exception as error:  # noqa: BLE001 - legacy provider boundary
            overture_errors.append((
                batch.index, batch.start_metres, batch.end_metres, error,
            ))
    if not overture_results:
        # Supplemental data must never discard a valid OSM result. The production
        # fetcher normalizes transport/schema failures to OvertureBuildingsError;
        # this broader boundary also protects the background UI task from a bad
        # third-party release while preserving the primary context.
        if len(batches) == 1:
            error = overture_errors[0][3]
            message = str(error) if isinstance(error, OvertureBuildingsError) else (
                f"Overture buildings unavailable: {error}"
            )
        else:
            details = "; ".join(
                f"batch {index}/{len(batches)} ({start:.0f}-{end:.0f} m): {error}"
                for index, start, end, error in overture_errors
            )
            message = "Overture buildings unavailable: " + details
        _cancelled(cancel_event)
        _emit(progress_callback, "Preparing review...", total_steps - 1, total_steps)
        result = OSMContext(
            osm.roads, osm.places, osm.features, (*osm.warnings, message),
            (*osm.metrics, ("route_length_metres", batches[-1].end_metres),
             ("batch_count", float(len(batches))), ("osm_seconds", osm_elapsed),
             ("osm_retries", float(retries)),
             ("osm_failed_batches", float(failed_osm_batches)),
             ("overture_failed_batches", float(len(overture_errors))),
             ("total_seconds", time.perf_counter() - started)),
        )
        _emit(progress_callback, "Surroundings ready", total_steps, total_steps)
        return result
    overture_features = {
        feature.source_id: feature
        for result in overture_results for feature in result.features
    }
    overture = OvertureFetchResult(
        tuple(overture_features.values()),
        sum(result.raw_count for result in overture_results),
        len(overture_features), overture_results[0].release,
        sum(result.elapsed_seconds for result in overture_results),
        all(result.cache_hit for result in overture_results),
    )
    if overture_errors:
        osm = OSMContext(osm.roads, osm.places, osm.features,
                         (*osm.warnings, "PARTIAL: Overture " + "; ".join(
                             f"batch {index}/{len(batches)} "
                             f"({start:.0f}-{end:.0f} m): {error}"
                             for index, start, end, error in overture_errors
                         )),
                         osm.metrics)
    _cancelled(cancel_event)
    _emit(progress_callback, "Conflating Buildings...", total_steps - 2, total_steps)
    conflation_started = time.perf_counter()
    conflated = conflate_buildings(osm.features, overture.features, route)
    elapsed = time.perf_counter() - conflation_started
    _emit(progress_callback, "Preparing review...", total_steps - 1, total_steps)
    result = OSMContext(
        osm.roads, osm.places, conflated.features, osm.warnings,
        (*osm.metrics, ("osm_seconds", osm_elapsed),
         ("overture_seconds", overture.elapsed_seconds),
         ("overture_cache_hits", float(sum(item.cache_hit for item in overture_results))),
         ("overture_cache_misses", float(sum(not item.cache_hit for item in overture_results))),
         ("overture_failed_batches", float(len(overture_errors))),
         ("conflation_seconds", elapsed), ("overture_raw", float(overture.raw_count)),
         ("overture_corridor", float(overture.intersect_count)),
         ("buildings_matched", float(conflated.matched)),
         ("buildings_unmatched", float(conflated.unmatched)),
         ("buildings_ambiguous", float(conflated.ambiguous)),
         ("route_length_metres", batches[-1].end_metres),
         ("batch_count", float(len(batches))), ("osm_retries", float(retries)),
         ("osm_failed_batches", float(failed_osm_batches)),
         ("total_seconds", time.perf_counter() - started)),
    )
    _emit(progress_callback, "Surroundings ready", total_steps, total_steps)
    return result


@dataclass(frozen=True, slots=True)
class OSMAdaptivePolicy:
    """Central policy for efficient initial requests and bounded recovery."""

    primary_interval_metres: float = SURROUND_BATCH_METRES
    overlap_metres: float = SURROUND_BATCH_OVERLAP_METRES
    attempts_per_interval: int = 2
    minimum_interval_metres: float = 375.0
    maximum_split_depth: int = 3


DEFAULT_OSM_ADAPTIVE_POLICY = OSMAdaptivePolicy()


@dataclass(slots=True)
class _AdaptiveStats:
    requests: int = 0
    retries: int = 0
    splits: int = 0
    fetch_seconds: float = 0.0


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError, HTTPError, URLError, OSError)):
        return True
    message = str(error).casefold()
    transient = any(
        word in message
        for word in ("contact", "temporary", "timeout", "network", "connection", "unavailable")
    )
    return transient and isinstance(error, (OSMContextError, RuntimeError))


def _adaptive_osm_interval(
    route: Route,
    start: float,
    end: float,
    depth: int,
    *,
    osm_fetcher: Callable[[Route], OSMContext],
    policy: OSMAdaptivePolicy,
    stats: _AdaptiveStats,
    progress_callback: Callable[[FetchProgress], None] | None,
    completed: int,
    total: int,
    cancel_event: Event | None,
) -> tuple[list[OSMContext], list[FetchCoverage]]:
    fetch_route = route_interval(route, start, end, overlap_metres=policy.overlap_metres)
    last_error: Exception | None = None
    attempts = 0
    for attempt in range(policy.attempts_per_interval):
        _cancelled(cancel_event)
        attempts += 1
        stats.requests += 1
        if attempt:
            stats.retries += 1
            _emit(
                progress_callback,
                f"OSM: retrying {start:.0f}-{end:.0f} m",
                completed,
                total,
            )
        request_started = time.perf_counter()
        try:
            context = osm_fetcher(fetch_route)
        except SurroundFetchCancelled:
            raise
        except Exception as error:  # noqa: BLE001 - classify provider failures below
            last_error = error
            if not _is_retryable(error):
                stats.fetch_seconds += time.perf_counter() - request_started
                break
        else:
            stats.fetch_seconds += time.perf_counter() - request_started
            _emit(
                progress_callback,
                f"OSM: {start:.0f}-{end:.0f} m complete",
                completed + 1,
                total,
            )
            return [context], [FetchCoverage(
                "OpenStreetMap", start, end, FetchCoverageStatus.SUCCESS,
                depth, attempts, max(0, attempts - 1), "",
            )]
        stats.fetch_seconds += time.perf_counter() - request_started

    assert last_error is not None
    can_split = (
        _is_retryable(last_error)
        and depth < policy.maximum_split_depth
        and (end - start) / 2 >= policy.minimum_interval_metres
    )
    if not can_split:
        return [], [FetchCoverage(
            "OpenStreetMap", start, end, FetchCoverageStatus.FAILED,
            depth, attempts, max(0, attempts - 1), str(last_error),
        )]
    stats.splits += 1
    midpoint = (start + end) / 2
    _emit(
        progress_callback,
        f"OSM: splitting {start:.0f}-{end:.0f} m",
        completed,
        total,
    )
    contexts: list[OSMContext] = []
    coverage: list[FetchCoverage] = []
    for child_start, child_end in ((start, midpoint), (midpoint, end)):
        child_contexts, child_coverage = _adaptive_osm_interval(
            route,
            child_start,
            child_end,
            depth + 1,
            osm_fetcher=osm_fetcher,
            policy=policy,
            stats=stats,
            progress_callback=progress_callback,
            completed=completed,
            total=total,
            cancel_event=cancel_event,
        )
        contexts.extend(child_contexts)
        coverage.extend(child_coverage)
    return contexts, coverage


def _fetch_osm_ranges(
    route: Route,
    ranges: list[tuple[float, float, int]],
    *,
    osm_fetcher: Callable[[Route], OSMContext],
    policy: OSMAdaptivePolicy,
    progress_callback: Callable[[FetchProgress], None] | None,
    cancel_event: Event | None,
    total_steps: int,
) -> tuple[OSMContext, tuple[FetchCoverage, ...]]:
    contexts: list[OSMContext] = []
    coverage: list[FetchCoverage] = []
    stats = _AdaptiveStats()
    for index, (start, end, depth) in enumerate(ranges, 1):
        _emit(progress_callback, f"OSM: {index}/{len(ranges)}", index - 1, total_steps)
        fetched, final = _adaptive_osm_interval(
            route,
            start,
            end,
            depth,
            osm_fetcher=osm_fetcher,
            policy=policy,
            stats=stats,
            progress_callback=progress_callback,
            completed=index - 1,
            total=total_steps,
            cancel_event=cancel_event,
        )
        contexts.extend(fetched)
        coverage.extend(final)
    warnings = [
        f"PARTIAL: OSM unresolved {item.station_start:.0f}-{item.station_end:.0f} m: "
        f"{item.failure_reason}"
        for item in coverage if item.status is FetchCoverageStatus.FAILED
    ]
    merge_started = time.perf_counter()
    merged = _merge_osm(contexts, warnings)
    merge_seconds = time.perf_counter() - merge_started
    metrics = (
        *merged.metrics,
        ("osm_network_requests", float(stats.requests)),
        ("osm_retries", float(stats.retries)),
        ("osm_adaptive_splits", float(stats.splits)),
        ("osm_successful_intervals", float(sum(
            item.status is FetchCoverageStatus.SUCCESS for item in coverage
        ))),
        ("osm_failed_intervals", float(sum(
            item.status is FetchCoverageStatus.FAILED for item in coverage
        ))),
        ("osm_fetch_seconds", stats.fetch_seconds),
        ("osm_merge_seconds", merge_seconds),
        ("osm_candidates", float(len(merged.roads) + len(merged.places) + len(merged.features))),
    )
    return OSMContext(
        merged.roads, merged.places, merged.features, merged.warnings, metrics,
        tuple(coverage),
    ), tuple(coverage)


def fetch_surroundings_context(
    route: Route,
    *,
    include_overture: bool = True,
    include_places: bool = False,
    osm_fetcher: Callable[[Route], OSMContext] = fetch_osm_context,
    overture_fetcher: Callable[[Route], OvertureFetchResult] = fetch_overture_buildings,
    places_fetcher: Callable[[Route], OverturePlacesResult] = fetch_overture_places,
    progress_callback: Callable[[FetchProgress], None] | None = None,
    cancel_event: Event | None = None,
    osm_policy: OSMAdaptivePolicy = DEFAULT_OSM_ADAPTIVE_POLICY,
) -> OSMContext:
    """Fetch large primary intervals and adaptively recover only failed areas."""
    started = time.perf_counter()
    batches = split_route_by_distance(
        route,
        batch_metres=osm_policy.primary_interval_metres,
        overlap_metres=osm_policy.overlap_metres,
    )
    total_steps = len(batches) * (1 + int(include_overture) + int(include_places)) + 2
    _emit(progress_callback, "Preparing route...", 0, total_steps)
    osm, osm_coverage = _fetch_osm_ranges(
        route,
        [(batch.start_metres, batch.end_metres, 0) for batch in batches],
        osm_fetcher=osm_fetcher,
        policy=osm_policy,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
        total_steps=total_steps,
    )
    if not include_overture and not include_places:
        _emit(progress_callback, "Preparing review...", total_steps - 1, total_steps)
        review_started = time.perf_counter()
        candidate_count = len(osm.roads) + len(osm.places) + len(osm.features)
        review_seconds = time.perf_counter() - review_started
        result = OSMContext(
            osm.roads, osm.places, osm.features, osm.warnings,
            (*osm.metrics, ("route_length_metres", batches[-1].end_metres),
             ("batch_count", float(len(batches))),
             ("osm_primary_intervals", float(len(batches))),
             ("review_candidates", float(candidate_count)),
             ("review_prepare_seconds", review_seconds),
             ("osm_failed_batches", float(sum(
                 item.status is FetchCoverageStatus.FAILED for item in osm_coverage
             ))),
             ("total_seconds", time.perf_counter() - started)),
            osm_coverage,
        )
        _emit(progress_callback, "Surroundings ready", total_steps, total_steps)
        return result

    overture_results: list[OvertureFetchResult] = []
    overture_coverage: list[FetchCoverage] = []
    overture_warnings: list[str] = []
    for index, batch in enumerate(batches, 1) if include_overture else ():
        _cancelled(cancel_event)
        _emit(
            progress_callback,
            f"Overture Buildings: fetching {index}/{len(batches)}",
            len(batches) + index - 1,
            total_steps,
        )
        try:
            item = overture_fetcher(batch.route)
        except SurroundFetchCancelled:
            raise
        except Exception as error:  # noqa: BLE001 - isolate supplemental provider
            overture_coverage.append(FetchCoverage(
                "Overture Buildings", batch.start_metres, batch.end_metres,
                FetchCoverageStatus.FAILED, failure_reason=str(error),
            ))
            if len(batches) == 1:
                overture_warnings.append(
                    str(error) if isinstance(error, OvertureBuildingsError)
                    else f"Overture buildings unavailable: {error}"
                )
            else:
                overture_warnings.append(
                    f"PARTIAL: Overture batch {batch.index}/{batch.count} "
                    f"({batch.start_metres:.0f}-{batch.end_metres:.0f} m): {error}"
                )
        else:
            overture_results.append(item)
            overture_coverage.append(FetchCoverage(
                "Overture Buildings", batch.start_metres, batch.end_metres,
                FetchCoverageStatus.SUCCESS,
            ))
            if item.cache_hit:
                _emit(
                    progress_callback,
                    f"Overture Buildings: cache hit {index}/{len(batches)}",
                    len(batches) + index,
                    total_steps,
                )

    places_results: list[OverturePlacesResult] = []
    places_coverage: list[FetchCoverage] = []
    places_warnings: list[str] = []
    places_step_start = len(batches) * (1 + int(include_overture))
    for index, batch in enumerate(batches, 1) if include_places else ():
        _cancelled(cancel_event)
        _emit(
            progress_callback,
            f"Overture Places: fetching {index}/{len(batches)}",
            places_step_start + index - 1,
            total_steps,
        )
        try:
            item = places_fetcher(batch.route)
        except SurroundFetchCancelled:
            raise
        except Exception as error:  # noqa: BLE001 - isolate independent provider
            places_coverage.append(FetchCoverage(
                "Overture Places", batch.start_metres, batch.end_metres,
                FetchCoverageStatus.FAILED, failure_reason=str(error),
            ))
            places_warnings.append(
                f"PARTIAL: Overture Places unresolved {batch.start_metres:.0f}-"
                f"{batch.end_metres:.0f} m: {error}"
            )
        else:
            places_results.append(item)
            places_coverage.append(FetchCoverage(
                "Overture Places", batch.start_metres, batch.end_metres,
                FetchCoverageStatus.SUCCESS,
            ))

    features = osm.features
    conflation_seconds = 0.0
    conflation_metrics: tuple[tuple[str, float], ...] = ()
    if overture_results:
        unique = {
            feature.source_id: feature
            for result in overture_results for feature in result.features
        }
        _emit(progress_callback, "Overture Buildings: conflating", total_steps - 2, total_steps)
        conflation_started = time.perf_counter()
        conflated = conflate_buildings(osm.features, tuple(unique.values()), route)
        conflation_seconds = time.perf_counter() - conflation_started
        features = conflated.features
        conflation_metrics = (
            ("buildings_matched", float(conflated.matched)),
            ("buildings_unmatched", float(conflated.unmatched)),
            ("buildings_ambiguous", float(conflated.ambiguous)),
        )
    if places_results:
        by_key = {feature.feature_key: feature for feature in features}
        for result in places_results:
            for feature in result.features:
                by_key[feature.feature_key] = feature
        features = tuple(by_key.values())
    _emit(progress_callback, "Preparing review...", total_steps - 1, total_steps)
    review_started = time.perf_counter()
    candidate_count = len(osm.roads) + len(osm.places) + len(features)
    final_buildings = sum(
        feature.category.value == "building" for feature in features
    )
    review_seconds = time.perf_counter() - review_started
    metrics = (
        *osm.metrics,
        ("overture_seconds", sum(item.elapsed_seconds for item in overture_results)),
        ("overture_cache_hits", float(sum(item.cache_hit for item in overture_results))),
        ("overture_cache_misses", float(sum(not item.cache_hit for item in overture_results))),
        ("overture_failed_batches", float(sum(
            item.status is FetchCoverageStatus.FAILED for item in overture_coverage
        ))),
        ("overture_raw", float(sum(item.raw_count for item in overture_results))),
        ("overture_corridor", float(sum(item.intersect_count for item in overture_results))),
        ("overture_final_buildings", float(final_buildings)),
        ("conflation_seconds", conflation_seconds),
        *conflation_metrics,
        ("overture_places_seconds", sum(item.elapsed_seconds for item in places_results)),
        ("overture_places_raw", float(sum(item.raw_count for item in places_results))),
        ("overture_places_retained", float(sum(
            item.retained_count for item in places_results
        ))),
        ("overture_places_recommended", float(sum(
            item.recommended_count for item in places_results
        ))),
        ("overture_places_failed_batches", float(sum(
            item.status is FetchCoverageStatus.FAILED for item in places_coverage
        ))),
        ("route_length_metres", batches[-1].end_metres),
        ("batch_count", float(len(batches))),
        ("osm_primary_intervals", float(len(batches))),
        ("review_candidates", float(candidate_count)),
        ("review_prepare_seconds", review_seconds),
        ("osm_failed_batches", float(sum(
            item.status is FetchCoverageStatus.FAILED for item in osm_coverage
        ))),
        ("total_seconds", time.perf_counter() - started),
    )
    result = OSMContext(
        osm.roads, osm.places, features,
        (*osm.warnings, *overture_warnings, *places_warnings), metrics,
        (*osm_coverage, *overture_coverage, *places_coverage),
    )
    _emit(progress_callback, "Surroundings ready", total_steps, total_steps)
    return result


def retry_failed_surroundings_context(
    route: Route,
    previous: OSMContext,
    *,
    osm_fetcher: Callable[[Route], OSMContext] = fetch_osm_context,
    overture_fetcher: Callable[[Route], OvertureFetchResult] = fetch_overture_buildings,
    places_fetcher: Callable[[Route], OverturePlacesResult] = fetch_overture_places,
    progress_callback: Callable[[FetchProgress], None] | None = None,
    cancel_event: Event | None = None,
    osm_policy: OSMAdaptivePolicy = DEFAULT_OSM_ADAPTIVE_POLICY,
) -> OSMContext:
    """Retry only unresolved intervals and merge them into the candidate snapshot."""
    failed_osm = [
        item for item in previous.coverage
        if item.provider == "OpenStreetMap" and item.status is FetchCoverageStatus.FAILED
    ]
    failed_overture = [
        item for item in previous.coverage
        if item.provider == "Overture Buildings" and item.status is FetchCoverageStatus.FAILED
    ]
    failed_places = [
        item for item in previous.coverage
        if item.provider == "Overture Places" and item.status is FetchCoverageStatus.FAILED
    ]
    total_steps = max(1, len(failed_osm) + len(failed_overture) + len(failed_places) + 1)
    recovered_osm = OSMContext()
    replacements: list[FetchCoverage] = []
    if failed_osm:
        recovered_osm, recovered_coverage = _fetch_osm_ranges(
            route,
            [(item.station_start, item.station_end, item.split_depth) for item in failed_osm],
            osm_fetcher=osm_fetcher,
            policy=osm_policy,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
            total_steps=total_steps,
        )
        replacements.extend(recovered_coverage)
    recovered_overture: list[OvertureFetchResult] = []
    for index, coverage in enumerate(failed_overture, 1):
        _cancelled(cancel_event)
        _emit(
            progress_callback,
            f"Overture Buildings: retrying {coverage.station_start:.0f}-"
            f"{coverage.station_end:.0f} m",
            len(failed_osm) + index - 1,
            total_steps,
        )
        try:
            item = overture_fetcher(route_interval(
                route, coverage.station_start, coverage.station_end,
                overlap_metres=osm_policy.overlap_metres,
            ))
        except Exception as error:  # noqa: BLE001 - isolate supplemental provider
            replacements.append(FetchCoverage(
                "Overture Buildings", coverage.station_start, coverage.station_end,
                FetchCoverageStatus.FAILED, coverage.split_depth,
                coverage.attempts + 1, coverage.retries + 1, str(error),
            ))
        else:
            recovered_overture.append(item)
            replacements.append(FetchCoverage(
                "Overture Buildings", coverage.station_start, coverage.station_end,
                FetchCoverageStatus.SUCCESS, coverage.split_depth,
                coverage.attempts + 1, coverage.retries + 1,
            ))
    recovered_places: list[OverturePlacesResult] = []
    for index, coverage in enumerate(failed_places, 1):
        _cancelled(cancel_event)
        _emit(
            progress_callback,
            f"Overture Places: retrying {coverage.station_start:.0f}-"
            f"{coverage.station_end:.0f} m",
            len(failed_osm) + len(failed_overture) + index - 1,
            total_steps,
        )
        try:
            item = places_fetcher(route_interval(
                route, coverage.station_start, coverage.station_end,
                overlap_metres=osm_policy.overlap_metres,
            ))
        except Exception as error:  # noqa: BLE001 - isolate independent provider
            replacements.append(FetchCoverage(
                "Overture Places", coverage.station_start, coverage.station_end,
                FetchCoverageStatus.FAILED, coverage.split_depth,
                coverage.attempts + 1, coverage.retries + 1, str(error),
            ))
        else:
            recovered_places.append(item)
            replacements.append(FetchCoverage(
                "Overture Places", coverage.station_start, coverage.station_end,
                FetchCoverageStatus.SUCCESS, coverage.split_depth,
                coverage.attempts + 1, coverage.retries + 1,
            ))
    merged = _merge_osm([previous, recovered_osm], [])
    features = merged.features
    if recovered_overture:
        recovered_features = tuple(
            feature for result in recovered_overture for feature in result.features
        )
        features = conflate_buildings(features, recovered_features, route).features
    if recovered_places:
        by_key = {feature.feature_key: feature for feature in features}
        for result in recovered_places:
            for feature in result.features:
                by_key[feature.feature_key] = feature
        features = tuple(by_key.values())
    failed_keys = {
        (item.provider, item.station_start, item.station_end)
        for item in (*failed_osm, *failed_overture, *failed_places)
    }
    coverage = tuple(
        item for item in previous.coverage
        if (item.provider, item.station_start, item.station_end) not in failed_keys
    ) + tuple(replacements)
    warnings = tuple(
        f"PARTIAL: {item.provider} unresolved {item.station_start:.0f}-"
        f"{item.station_end:.0f} m: {item.failure_reason}"
        for item in coverage if item.status is FetchCoverageStatus.FAILED
    )
    _emit(progress_callback, "Preparing review...", total_steps, total_steps)
    return OSMContext(
        merged.roads, merged.places, features, warnings,
        (*previous.metrics, *recovered_osm.metrics), coverage,
    )
