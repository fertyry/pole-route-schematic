"""Fetch and normalize supplemental Overture building footprints."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from shapely import from_wkb, make_valid
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, shape
from shapely.strtree import STRtree

from pole_route.domain.context import (
    ContextFeature, ContextGeometryPart, FeatureProvenance, OSMFeatureCategory,
    OSMGeometryKind,
)
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.projection import MetricProjection

OVERTURE_BUILDING_CORRIDOR_METRES = 100.0
MAX_CACHE_FILES = 8
OVERTURE_CONNECT_TIMEOUT_SECONDS = 15
OVERTURE_REQUEST_TIMEOUT_SECONDS = 60


class OvertureBuildingsError(RuntimeError):
    """Supplemental Overture buildings could not be obtained."""


@dataclass(frozen=True, slots=True)
class OvertureFetchResult:
    features: tuple[ContextFeature, ...]
    raw_count: int
    intersect_count: int
    release: str
    elapsed_seconds: float
    cache_hit: bool = False


@dataclass(frozen=True, slots=True)
class BuildingConflationResult:
    features: tuple[ContextFeature, ...]
    matched: int
    unmatched: int
    ambiguous: int
    duplicate_source_ids: int


def fetch_overture_buildings(
    main_route: Route,
    corridor_metres: float = OVERTURE_BUILDING_CORRIDOR_METRES,
    *,
    reader_factory: Callable[..., object] | None = None,
    release_getter: Callable[[], str] | None = None,
    cache_directory: Path | None = None,
) -> OvertureFetchResult:
    """Read only Overture building rows intersecting the route corridor."""
    if corridor_metres <= 0:
        raise ValueError("Building corridor must be greater than zero")
    started = time.perf_counter()
    projection = MetricProjection.for_points(main_route.points)
    route_metric = LineString([projection.to_metric(point) for point in main_route.points])
    corridor = route_metric.buffer(corridor_metres)
    min_x, min_y, max_x, max_y = corridor.bounds
    southwest = projection.to_geographic(min_x, min_y)
    northeast = projection.to_geographic(max_x, max_y)
    bbox = (southwest.longitude, southwest.latitude, northeast.longitude, northeast.latitude)

    if reader_factory is None or release_getter is None:
        try:
            from overturemaps.core import get_latest_release, record_batch_reader
        except ImportError as error:
            raise OvertureBuildingsError(
                "Overture building support is not installed; OpenStreetMap results are still available"
            ) from error
        reader_factory = reader_factory or record_batch_reader
        release_getter = release_getter or get_latest_release
    try:
        release = str(release_getter())
    except Exception as error:
        raise OvertureBuildingsError(f"Could not determine Overture release: {error}") from error

    cache_path = _cache_path(cache_directory, release, bbox, corridor_metres)
    cached = _read_cache(cache_path)
    if cached is not None:
        return OvertureFetchResult(
            tuple(_feature_from_cache(item) for item in cached["features"]),
            int(cached["raw_count"]), int(cached["intersect_count"]), release,
            time.perf_counter() - started, True,
        )
    try:
        reader = reader_factory(
            "building", bbox=bbox, release=release, stac=True,
            connect_timeout=OVERTURE_CONNECT_TIMEOUT_SECONDS,
            request_timeout=OVERTURE_REQUEST_TIMEOUT_SECONDS,
        )
        rows = _rows_from_reader(reader)
    except Exception as error:
        raise OvertureBuildingsError(f"Could not download Overture buildings: {error}") from error

    features: list[ContextFeature] = []
    seen: set[str] = set()
    raw_count = 0
    try:
        for row in rows:
            raw_count += 1
            source_id = str(row.get("id") or "").strip()
            if not source_id or source_id in seen:
                continue
            geometry = _row_geometry(row)
            if geometry is None:
                continue
            metric = _metric_polygon(geometry, projection)
            if metric is None or not metric.intersects(corridor):
                continue
            seen.add(source_id)
            features.append(_context_feature(row, geometry, release))
    except Exception as error:
        raise OvertureBuildingsError(f"Could not read Overture buildings: {error}") from error
    payload = {
        "raw_count": raw_count, "intersect_count": len(features),
        "features": [_feature_to_cache(item) for item in features],
    }
    _write_cache(cache_path, payload)
    return OvertureFetchResult(
        tuple(features), raw_count, len(features), release, time.perf_counter() - started,
        False,
    )


def conflate_buildings(
    osm_features: Iterable[ContextFeature],
    overture_features: Iterable[ContextFeature],
    main_route: Route,
) -> BuildingConflationResult:
    """Prefer OSM footprint geometry and add only confident Overture supplements."""
    osm = list(osm_features)
    overture: list[ContextFeature] = []
    seen_ids: set[str] = set()
    duplicates = 0
    for feature in overture_features:
        if feature.source_id in seen_ids:
            duplicates += 1
            continue
        seen_ids.add(feature.source_id)
        overture.append(feature)
    projection = MetricProjection.for_points(main_route.points)
    osm_buildings = [item for item in osm if item.category is OSMFeatureCategory.BUILDING]
    osm_shapes = [_feature_metric_polygon(item, projection) for item in osm_buildings]
    valid_pairs = [(item, geom) for item, geom in zip(osm_buildings, osm_shapes) if geom is not None]
    tree = STRtree([geom for _, geom in valid_pairs]) if valid_pairs else None
    merged_by_key = {item.feature_key: item for item in osm}
    supplements: list[ContextFeature] = []
    matched = ambiguous = unmatched = 0
    for feature in overture:
        candidate = _feature_metric_polygon(feature, projection)
        possible = [] if tree is None or candidate is None else list(tree.query(candidate))
        scores: list[tuple[float, float, float, int]] = []
        for index in possible:
            other = valid_pairs[int(index)][1]
            intersection = candidate.intersection(other).area
            if intersection <= 0:
                continue
            union = candidate.union(other).area
            smaller = min(candidate.area, other.area)
            iou = intersection / union if union else 0.0
            coverage = intersection / smaller if smaller else 0.0
            area_ratio = smaller / max(candidate.area, other.area)
            scores.append((coverage, iou, area_ratio, int(index)))
        scores.sort(reverse=True)
        confident = scores and scores[0][0] >= 0.88 and (
            scores[0][1] >= 0.55 or scores[0][2] >= 0.70
        )
        uncertain = scores and scores[0][0] >= 0.25
        if confident:
            matched += 1
            osm_feature = valid_pairs[scores[0][3]][0]
            provenance = _merge_provenance(osm_feature, feature)
            matched_ids = tuple(dict.fromkeys((*osm_feature.matched_source_ids,
                                               f"Overture:{feature.source_id}")))
            merged_by_key[osm_feature.feature_key] = replace(
                osm_feature, provenance=provenance, conflation_status="matched",
                matched_source_ids=matched_ids,
            )
        elif uncertain:
            ambiguous += 1
            matched_ids = tuple(
                f"OpenStreetMap:{valid_pairs[item[3]][0].source_id}" for item in scores[:3]
            )
            supplements.append(replace(
                feature, conflation_status="ambiguous", matched_source_ids=matched_ids,
                recommended=False,
                recommendation="Possible overlap with an OSM building; review manually",
            ))
        else:
            unmatched += 1
            supplements.append(replace(
                feature, conflation_status="supplemental-unmatched",
                recommendation="Supplemental Overture building not represented in OSM",
            ))
    return BuildingConflationResult(
        tuple((*merged_by_key.values(), *supplements)), matched, unmatched, ambiguous, duplicates
    )


def _rows_from_reader(reader: object) -> Iterable[Mapping[str, object]]:
    if reader is None:
        return ()
    if isinstance(reader, Iterable):
        def iter_batches():
            for batch in reader:
                if hasattr(batch, "to_pylist"):
                    yield from batch.to_pylist()
                elif isinstance(batch, Mapping):
                    yield batch
                else:
                    yield from batch
        return iter_batches()
    table = reader.read_all() if hasattr(reader, "read_all") else reader
    if hasattr(table, "to_pylist"):
        return table.to_pylist()
    if isinstance(table, Iterable):
        return table
    raise TypeError("Overture reader returned an unsupported result")


def _row_geometry(row: Mapping[str, object]):
    value = row.get("geometry")
    try:
        geometry = from_wkb(bytes(value)) if isinstance(value, (bytes, bytearray, memoryview)) else shape(value)
        if not geometry.is_valid:
            geometry = make_valid(geometry)
        polygons = _polygon_parts(geometry)
        polygons = [item for item in polygons if isinstance(item, Polygon) and not item.is_empty]
        if not polygons:
            return None
        return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    except (TypeError, ValueError, AttributeError):
        return None


def _polygon_parts(geometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, (MultiPolygon, GeometryCollection)):
        return [
            polygon
            for part in geometry.geoms
            for polygon in _polygon_parts(part)
        ]
    return []


def _context_feature(row: Mapping[str, object], geometry, release: str) -> ContextFeature:
    source_id = str(row["id"])
    sources = row.get("sources") if isinstance(row.get("sources"), list) else []
    source = sources[0] if sources and isinstance(sources[0], Mapping) else {}
    confidence = row.get("confidence", source.get("confidence"))
    provenance = FeatureProvenance(
        source="Overture", source_id=source_id,
        provider=str(source.get("dataset") or source.get("property") or ""),
        dataset="Overture Buildings", record_id=str(source.get("record_id") or source_id),
        release=release, version=str(row.get("version") or ""),
        update_time=str(row.get("update_time") or ""),
        confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
    )
    kind = OSMGeometryKind.POLYGON if isinstance(geometry, Polygon) else OSMGeometryKind.MULTIPOLYGON
    polygons = [geometry] if isinstance(geometry, Polygon) else geometry.geoms
    parts = tuple(ContextGeometryPart(
        tuple(GeoPoint(float(x), float(y)) for x, y, *_ in polygon.exterior.coords),
        tuple(tuple(GeoPoint(float(x), float(y)) for x, y, *_ in ring.coords)
              for ring in polygon.interiors),
    ) for polygon in polygons)
    return ContextFeature(
        "", 0, OSMFeatureCategory.BUILDING, kind, parts,
        name=_overture_name(row.get("names")),
        tags=tuple((key, str(row[key])) for key in ("subtype", "class") if row.get(key)),
        source="Overture", source_id=source_id, source_release=release,
        source_version=str(row.get("version") or ""), dataset="Overture Buildings",
        record_id=source_id, update_time=str(row.get("update_time") or ""),
        confidence=provenance.confidence, provenance=(provenance,),
    )


def _overture_name(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    common = value.get("common")
    if isinstance(common, Mapping):
        thai = common.get("th")
        name = _first_name(thai)
        if name:
            return name
    primary = value.get("primary")
    return _first_name(primary)


def _first_name(value: object) -> str | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return str(value).strip() if value and str(value).strip() else None


def _metric_polygon(geometry, projection: MetricProjection):
    def project(polygon):
        return Polygon(
            [projection.to_metric(GeoPoint(float(x), float(y))) for x, y, *_ in polygon.exterior.coords],
            [[projection.to_metric(GeoPoint(float(x), float(y))) for x, y, *_ in ring.coords]
             for ring in polygon.interiors],
        )
    try:
        return project(geometry) if isinstance(geometry, Polygon) else MultiPolygon([project(item) for item in geometry.geoms])
    except (ValueError, TypeError):
        return None


def _feature_metric_polygon(feature: ContextFeature, projection: MetricProjection):
    try:
        polygons = [Polygon(
            [projection.to_metric(point) for point in part.coordinates],
            [[projection.to_metric(point) for point in hole] for hole in part.holes],
        ) for part in feature.parts]
        return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    except ValueError:
        return None


def _merge_provenance(osm: ContextFeature, overture: ContextFeature):
    osm_record = FeatureProvenance("OpenStreetMap", osm.source_id, record_id=osm.source_id)
    overture_record = FeatureProvenance(
        overture.source, overture.source_id, provider=overture.provider,
        dataset=overture.dataset, resource=overture.resource,
        record_id=overture.record_id or overture.source_id,
        release=overture.source_release, version=overture.source_version,
        update_time=overture.update_time, confidence=overture.confidence,
        license=overture.source_license,
    )
    records = (*osm.provenance, osm_record, *overture.provenance, overture_record)
    unique = {(item.source, item.source_id, item.release): item for item in records}
    return tuple(unique.values())


def _cache_path(directory: Path | None, release: str, bbox, corridor: float) -> Path:
    base = directory or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PoleRoute Schematic" / "cache" / "overture"
    key = "_".join((release.replace("/", "-"), *(f"{value:.5f}" for value in bbox), f"{corridor:.1f}"))
    return base / f"{key}.json"


def _read_cache(path: Path):
    try:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        if not isinstance(payload.get("features"), list):
            return None
        int(payload["raw_count"])
        int(payload["intersect_count"])
        return payload
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _write_cache(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        files = sorted(
            path.parent.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for old in files[MAX_CACHE_FILES:]:
            old.unlink(missing_ok=True)
    except OSError:
        pass
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _feature_to_cache(feature: ContextFeature) -> dict:
    from pole_route.project.storage import osm_features_to_data
    return osm_features_to_data((feature,))[0]


def _feature_from_cache(data: dict) -> ContextFeature:
    from pole_route.project.storage import osm_features_from_data
    return osm_features_from_data([data])[0]
