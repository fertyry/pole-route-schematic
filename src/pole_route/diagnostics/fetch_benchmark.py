"""Build and retain lightweight Surround-fetch benchmark records."""

from __future__ import annotations

import ctypes
import json
import os
import tempfile
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pole_route import __version__
from pole_route.domain.context import (
    FetchCoverageStatus,
    OSMContext,
    OSMFeatureCategory,
)
from pole_route.domain.route import Route

SCHEMA_VERSION = 1
MAX_RECORDS = 200
LOG_RELATIVE_PATH = Path("diagnostics") / "fetch_benchmark.jsonl"


class _ProcessMemoryCounters(ctypes.Structure):
    """64-bit-safe Windows PROCESS_MEMORY_COUNTERS layout."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


@dataclass(frozen=True, slots=True)
class FetchRunStart:
    """Small operation snapshot captured before network work begins."""

    run_id: str
    operation: str
    started_at: str
    monotonic_started: float
    process_rss_start_mb: float | None
    process_peak_rss_start_mb: float | None


def start_fetch_run(operation: str) -> FetchRunStart:
    if operation not in {"refresh", "retry_failed_areas"}:
        raise ValueError(f"Unsupported fetch benchmark operation: {operation}")
    rss, peak = process_memory_mb()
    return FetchRunStart(
        str(uuid.uuid4()),
        operation,
        datetime.now(UTC).isoformat(),
        time.perf_counter(),
        rss,
        peak,
    )


def build_fetch_record(
    started: FetchRunStart,
    *,
    route: Route,
    context: OSMContext | None,
    project_path: str | Path,
    project_title: str = "",
    accepted_count: int | None = None,
    outcome: str | None = None,
    error: str = "",
) -> dict[str, Any]:
    """Build one bounded JSON-compatible record from canonical fetch state."""

    completed_at = datetime.now(UTC).isoformat()
    total_elapsed = max(0.0, time.perf_counter() - started.monotonic_started)
    rss_end, peak_end = process_memory_mb()
    peak_delta = (
        max(0.0, peak_end - started.process_peak_rss_start_mb)
        if peak_end is not None and started.process_peak_rss_start_mb is not None
        else None
    )
    metrics = _last_metrics(context)
    unresolved = _unresolved_intervals(context)
    result = outcome or _result_from_context(context)
    categories = _category_counts(context)
    project = Path(project_path)
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": started.run_id,
        "started_at": started.started_at,
        "completed_at": completed_at,
        "operation": started.operation,
        "application_version": __version__,
        "project": {
            "name": project_title.strip() or project.stem,
            "file_name": project.name,
            "folder_name": project.parent.name,
        },
        "route": {
            "name": route.name,
            "length_metres": _route_length(metrics, route),
        },
        "result": result,
        "total_elapsed_seconds": total_elapsed,
        "candidate_count": _candidate_count(context),
        "accepted_count": accepted_count,
        "warning_count": len(context.warnings) if context else int(bool(error)),
        "unresolved_final_interval_count": len(unresolved),
        "unresolved_intervals": unresolved,
        "category_counts": categories,
        "providers": {
            "OpenStreetMap": _osm_metrics(metrics, context),
            "Overture Buildings": _building_metrics(metrics, context),
            "Overture Places": _places_metrics(metrics, context),
        },
        "memory": {
            "process_rss_start_mb": started.process_rss_start_mb,
            "process_rss_end_mb": rss_end,
            "process_peak_rss_mb": peak_end,
            "process_peak_rss_at_start_mb": started.process_peak_rss_start_mb,
            "process_peak_delta_mb": peak_delta,
        },
    }
    if error:
        record["error"] = error
    return record


def benchmark_log_path(project_path: str | Path) -> Path:
    """Return the project-local log path without storing it in the project."""

    return Path(project_path).parent / LOG_RELATIVE_PATH


def append_fetch_record(
    project_path: str | Path,
    record: dict[str, Any],
    *,
    max_records: int = MAX_RECORDS,
) -> Path:
    """Append one UTF-8 JSON line and atomically retain the newest bounded history."""

    if max_records < 1:
        raise ValueError("Fetch benchmark retention must keep at least one record")
    path = benchmark_log_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if len(existing) < max_records:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return path

    retained = [*existing[-(max_records - 1):], line] if max_records > 1 else [line]
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(retained) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def read_fetch_records(project_path: str | Path) -> tuple[dict[str, Any], ...]:
    """Read valid history records; malformed/interrupted lines are ignored."""

    path = benchmark_log_path(project_path)
    if not path.exists():
        return ()
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return tuple(records[-MAX_RECORDS:])


def process_memory_mb(
    *,
    _platform: str | None = None,
    _reader=None,
) -> tuple[float | None, float | None]:
    """Return current and OS-observed process peak RSS on Windows, else unavailable."""

    if (_platform or os.name) != "nt":
        return None, None
    try:
        values = (_reader or _windows_process_memory_bytes)()
    except (AttributeError, OSError, TypeError, ValueError):
        return None, None
    if values is None:
        return None, None
    divisor = 1024 * 1024
    rss_bytes, peak_bytes = values
    return rss_bytes / divisor, peak_bytes / divisor


def _windows_process_memory_bytes(
    kernel32=None,
    psapi=None,
) -> tuple[int, int] | None:
    """Query current/peak working set with explicit 64-bit-safe Windows bindings."""

    kernel32 = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.argtypes = []
    get_current_process.restype = wintypes.HANDLE
    handle = get_current_process()

    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    pointer_type = ctypes.POINTER(_ProcessMemoryCounters)
    get_memory_info = getattr(kernel32, "K32GetProcessMemoryInfo", None)
    if get_memory_info is not None:
        get_memory_info.argtypes = [wintypes.HANDLE, pointer_type, wintypes.DWORD]
        get_memory_info.restype = wintypes.BOOL
        if get_memory_info(handle, ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)

    psapi = psapi or ctypes.WinDLL("psapi", use_last_error=True)
    get_memory_info = psapi.GetProcessMemoryInfo
    get_memory_info.argtypes = [wintypes.HANDLE, pointer_type, wintypes.DWORD]
    get_memory_info.restype = wintypes.BOOL
    if not get_memory_info(handle, ctypes.byref(counters), counters.cb):
        return None
    return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)


def _last_metrics(context: OSMContext | None) -> dict[str, float]:
    return dict(context.metrics) if context else {}


def _route_length(metrics: dict[str, float], route: Route) -> float:
    if "route_length_metres" in metrics:
        return metrics["route_length_metres"]
    from shapely.geometry import LineString

    from pole_route.geometry.projection import MetricProjection

    projection = MetricProjection.for_points(route.points)
    return float(LineString([projection.to_metric(point) for point in route.points]).length)


def _result_from_context(context: OSMContext | None) -> str:
    if context is None:
        return "FAILED"
    failed = sum(item.status is FetchCoverageStatus.FAILED for item in context.coverage)
    successful = sum(item.status is FetchCoverageStatus.SUCCESS for item in context.coverage)
    if not failed:
        return "COMPLETE"
    return "PARTIAL" if successful else "FAILED"


def _candidate_count(context: OSMContext | None) -> int:
    if context is None:
        return 0
    return len(context.roads) + len(context.places) + len(context.features)


def _category_counts(context: OSMContext | None) -> dict[str, int]:
    counts = {"roads_sois": len(context.roads) if context else 0}
    for category in OSMFeatureCategory:
        counts[category.value] = 0
    if context:
        for feature in context.features:
            counts[feature.category.value] += 1
        counts[OSMFeatureCategory.POI.value] += len(context.places)
    return counts


def _unresolved_intervals(context: OSMContext | None) -> list[dict[str, Any]]:
    if context is None:
        return []
    return [
        {
            "provider": item.provider,
            "start_station_m": item.station_start,
            "end_station_m": item.station_end,
            "failure_reason": item.failure_reason,
            "split_depth": item.split_depth,
            "attempts": item.attempts,
        }
        for item in context.coverage
        if item.status is FetchCoverageStatus.FAILED
    ]


def _coverage(provider: str, context: OSMContext | None) -> dict[str, Any]:
    intervals = [item for item in context.coverage if item.provider == provider] if context else []
    failed = [item for item in intervals if item.status is FetchCoverageStatus.FAILED]
    successful = len(intervals) - len(failed)
    if not failed:
        result = "COMPLETE"
    elif successful:
        result = "PARTIAL"
    else:
        result = "FAILED"
    return {
        "result": result,
        "successful_final_interval_count": successful,
        "failed_final_interval_count": len(failed),
    }


def _metric(metrics: dict[str, float], key: str) -> float:
    return metrics.get(key, 0.0)


def _osm_metrics(metrics: dict[str, float], context: OSMContext | None) -> dict[str, Any]:
    return {
        **_coverage("OpenStreetMap", context),
        "primary_interval_count": _metric(metrics, "osm_primary_intervals"),
        "network_request_count": _metric(metrics, "osm_network_requests"),
        "retry_count": _metric(metrics, "osm_retries"),
        "adaptive_split_count": _metric(metrics, "osm_adaptive_splits"),
        "endpoint_fallback_count": _metric(metrics, "osm_endpoint_fallbacks"),
        "fetch_elapsed_seconds": _metric(metrics, "osm_fetch_seconds"),
        "download_elapsed_seconds": _metric(metrics, "osm_download_seconds"),
        "parse_filter_elapsed_seconds": _metric(metrics, "osm_parse_filter_seconds"),
        "merge_elapsed_seconds": _metric(metrics, "osm_merge_seconds"),
        "candidate_count": _metric(metrics, "osm_candidates"),
    }


def _building_metrics(metrics: dict[str, float], context: OSMContext | None) -> dict[str, Any]:
    return {
        **_coverage("Overture Buildings", context),
        "elapsed_seconds": _metric(metrics, "overture_seconds"),
        "cache_hits": _metric(metrics, "overture_cache_hits"),
        "cache_misses": _metric(metrics, "overture_cache_misses"),
        "raw_count": _metric(metrics, "overture_raw"),
        "corridor_count": _metric(metrics, "overture_corridor"),
        "final_count": _metric(metrics, "overture_final_buildings"),
        "conflation_elapsed_seconds": _metric(metrics, "conflation_seconds"),
    }


def _places_metrics(metrics: dict[str, float], context: OSMContext | None) -> dict[str, Any]:
    return {
        **_coverage("Overture Places", context),
        "elapsed_seconds": _metric(metrics, "overture_places_seconds"),
        "request_count": _coverage_request_count("Overture Places", context),
        "raw_count": _metric(metrics, "overture_places_raw"),
        "retained_count": _metric(metrics, "overture_places_retained"),
        "recommended_count": _metric(metrics, "overture_places_recommended"),
        "final_candidate_count": _category_counts(context).get("poi", 0),
    }


def _coverage_request_count(provider: str, context: OSMContext | None) -> int:
    if context is None:
        return 0
    return sum(item.attempts for item in context.coverage if item.provider == provider)
