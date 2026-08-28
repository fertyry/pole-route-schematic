from __future__ import annotations

from shapely.geometry import Point, mapping

from pole_route.domain.context import (
    FetchCoverage,
    FetchCoverageStatus,
    OSMContext,
    OSMFeatureCategory,
    ProviderFetchState,
)
from pole_route.domain.route import GeoPoint, Route
from pole_route.importers.overture_places import (
    OverturePlacesError,
    OverturePlacesResult,
    fetch_overture_places,
)
from pole_route.importers.surroundings import (
    fetch_surroundings_context,
    retry_failed_surroundings_context,
)


def _route(delta_latitude: float = 0.01) -> Route:
    return Route(
        "Route",
        "route.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.0 + delta_latitude)),
    )


def _row(
    source_id: str,
    category: str,
    *,
    longitude: float = 100.0001,
    confidence: float | None = 0.9,
    name: str = "สถานที่ทดสอบ",
) -> dict:
    row = {
        "id": source_id,
        "geometry": mapping(Point(longitude, 13.005)),
        "categories": {"primary": category},
        "names": {"primary": "Fallback", "common": {"th": [name]}},
        "sources": [{"dataset": "source-dataset", "record_id": f"src-{source_id}"}],
        "version": 3,
        "update_time": "2026-01-01T00:00:00Z",
    }
    if confidence is not None:
        row["confidence"] = confidence
    return row


def _fetch(rows: list[dict]):
    calls = []

    def reader(kind, **kwargs):
        calls.append((kind, kwargs))
        return rows

    result = fetch_overture_places(
        _route(), reader_factory=reader, release_getter=lambda: "2026-08-20.0"
    )
    return result, calls


def test_high_value_place_preserves_identity_thai_name_and_provenance() -> None:
    result, calls = _fetch([_row("place-1", "hospital")])
    feature = result.features[0]

    assert calls[0][0] == "place"
    assert result.raw_count == result.retained_count == result.recommended_count == 1
    assert feature.source == "Overture"
    assert feature.source_id == "place-1"
    assert feature.record_id == "src-place-1"
    assert feature.source_release == "2026-08-20.0"
    assert feature.name == "สถานที่ทดสอบ"
    assert feature.category is OSMFeatureCategory.POI
    assert feature.recommended
    assert feature.provenance[0].dataset == "Overture Places"
    assert feature.provenance[0].license


def test_tier_b_categories_normalize_without_fabricating_osm_identity() -> None:
    result, _calls = _fetch([
        _row("fuel", "gas_station"),
        _row("mall", "shopping_center"),
        _row("stadium", "stadium"),
    ])
    by_id = {item.source_id: item for item in result.features}

    assert by_id["fuel"].category is OSMFeatureCategory.FUEL
    assert by_id["mall"].category is OSMFeatureCategory.SHOP
    assert by_id["stadium"].category is OSMFeatureCategory.POI
    assert all(item.osm_id == 0 and item.osm_type == "" for item in result.features)


def test_generic_business_filter_is_strict_and_never_recommended() -> None:
    result, _calls = _fetch([
        _row("missing-confidence", "restaurant", confidence=None),
        _row("low-confidence", "cafe", confidence=0.5),
        _row("kept", "restaurant", confidence=0.95),
        _row("unknown", "hairdresser", confidence=0.99),
    ])

    assert [item.source_id for item in result.features] == ["kept"]
    assert not result.features[0].recommended
    assert dict(result.features[0].tags)["value_tier"] == "C"


def test_important_place_can_be_retained_farther_but_not_recommended() -> None:
    result, _calls = _fetch([
        _row("school", "school", longitude=100.003),
        _row("restaurant", "restaurant", longitude=100.003, confidence=0.99),
    ])

    assert [item.source_id for item in result.features] == ["school"]
    assert not result.features[0].recommended


def test_places_failure_is_isolated_from_osm_and_buildings() -> None:
    osm = OSMContext(features=())

    def fail(_route: Route) -> OverturePlacesResult:
        raise OverturePlacesError("places unavailable")

    result = fetch_surroundings_context(
        _route(),
        include_overture=False,
        include_places=True,
        osm_fetcher=lambda _route: osm,
        places_fetcher=fail,
    )

    assert result.provider_state("OpenStreetMap") is ProviderFetchState.COMPLETE
    assert result.provider_state("Overture Places") is ProviderFetchState.FAILED
    assert dict(result.metrics)["overture_places_failed_batches"] == 1
    assert any("Overture Places unresolved" in item for item in result.warnings)


def test_places_deduplicate_across_route_batches_and_report_metrics() -> None:
    feature = _fetch([_row("stable", "hospital")])[0].features[0]
    provider = OverturePlacesResult((feature,), 3, 1, 1, "release", 0.2)
    result = fetch_surroundings_context(
        _route(0.06),
        include_overture=False,
        include_places=True,
        osm_fetcher=lambda _route: OSMContext(),
        places_fetcher=lambda _route: provider,
    )

    assert [item.source_id for item in result.features] == ["stable"]
    metrics = dict(result.metrics)
    assert metrics["overture_places_raw"] == 9
    assert metrics["overture_places_retained"] == 3
    assert metrics["overture_places_recommended"] == 3


def test_retry_places_queries_only_failed_interval_and_preserves_old_features() -> None:
    old = _fetch([_row("old", "hospital")])[0].features[0]
    new = _fetch([_row("new", "school")])[0].features[0]
    previous = OSMContext(
        features=(old,),
        coverage=(FetchCoverage(
            "Overture Places", 0, 1000, FetchCoverageStatus.FAILED,
            failure_reason="timeout",
        ),),
    )
    calls: list[str] = []

    def recover(route: Route) -> OverturePlacesResult:
        calls.append(route.name)
        return OverturePlacesResult((new,), 1, 1, 1, "release", 0.1)

    result = retry_failed_surroundings_context(
        _route(), previous, places_fetcher=recover
    )

    assert calls == ["Route [0-1000 m]"]
    assert {item.source_id for item in result.features} == {"old", "new"}
    assert result.provider_state("Overture Places") is ProviderFetchState.COMPLETE
    metrics = dict(result.metrics)
    assert metrics["overture_places_seconds"] == 0.1
    assert metrics["overture_places_raw"] == 1
    assert metrics["overture_places_retained"] == 1
    assert metrics["overture_places_recommended"] == 1
