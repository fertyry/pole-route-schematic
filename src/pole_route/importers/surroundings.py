"""Coordinate primary OSM context with optional supplemental sources."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event

from pole_route.domain.context import OSMContext
from pole_route.domain.route import Route
from pole_route.importers.osm_context import OSMContextError, fetch_osm_context
from pole_route.importers.overture_buildings import (
    OvertureBuildingsError, OvertureFetchResult, conflate_buildings,
    fetch_overture_buildings,
)
from pole_route.importers.route_batches import split_route_by_distance

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
        tuple((*[warning for context in contexts for warning in context.warnings], *warnings)),
        tuple(metrics.items()),
    )


def fetch_surroundings_context(
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
            except Exception as error:
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
        except Exception as error:
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
