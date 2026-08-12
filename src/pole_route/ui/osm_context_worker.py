"""Background worker for OpenStreetMap context downloads."""

from PySide6.QtCore import QObject, Signal, Slot

from pole_route.domain.route import Route
from pole_route.importers.osm_context import OSMContextError, fetch_osm_context


class OSMContextWorker(QObject):
    """Fetch route context without blocking the Qt user interface."""

    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, route: Route) -> None:
        super().__init__()
        self._route = route

    @Slot()
    def run(self) -> None:
        try:
            context = fetch_osm_context(self._route)
        except OSMContextError as error:
            self.failed.emit(str(error))
        except Exception as error:  # defensive boundary around a background task
            self.failed.emit(f"Unexpected OpenStreetMap error: {error}")
        else:
            self.succeeded.emit(context)
        finally:
            self.finished.emit()

