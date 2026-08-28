import json

import pytest

from pole_route.diagnostics.fetch_benchmark import (
    _windows_process_memory_bytes,
    append_fetch_record,
    benchmark_log_path,
    build_fetch_record,
    process_memory_mb,
    read_fetch_records,
    start_fetch_run,
)
from pole_route.domain.context import (
    ContextFeature,
    ContextGeometryPart,
    ContextRoad,
    FetchCoverage,
    FetchCoverageStatus,
    OSMContext,
    OSMFeatureCategory,
    OSMGeometryKind,
)
from pole_route.domain.route import GeoPoint, Route
from pole_route.project.storage import load_project_file, save_project_file
from pole_route.ui.fetch_diagnostics_dialog import FetchDiagnosticsDialog
from pole_route.ui.main_window import MainWindow


class _FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class _FakeKernel32:
    def __init__(self, callback):
        self.GetCurrentProcess = _FakeFunction(lambda: 12345)
        self.K32GetProcessMemoryInfo = _FakeFunction(callback)


class _FakePsapi:
    def __init__(self, callback):
        self.GetProcessMemoryInfo = _FakeFunction(callback)


def _route(name="เส้นทางทดสอบ") -> Route:
    return Route(
        name,
        "test.kml",
        (GeoPoint(100.0, 13.0), GeoPoint(100.01, 13.0)),
    )


def _feature(category=OSMFeatureCategory.BUILDING) -> ContextFeature:
    return ContextFeature(
        "way",
        100 + list(OSMFeatureCategory).index(category),
        category,
        OSMGeometryKind.POLYGON,
        (ContextGeometryPart((
            GeoPoint(100.0, 13.0),
            GeoPoint(100.001, 13.0),
            GeoPoint(100.001, 13.001),
            GeoPoint(100.0, 13.0),
        )),),
        name="อาคารทดสอบ",
    )


def _context(*, failed=False) -> OSMContext:
    status = FetchCoverageStatus.FAILED if failed else FetchCoverageStatus.SUCCESS
    return OSMContext(
        roads=(ContextRoad(_route("ซอยทดสอบ"), "residential", 6.0),),
        features=(_feature(), _feature(OSMFeatureCategory.POI)),
        warnings=("provider warning",) if failed else (),
        metrics=(
            ("route_length_metres", 1084.2),
            ("osm_primary_intervals", 1.0),
            ("osm_network_requests", 2.0),
            ("osm_retries", 1.0),
            ("osm_adaptive_splits", 1.0),
            ("osm_endpoint_fallbacks", 1.0),
            ("osm_fetch_seconds", 2.5),
            ("osm_parse_filter_seconds", 0.4),
            ("osm_merge_seconds", 0.1),
            ("osm_candidates", 3.0),
            ("overture_seconds", 1.2),
            ("overture_cache_hits", 1.0),
            ("overture_cache_misses", 0.0),
            ("overture_raw", 8.0),
            ("overture_corridor", 3.0),
            ("overture_final_buildings", 1.0),
            ("conflation_seconds", 0.2),
            ("overture_places_seconds", 0.8),
            ("overture_places_raw", 10.0),
            ("overture_places_retained", 2.0),
            ("overture_places_recommended", 1.0),
        ),
        coverage=(
            FetchCoverage("OpenStreetMap", 0, 1084.2, status, 1, 2, 1,
                          "timeout" if failed else ""),
            FetchCoverage("Overture Buildings", 0, 1084.2,
                          FetchCoverageStatus.SUCCESS),
            FetchCoverage("Overture Places", 0, 1084.2,
                          FetchCoverageStatus.SUCCESS),
        ),
    )


def _record(project, *, operation="refresh", context=None, outcome=None):
    return build_fetch_record(
        start_fetch_run(operation),
        route=_route(),
        context=context if context is not None else _context(),
        project_path=project,
        project_title="โครงการทดสอบ",
        accepted_count=4,
        outcome=outcome,
    )


def _fill_memory(rss_bytes, peak_bytes):
    def callback(_handle, counters_pointer, _size):
        counters_pointer._obj.WorkingSetSize = rss_bytes
        counters_pointer._obj.PeakWorkingSetSize = peak_bytes
        return 1

    return callback


def test_windows_memory_api_uses_explicit_binding_and_returns_bytes() -> None:
    kernel = _FakeKernel32(_fill_memory(512 * 1024**2, 1536 * 1024**2))
    assert _windows_process_memory_bytes(kernel, _FakePsapi(lambda *_args: 0)) == (
        512 * 1024**2, 1536 * 1024**2
    )
    assert kernel.GetCurrentProcess.restype is not None
    assert kernel.K32GetProcessMemoryInfo.argtypes is not None


def test_windows_memory_api_falls_back_to_psapi() -> None:
    kernel = _FakeKernel32(lambda *_args: 0)
    psapi = _FakePsapi(_fill_memory(256 * 1024**2, 2048 * 1024**2))
    assert _windows_process_memory_bytes(kernel, psapi) == (
        256 * 1024**2, 2048 * 1024**2
    )
    assert psapi.GetProcessMemoryInfo.argtypes is not None


def test_memory_values_convert_bytes_to_mb_and_failure_is_nonfatal() -> None:
    assert process_memory_mb(
        _platform="nt", _reader=lambda: (512 * 1024**2, 1536 * 1024**2)
    ) == (512.0, 1536.0)
    assert process_memory_mb(_platform="nt", _reader=lambda: None) == (None, None)

    def fail():
        raise OSError("API unavailable")

    assert process_memory_mb(_platform="nt", _reader=fail) == (None, None)
    assert process_memory_mb(
        _platform="posix", _reader=lambda: pytest.fail("must not call Windows API")
    ) == (None, None)


def test_record_contains_identity_metrics_categories_and_unresolved(tmp_path) -> None:
    project = tmp_path / "งานไทย" / "A001.prs"
    context = _context(failed=True)
    record = _record(project, context=context)

    assert record["schema_version"] == 1
    assert record["operation"] == "refresh"
    assert record["project"] == {
        "name": "โครงการทดสอบ", "file_name": "A001.prs", "folder_name": "งานไทย"
    }
    assert record["route"]["name"] == "เส้นทางทดสอบ"
    assert record["route"]["length_metres"] == 1084.2
    assert record["result"] == "PARTIAL"
    assert record["candidate_count"] == 3
    assert record["accepted_count"] == 4
    assert record["category_counts"]["roads_sois"] == 1
    assert record["category_counts"]["building"] == 1
    assert record["category_counts"]["poi"] == 1
    assert record["providers"]["OpenStreetMap"]["network_request_count"] == 2
    assert record["providers"]["Overture Buildings"]["cache_hits"] == 1
    assert record["providers"]["Overture Places"]["retained_count"] == 2
    assert record["unresolved_intervals"] == [{
        "provider": "OpenStreetMap",
        "start_station_m": 0,
        "end_station_m": 1084.2,
        "failure_reason": "timeout",
        "split_depth": 1,
        "attempts": 2,
    }]


def test_benchmark_json_stores_start_end_peak_and_peak_baseline_delta(
    tmp_path, monkeypatch
) -> None:
    values = iter(((100.0, 120.0), (130.0, 180.0)))
    monkeypatch.setattr(
        "pole_route.diagnostics.fetch_benchmark.process_memory_mb", lambda: next(values)
    )
    started = start_fetch_run("refresh")
    record = build_fetch_record(
        started, route=_route(), context=_context(), project_path=tmp_path / "A001.prs"
    )
    assert record["memory"] == {
        "process_rss_start_mb": 100.0,
        "process_rss_end_mb": 130.0,
        "process_peak_rss_mb": 180.0,
        "process_peak_rss_at_start_mb": 120.0,
        "process_peak_delta_mb": 60.0,
    }


@pytest.mark.parametrize(
    ("context", "outcome", "expected"),
    [(_context(), None, "COMPLETE"), (_context(failed=True), None, "PARTIAL"),
     (None, "FAILED", "FAILED"), (None, "CANCELLED", "CANCELLED")],
)
def test_result_states(tmp_path, context, outcome, expected) -> None:
    record = build_fetch_record(
        start_fetch_run("refresh"), route=_route(), context=context,
        project_path=tmp_path / "a.prs", outcome=outcome,
    )
    assert record["result"] == expected


def test_jsonl_append_utf8_and_retry_operation(tmp_path) -> None:
    project = tmp_path / "A001.prs"
    append_fetch_record(project, _record(project))
    append_fetch_record(project, _record(project, operation="retry_failed_areas"))

    lines = benchmark_log_path(project).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(isinstance(json.loads(line), dict) for line in lines)
    assert "โครงการทดสอบ" in lines[0]
    assert [item["operation"] for item in read_fetch_records(project)] == [
        "refresh", "retry_failed_areas"
    ]


def test_retention_keeps_newest_records(tmp_path) -> None:
    project = tmp_path / "A001.prs"
    for index in range(5):
        record = _record(project)
        record["sequence"] = index
        append_fetch_record(project, record, max_records=3)
    assert [item["sequence"] for item in read_fetch_records(project)] == [2, 3, 4]


def test_reader_skips_malformed_interrupted_line(tmp_path) -> None:
    project = tmp_path / "A001.prs"
    path = benchmark_log_path(project)
    path.parent.mkdir(parents=True)
    path.write_text('{"run_id":"ok"}\n{"broken":', encoding="utf-8")
    assert read_fetch_records(project) == ({"run_id": "ok"},)


def test_diagnostics_are_external_to_project_schema(tmp_path) -> None:
    project = tmp_path / "A001.prs"
    save_project_file(project, {"routes": []})
    append_fetch_record(project, _record(project))
    document = load_project_file(project)
    assert document["version"] == 1
    assert "fetch_benchmark" not in document
    assert "diagnostics" not in document


def test_main_window_logging_is_nonfatal_and_review_creates_no_record(
    qtbot, tmp_path, monkeypatch
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.project_path = str(tmp_path / "A001.prs")
    window.current_route = _route()
    window.surrounding_candidates = _context()

    def fail_write(*_args, **_kwargs):
        raise OSError("read only folder")

    monkeypatch.setattr("pole_route.ui.main_window.append_fetch_record", fail_write)
    window._record_fetch_benchmark(start_fetch_run("refresh"), _context())
    assert "diagnostics could not be written" in window.statusBar().currentMessage()
    assert not benchmark_log_path(window.project_path).exists()


def test_refresh_and_retry_finished_each_write_one_record(qtbot, tmp_path, monkeypatch) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.project_path = str(tmp_path / "A001.prs")
    window.current_route = _route()
    window.surrounding_candidates = _context(failed=True)
    window.fetch_surroundings_action.setEnabled(False)
    monkeypatch.setattr(window, "_review_surroundings", lambda _context: None)
    written = []
    monkeypatch.setattr(
        "pole_route.ui.main_window.append_fetch_record",
        lambda _path, record: written.append(record),
    )

    for operation in ("refresh", "retry_failed_areas"):
        window._pending_fetch_benchmark = start_fetch_run(operation)
        window._pending_osm_context = _context()
        window._surroundings_fetch_finished()

    assert [record["operation"] for record in written] == [
        "refresh", "retry_failed_areas"
    ]

    monkeypatch.setattr(window, "_review_surroundings", lambda _context: None)
    window._review_cached_surroundings()
    assert not benchmark_log_path(window.project_path).exists()


def test_unsaved_project_does_not_write_and_empty_viewer_is_safe(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_route = _route()
    window._record_fetch_benchmark(start_fetch_run("refresh"), _context())

    dialog = FetchDiagnosticsDialog(tmp_path / "not-saved-yet.prs")
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 0


def test_viewer_shows_summary_row(qtbot, tmp_path) -> None:
    project = tmp_path / "A001.prs"
    record = _record(project)
    record["memory"] = {
        "process_rss_end_mb": 64.0,
        "process_peak_rss_mb": 1536.0,
    }
    append_fetch_record(project, record)
    dialog = FetchDiagnosticsDialog(project)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 2).text() == "เส้นทางทดสอบ"
    assert dialog.table.horizontalHeaderItem(16).text() == "Peak RAM"
    assert dialog.table.item(0, 16).text() == "1.50 GB"


def test_viewer_formats_peak_mb_and_old_record_without_memory(qtbot, tmp_path) -> None:
    project = tmp_path / "A001.prs"
    small_peak = _record(project)
    small_peak["memory"] = {"process_peak_rss_mb": 768.0}
    old_record = _record(project)
    old_record.pop("memory")
    append_fetch_record(project, small_peak)
    append_fetch_record(project, old_record)

    dialog = FetchDiagnosticsDialog(project)
    qtbot.addWidget(dialog)
    assert dialog.table.item(0, 16).text() == "—"
    assert dialog.table.item(1, 16).text() == "768 MB"
