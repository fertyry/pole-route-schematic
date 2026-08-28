"""Background worker for reviewed online surroundings downloads."""

from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from pole_route.domain.context import OSMContext
from pole_route.domain.route import Route
from pole_route.importers.osm_context import OSMContextError, fetch_osm_context
from pole_route.importers.surroundings import (
    FetchProgress,
    SurroundFetchCancelled,
    fetch_surroundings_context,
    retry_failed_surroundings_context,
)


class OSMContextWorker(QObject):
    """Fetch route context without blocking the Qt user interface."""

    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(str, int, int)
    finished = Signal()

    def __init__(
        self,
        route: Route,
        include_overture: bool = False,
        include_places: bool = False,
        retry_context: OSMContext | None = None,
    ) -> None:
        super().__init__()
        self._route = route
        self._include_overture = include_overture
        self._include_places = include_places
        self._retry_context = retry_context
        self._cancel_event = Event()

    def cancel(self) -> None:
        """Request cooperative cancellation at the next source/batch boundary."""
        self._cancel_event.set()

    def _report_progress(self, update: FetchProgress) -> None:
        self.progress.emit(update.message, update.completed, update.total)

    @Slot()
    def run(self) -> None:
        try:
            if self._retry_context is None:
                context = fetch_surroundings_context(
                    self._route,
                    include_overture=self._include_overture,
                    include_places=self._include_places,
                    osm_fetcher=fetch_osm_context,
                    progress_callback=self._report_progress,
                    cancel_event=self._cancel_event,
                )
            else:
                context = retry_failed_surroundings_context(
                    self._route,
                    self._retry_context,
                    osm_fetcher=fetch_osm_context,
                    progress_callback=self._report_progress,
                    cancel_event=self._cancel_event,
                )
        except SurroundFetchCancelled:
            self.cancelled.emit()
        except OSMContextError as error:
            self.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001 - background task safety boundary
            self.failed.emit(f"Unexpected OpenStreetMap error: {error}")
        else:
            self.succeeded.emit(context)
        finally:
            self.finished.emit()
