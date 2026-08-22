"""Background worker for OpenStreetMap context downloads."""

from PySide6.QtCore import QObject, Signal, Slot

from pole_route.domain.route import Route
from pole_route.importers.osm_context import OSMContextError, fetch_osm_context
from pole_route.importers.surroundings import fetch_surroundings_context


class OSMContextWorker(QObject):
    """Fetch route context without blocking the Qt user interface."""

    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, route: Route, include_overture: bool = False) -> None:
        super().__init__()
        self._route = route
        self._include_overture = include_overture

    @Slot()
    def run(self) -> None:
        try:
            if self._include_overture:
                context = fetch_surroundings_context(
                    self._route, include_overture=True, osm_fetcher=fetch_osm_context
                )
            else:
                context = fetch_osm_context(self._route)
        except OSMContextError as error:
            self.failed.emit(str(error))
        except Exception as error:  # defensive boundary around a background task
            self.failed.emit(f"Unexpected OpenStreetMap error: {error}")
        else:
            self.succeeded.emit(context)
        finally:
            self.finished.emit()
