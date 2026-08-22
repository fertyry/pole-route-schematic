"""Coordinate primary OSM context with optional supplemental sources."""

from __future__ import annotations

import time
from collections.abc import Callable

from pole_route.domain.context import OSMContext
from pole_route.domain.route import Route
from pole_route.importers.osm_context import fetch_osm_context
from pole_route.importers.overture_buildings import (
    OvertureBuildingsError, OvertureFetchResult, conflate_buildings,
    fetch_overture_buildings,
)


def fetch_surroundings_context(
    route: Route, *, include_overture: bool = True,
    osm_fetcher: Callable[[Route], OSMContext] = fetch_osm_context,
    overture_fetcher: Callable[[Route], OvertureFetchResult] = fetch_overture_buildings,
) -> OSMContext:
    """Fetch OSM first and degrade gracefully if Overture is unavailable."""
    started = time.perf_counter()
    osm = osm_fetcher(route)
    osm_elapsed = time.perf_counter() - started
    if not include_overture:
        return OSMContext(osm.roads, osm.places, osm.features, osm.warnings,
                          (*osm.metrics, ("osm_seconds", osm_elapsed)))
    try:
        overture = overture_fetcher(route)
    except Exception as error:
        # Supplemental data must never discard a valid OSM result. The production
        # fetcher normalizes transport/schema failures to OvertureBuildingsError;
        # this broader boundary also protects the background UI task from a bad
        # third-party release while preserving the primary context.
        message = str(error) if isinstance(error, OvertureBuildingsError) else (
            f"Overture buildings unavailable: {error}"
        )
        return OSMContext(
            osm.roads, osm.places, osm.features, (*osm.warnings, message),
            (*osm.metrics, ("osm_seconds", osm_elapsed)),
        )
    conflation_started = time.perf_counter()
    conflated = conflate_buildings(osm.features, overture.features, route)
    elapsed = time.perf_counter() - conflation_started
    return OSMContext(
        osm.roads, osm.places, conflated.features, osm.warnings,
        (*osm.metrics, ("osm_seconds", osm_elapsed),
         ("overture_seconds", overture.elapsed_seconds),
         ("conflation_seconds", elapsed), ("overture_raw", float(overture.raw_count)),
         ("overture_corridor", float(overture.intersect_count)),
         ("buildings_matched", float(conflated.matched)),
         ("buildings_unmatched", float(conflated.unmatched)),
         ("buildings_ambiguous", float(conflated.ambiguous))),
    )
