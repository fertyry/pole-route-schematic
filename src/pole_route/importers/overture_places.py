"""Fetch and normalize high-value Overture Places near a Main Route."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from shapely import from_wkb
from shapely.geometry import LineString, Point, shape

from pole_route.domain.context import (
    ContextFeature,
    ContextGeometryPart,
    FeatureProvenance,
    OSMFeatureCategory,
    OSMGeometryKind,
)
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.projection import MetricProjection


class OverturePlacesError(RuntimeError):
    """Overture Places could not be obtained or interpreted."""


@dataclass(frozen=True, slots=True)
class OverturePlacePolicy:
    tier_a_max_metres: float = 400.0
    tier_b_max_metres: float = 250.0
    tier_c_max_metres: float = 100.0
    tier_a_recommended_metres: float = 250.0
    tier_b_recommended_metres: float = 175.0
    tier_c_minimum_confidence: float = 0.8


DEFAULT_OVERTURE_PLACE_POLICY = OverturePlacePolicy()
OVERTURE_PLACES_LICENSE = "Overture Maps Foundation data"
OVERTURE_CONNECT_TIMEOUT_SECONDS = 15
OVERTURE_REQUEST_TIMEOUT_SECONDS = 60


@dataclass(frozen=True, slots=True)
class OverturePlacesResult:
    features: tuple[ContextFeature, ...]
    raw_count: int
    retained_count: int
    recommended_count: int
    release: str
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class _PlaceClass:
    tier: str
    normalized: str
    category: OSMFeatureCategory


def fetch_overture_places(
    main_route: Route,
    *,
    policy: OverturePlacePolicy = DEFAULT_OVERTURE_PLACE_POLICY,
    reader_factory: Callable[..., object] | None = None,
    release_getter: Callable[[], str] | None = None,
) -> OverturePlacesResult:
    """Read a bounded bbox, then apply metric route distance and value policy."""
    started = time.perf_counter()
    projection = MetricProjection.for_points(main_route.points)
    route_metric = LineString(projection.to_metric(point) for point in main_route.points)
    corridor = route_metric.buffer(max(
        policy.tier_a_max_metres,
        policy.tier_b_max_metres,
        policy.tier_c_max_metres,
    ))
    min_x, min_y, max_x, max_y = corridor.bounds
    southwest = projection.to_geographic(min_x, min_y)
    northeast = projection.to_geographic(max_x, max_y)
    bbox = (southwest.longitude, southwest.latitude, northeast.longitude, northeast.latitude)
    if reader_factory is None or release_getter is None:
        try:
            from overturemaps.core import get_latest_release, record_batch_reader
        except ImportError as error:
            raise OverturePlacesError("Overture Places support is not installed") from error
        reader_factory = reader_factory or record_batch_reader
        release_getter = release_getter or get_latest_release
    try:
        release = str(release_getter())
        reader = reader_factory(
            "place",
            bbox=bbox,
            release=release,
            stac=True,
            connect_timeout=OVERTURE_CONNECT_TIMEOUT_SECONDS,
            request_timeout=OVERTURE_REQUEST_TIMEOUT_SECONDS,
        )
        rows = _rows_from_reader(reader)
    except Exception as error:
        raise OverturePlacesError(f"Could not download Overture Places: {error}") from error

    features: list[ContextFeature] = []
    seen: set[str] = set()
    raw_count = 0
    for row in rows:
        raw_count += 1
        source_id = str(row.get("id") or "").strip()
        if not source_id or source_id in seen:
            continue
        point = _row_point(row)
        classification = _classify(row.get("categories"))
        if point is None or classification is None:
            continue
        distance = Point(projection.to_metric(point)).distance(route_metric)
        confidence = _confidence(row)
        if not _retain(classification.tier, distance, confidence, policy):
            continue
        recommended = _recommended(classification.tier, distance, confidence, policy)
        seen.add(source_id)
        features.append(_context_feature(
            row,
            point,
            classification,
            distance,
            confidence,
            recommended,
            release,
        ))
    features.sort(key=lambda item: (not item.recommended, item.name or "", item.source_id))
    return OverturePlacesResult(
        tuple(features),
        raw_count,
        len(features),
        sum(feature.recommended for feature in features),
        release,
        time.perf_counter() - started,
    )


def _classify(value: object) -> _PlaceClass | None:
    primary = ""
    if isinstance(value, Mapping):
        primary = str(value.get("primary") or "").strip().casefold()
    elif value:
        primary = str(value).strip().casefold()
    token = primary.replace("-", "_").replace(" ", "_")
    tier_a = {
        "hospital": "hospital",
        "school": "school",
        "university": "university",
        "college": "university",
        "place_of_worship": "place_of_worship",
        "temple": "place_of_worship",
        "government": "government",
        "government_office": "government",
        "public_facility": "government",
    }
    tier_b = {
        "market": "market",
        "marketplace": "market",
        "gas_station": "fuel",
        "fuel": "fuel",
        "shopping_center": "mall",
        "shopping_centre": "mall",
        "mall": "mall",
        "stadium": "stadium",
        "sports_center": "sports_center",
        "sports_centre": "sports_center",
        "tourist_attraction": "attraction",
        "attraction": "attraction",
        "museum": "attraction",
    }
    tier_c = {
        "shop": "business",
        "store": "business",
        "restaurant": "restaurant",
        "cafe": "cafe",
        "coffee_shop": "cafe",
    }
    if token in tier_a:
        return _PlaceClass("A", tier_a[token], OSMFeatureCategory.POI)
    if token in tier_b:
        category = (
            OSMFeatureCategory.FUEL if tier_b[token] == "fuel"
            else OSMFeatureCategory.SHOP if tier_b[token] in {"market", "mall"}
            else OSMFeatureCategory.POI
        )
        return _PlaceClass("B", tier_b[token], category)
    if token in tier_c:
        return _PlaceClass("C", tier_c[token], OSMFeatureCategory.SHOP)
    return None


def _retain(
    tier: str,
    distance: float,
    confidence: float | None,
    policy: OverturePlacePolicy,
) -> bool:
    if tier == "A":
        return distance <= policy.tier_a_max_metres
    if tier == "B":
        return distance <= policy.tier_b_max_metres
    return (
        distance <= policy.tier_c_max_metres
        and confidence is not None
        and confidence >= policy.tier_c_minimum_confidence
    )


def _recommended(
    tier: str,
    distance: float,
    confidence: float | None,
    policy: OverturePlacePolicy,
) -> bool:
    if tier == "A":
        return distance <= policy.tier_a_recommended_metres
    if tier == "B":
        return distance <= policy.tier_b_recommended_metres
    return False


def _context_feature(
    row: Mapping[str, object],
    point: GeoPoint,
    classification: _PlaceClass,
    distance: float,
    confidence: float | None,
    recommended: bool,
    release: str,
) -> ContextFeature:
    source_id = str(row["id"])
    name = _name(row.get("names"))
    sources = row.get("sources") if isinstance(row.get("sources"), list) else []
    source = sources[0] if sources and isinstance(sources[0], Mapping) else {}
    provenance = FeatureProvenance(
        source="Overture",
        source_id=source_id,
        provider=str(source.get("dataset") or source.get("property") or ""),
        dataset="Overture Places",
        record_id=str(source.get("record_id") or source_id),
        release=release,
        version=str(row.get("version") or ""),
        update_time=str(row.get("update_time") or ""),
        confidence=confidence,
        license=OVERTURE_PLACES_LICENSE,
    )
    return ContextFeature(
        "",
        0,
        classification.category,
        OSMGeometryKind.POINT,
        (ContextGeometryPart((point,)),),
        name=name,
        tags=(("place_category", classification.normalized), ("value_tier", classification.tier)),
        recommended=recommended,
        recommendation=(
            f"Tier {classification.tier} landmark {distance:.0f} m from Main Route"
            if recommended
            else f"Tier {classification.tier} place {distance:.0f} m from Main Route; review manually"
        ),
        source="Overture",
        source_id=source_id,
        source_release=release,
        source_version=str(row.get("version") or ""),
        provider=provenance.provider,
        dataset="Overture Places",
        record_id=provenance.record_id,
        update_time=provenance.update_time,
        confidence=confidence,
        source_license=OVERTURE_PLACES_LICENSE,
        provenance=(provenance,),
    )


def _row_point(row: Mapping[str, object]) -> GeoPoint | None:
    value = row.get("geometry")
    try:
        geometry = (
            from_wkb(bytes(value))
            if isinstance(value, (bytes, bytearray, memoryview))
            else shape(value)
        )
        if not isinstance(geometry, Point) or geometry.is_empty:
            return None
        return GeoPoint(float(geometry.x), float(geometry.y))
    except (TypeError, ValueError, AttributeError):
        return None


def _rows_from_reader(reader: object) -> Iterable[Mapping[str, object]]:
    if reader is None:
        return ()
    if isinstance(reader, Iterable):
        def iterate():
            for batch in reader:
                if hasattr(batch, "to_pylist"):
                    yield from batch.to_pylist()
                elif isinstance(batch, Mapping):
                    yield batch
                else:
                    yield from batch
        return iterate()
    table = reader.read_all() if hasattr(reader, "read_all") else reader
    if hasattr(table, "to_pylist"):
        return table.to_pylist()
    if isinstance(table, Iterable):
        return table
    raise TypeError("Overture reader returned an unsupported result")


def _confidence(row: Mapping[str, object]) -> float | None:
    value = row.get("confidence")
    return float(value) if isinstance(value, (int, float)) else None


def _name(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    common = value.get("common")
    if isinstance(common, Mapping):
        thai = _first(common.get("th"))
        if thai:
            return thai
    return _first(value.get("primary"))


def _first(value: object) -> str | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return str(value).strip() if value and str(value).strip() else None
