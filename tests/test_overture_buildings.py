from __future__ import annotations

import pytest
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping

from pole_route.domain.context import (
    ContextFeature, ContextGeometryPart, OSMContext, OSMFeatureCategory, OSMGeometryKind,
)
from pole_route.domain.route import GeoPoint, Route
from pole_route.importers.overture_buildings import (
    OvertureBuildingsError, OvertureFetchResult, conflate_buildings,
    fetch_overture_buildings,
)
from pole_route.importers.surroundings import (
    SurroundFetchCancelled,
    fetch_surroundings_context,
)


def _route() -> Route:
    return Route("A005", "A005.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.01)))


def _row(source_id="overture-1", geometry=None):
    return {
        "id": source_id,
        "geometry": mapping(geometry or Polygon([
            (99.99995, 13.004), (100.00005, 13.004),
            (100.00005, 13.0041), (99.99995, 13.0041), (99.99995, 13.004),
        ])),
        "version": 3,
        "names": {"primary": "Building", "common": {"th": "อาคารทดสอบ"}},
        "sources": [{"dataset": "example", "record_id": "record-1"}],
        "confidence": 0.91,
    }


def _feature(source, source_id, min_lon=99.99995, max_lon=100.00005):
    points = (
        GeoPoint(min_lon, 13.004), GeoPoint(max_lon, 13.004),
        GeoPoint(max_lon, 13.0041), GeoPoint(min_lon, 13.0041),
        GeoPoint(min_lon, 13.004),
    )
    return ContextFeature(
        "way" if source == "OpenStreetMap" else "",
        998986400 if source == "OpenStreetMap" else 0,
        OSMFeatureCategory.BUILDING, OSMGeometryKind.POLYGON,
        (ContextGeometryPart(points),), source=source, source_id=source_id,
    )


class _Table:
    def __init__(self, rows):
        self._rows = rows

    def to_pylist(self):
        return self._rows


class _Reader:
    def __init__(self, rows):
        self._rows = rows

    def read_all(self):
        return _Table(self._rows)


def test_fetch_parses_polygon_hole_multipolygon_and_source_fields(tmp_path):
    exterior = [(99.9999, 13.004), (100.0001, 13.004), (100.0001, 13.0042),
                (99.9999, 13.0042), (99.9999, 13.004)]
    hole = [(99.99995, 13.00405), (100.00005, 13.00405),
            (100.00005, 13.0041), (99.99995, 13.0041), (99.99995, 13.00405)]
    geometry = MultiPolygon((Polygon(exterior, (hole,)),))
    result = fetch_overture_buildings(
        _route(), reader_factory=lambda *_args, **_kwargs: _Reader([_row(geometry=geometry)]),
        release_getter=lambda: "2026-08-01", cache_directory=tmp_path,
    )
    feature = result.features[0]
    assert result.raw_count == result.intersect_count == 1
    assert feature.category is OSMFeatureCategory.BUILDING
    assert feature.geometry_kind is OSMGeometryKind.POLYGON
    assert feature.parts[0].holes
    assert feature.name == "อาคารทดสอบ"
    assert feature.source == "Overture"
    assert feature.source_id == "overture-1"
    assert feature.source_release == "2026-08-01"
    assert feature.confidence == 0.91


def test_fetch_ignores_invalid_and_outside_geometry(tmp_path):
    far = Polygon([(101, 14), (101.1, 14), (101.1, 14.1), (101, 14.1), (101, 14)])
    rows = [_row("far", far), {"id": "bad", "geometry": None}]
    result = fetch_overture_buildings(
        _route(), reader_factory=lambda *_args, **_kwargs: _Reader(rows),
        release_getter=lambda: "release", cache_directory=tmp_path,
    )
    assert result.raw_count == 2
    assert result.features == ()


def test_fetch_recovers_polygon_from_validated_geometry_collection(tmp_path):
    polygon = Polygon([
        (99.99995, 13.004), (100.00005, 13.004),
        (100.00005, 13.0041), (99.99995, 13.0041), (99.99995, 13.004),
    ])
    row = _row(geometry=GeometryCollection((polygon,)))
    result = fetch_overture_buildings(
        _route(), reader_factory=lambda *_args, **_kwargs: _Reader([row]),
        release_getter=lambda: "release", cache_directory=tmp_path,
    )
    assert len(result.features) == 1


def test_fetch_reuses_bounded_cache_without_querying_source(tmp_path):
    calls = 0

    def reader(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _Reader([_row()])

    first = fetch_overture_buildings(
        _route(), reader_factory=reader, release_getter=lambda: "release",
        cache_directory=tmp_path,
    )
    second = fetch_overture_buildings(
        _route(), reader_factory=reader, release_getter=lambda: "release",
        cache_directory=tmp_path,
    )
    assert calls == 1
    assert second.features == first.features
    assert not first.cache_hit
    assert second.cache_hit


def test_fetch_ignores_malformed_cache_and_replaces_it(tmp_path):
    release = "release"
    projection_route = _route()
    # Prime the exact cache name, then corrupt it before the second source read.
    first = fetch_overture_buildings(
        projection_route,
        reader_factory=lambda *_args, **_kwargs: _Reader([_row()]),
        release_getter=lambda: release,
        cache_directory=tmp_path,
    )
    cache_file = next(tmp_path.glob("*.json"))
    cache_file.write_text("not-json", encoding="utf-8")
    calls = 0

    def reader(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _Reader([_row()])

    second = fetch_overture_buildings(
        projection_route, reader_factory=reader, release_getter=lambda: release,
        cache_directory=tmp_path,
    )
    assert first.features == second.features
    assert calls == 1
    assert not second.cache_hit


def test_cache_cleanup_is_bounded(tmp_path):
    from pole_route.importers.overture_buildings import MAX_CACHE_FILES, _write_cache

    payload = {"raw_count": 0, "intersect_count": 0, "features": []}
    for index in range(MAX_CACHE_FILES + 3):
        _write_cache(tmp_path / f"cache-{index}.json", payload)
    assert len(list(tmp_path.glob("*.json"))) == MAX_CACHE_FILES


def test_confident_match_keeps_osm_geometry_and_merges_provenance():
    osm = _feature("OpenStreetMap", "way/998986400")
    overture = _feature("Overture", "overture-1")
    result = conflate_buildings((osm,), (overture,), _route())
    assert result.matched == 1
    assert len(result.features) == 1
    merged = result.features[0]
    assert merged.parts == osm.parts
    assert merged.source == "OpenStreetMap"
    assert merged.conflation_status == "matched"
    assert merged.matched_source_ids == ("Overture:overture-1",)
    assert {item.source for item in merged.provenance} == {"OpenStreetMap", "Overture"}


def test_unmatched_and_ambiguous_supplements_are_preserved():
    osm = _feature("OpenStreetMap", "way/1")
    ambiguous = _feature("Overture", "overlap", 100.00002, 100.00012)
    unmatched = _feature("Overture", "missing", 100.0005, 100.0006)
    result = conflate_buildings((osm,), (ambiguous, unmatched), _route())
    assert len(result.features) == 3
    assert result.ambiguous == 1
    assert result.unmatched == 1
    assert {item.conflation_status for item in result.features if item.source == "Overture"} == {
        "ambiguous", "supplemental-unmatched"
    }


def test_duplicate_overture_identity_is_not_added_twice():
    overture = _feature("Overture", "same")
    result = conflate_buildings((), (overture, overture), _route())
    assert result.duplicate_source_ids == 1
    assert len(result.features) == 1


def test_combined_fetch_falls_back_to_osm_when_overture_fails():
    osm = OSMContext((), (), (_feature("OpenStreetMap", "way/998986400"),))

    def fail(_route):
        raise OvertureBuildingsError("Overture unavailable")

    result = fetch_surroundings_context(
        _route(), osm_fetcher=lambda _route: osm, overture_fetcher=fail,
    )
    assert result.features == osm.features
    assert result.warnings == ("Overture unavailable",)


def test_combined_fetch_falls_back_on_unexpected_supplement_error():
    osm = OSMContext((), (), (_feature("OpenStreetMap", "way/1"),))
    result = fetch_surroundings_context(
        _route(), osm_fetcher=lambda _route: osm,
        overture_fetcher=lambda _route: (_ for _ in ()).throw(ValueError("bad release")),
    )
    assert result.features == osm.features
    assert result.warnings == ("Overture buildings unavailable: bad release",)


def test_combined_fetch_reports_counts_without_duplicating_a005_building():
    osm_feature = _feature("OpenStreetMap", "way/998986400")
    supplement = _feature("Overture", "overture-a005")
    result = fetch_surroundings_context(
        _route(), osm_fetcher=lambda _route: OSMContext((), (), (osm_feature,)),
        overture_fetcher=lambda _route: OvertureFetchResult(
            (supplement,), 612, 612, "release", 0.1
        ),
    )
    buildings = [item for item in result.features if item.category is OSMFeatureCategory.BUILDING]
    assert len(buildings) == 1
    assert buildings[0].source_id == "way/998986400"
    assert dict(result.metrics)["overture_raw"] == 612


def test_combined_fetch_retries_osm_and_reports_metrics():
    calls = 0
    osm = OSMContext((), (), (_feature("OpenStreetMap", "way/1"),))

    def flaky(_route):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return osm

    result = fetch_surroundings_context(_route(), include_overture=False, osm_fetcher=flaky)
    assert result.features == osm.features
    assert calls == 2
    assert dict(result.metrics)["osm_retries"] == 1


def test_combined_fetch_cancellation_preserves_caller_owned_state():
    from threading import Event

    accepted = [_feature("OpenStreetMap", "way/existing")]
    cancel = Event()
    cancel.set()
    try:
        fetch_surroundings_context(
            _route(), include_overture=False,
            osm_fetcher=lambda _route: OSMContext(), cancel_event=cancel,
        )
    except SurroundFetchCancelled:
        pass
    else:
        raise AssertionError("Cancellation was not observed")
    assert [item.source_id for item in accepted] == ["way/existing"]


def test_long_fetch_cancels_at_batch_boundary_and_never_reports_ready():
    from threading import Event

    route = Route(
        "Long", "long.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.06)),
    )
    cancel = Event()
    updates = []
    calls = 0

    def osm_fetcher(_batch):
        nonlocal calls
        calls += 1
        cancel.set()
        return OSMContext((), ())

    with pytest.raises(SurroundFetchCancelled):
        fetch_surroundings_context(
            route,
            include_overture=False,
            osm_fetcher=osm_fetcher,
            progress_callback=updates.append,
            cancel_event=cancel,
        )

    assert calls == 1
    assert updates[0].message == "Preparing route..."
    assert all(update.message != "Surroundings ready" for update in updates)


def test_progress_reports_sources_conflation_review_and_completion():
    updates = []
    result = fetch_surroundings_context(
        _route(),
        osm_fetcher=lambda _batch: OSMContext((), ()),
        overture_fetcher=lambda _batch: OvertureFetchResult(
            (), 0, 0, "release", 0.01, True,
        ),
        progress_callback=updates.append,
    )

    messages = [update.message for update in updates]
    assert messages == [
        "Preparing route...",
        "Fetching OSM 1/1",
        "Fetching Overture Buildings 1/1",
        "Loaded cached Overture Buildings 1/1",
        "Conflating Buildings...",
        "Preparing review...",
        "Surroundings ready",
    ]
    assert updates[-1].completed == updates[-1].total
    assert dict(result.metrics)["overture_cache_hits"] == 1


def test_osm_only_progress_reaches_ready_without_supplemental_source():
    updates = []

    fetch_surroundings_context(
        _route(),
        include_overture=False,
        osm_fetcher=lambda _batch: OSMContext((), ()),
        progress_callback=updates.append,
    )

    assert [update.message for update in updates][-2:] == [
        "Preparing review...",
        "Surroundings ready",
    ]
    assert updates[-1].completed == updates[-1].total


def test_long_fetch_keeps_partial_osm_batches_and_deduplicates_overlap():
    route = Route(
        "Long", "long.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.09)),
    )
    shared = _feature("OpenStreetMap", "way/shared")
    calls = 0

    def osm_fetcher(_batch):
        nonlocal calls
        calls += 1
        if calls in (2, 3):  # both attempts for the second core interval fail
            raise RuntimeError("batch unavailable")
        return OSMContext((), (), (shared,))

    result = fetch_surroundings_context(
        route, include_overture=False, osm_fetcher=osm_fetcher,
    )
    assert result.features == (shared,)
    assert any("PARTIAL: OSM batch 2/4" in warning for warning in result.warnings)
    metrics = dict(result.metrics)
    assert metrics["batch_count"] == 4
    assert metrics["osm_failed_batches"] == 1


def test_long_fetch_keeps_overture_success_when_one_batch_fails():
    route = Route(
        "Long", "long.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.06)),
    )
    supplement = _feature("Overture", "stable-building")
    calls = 0

    def overture_fetcher(_batch):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OvertureBuildingsError("timeout")
        return OvertureFetchResult((supplement,), 1, 1, "release", 0.01)

    result = fetch_surroundings_context(
        route, osm_fetcher=lambda _batch: OSMContext((), (), ()),
        overture_fetcher=overture_fetcher,
    )
    assert [item.source_id for item in result.features] == ["stable-building"]
    assert any(
        "PARTIAL: Overture batch 2/3 (3000-6000 m)" in warning
        for warning in result.warnings
    )
