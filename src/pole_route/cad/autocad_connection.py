"""Explicit, locked connection to an already-running AutoCAD drawing."""

from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Protocol


class AutoCADConnectionError(RuntimeError):
    pass


class AutoCADApplication(Protocol):
    @property
    def Documents(self): ...


@dataclass(frozen=True, slots=True)
class DrawingIdentity:
    full_name: str
    name: str


class AutoCADConnection:
    """Locks to a document path; active-tab changes never retarget it."""

    def __init__(self, application: AutoCADApplication | None = None) -> None:
        self._application = application
        self._target_full_name: str | None = None

    def connect_application(self) -> None:
        if self._application is not None:
            return
        try:
            import win32com.client
            self._application = win32com.client.GetActiveObject("AutoCAD.Application")
        except Exception as error:
            raise AutoCADConnectionError("No running AutoCAD application was found.") from error

    def drawings(self) -> tuple[DrawingIdentity, ...]:
        self.connect_application()
        return tuple(
            DrawingIdentity(str(doc.FullName), str(doc.Name))
            for doc in _documents(self._application)
        )

    def select(self, full_name: str) -> DrawingIdentity:
        document = self._find(full_name)
        self._target_full_name = str(document.FullName)
        return DrawingIdentity(str(document.FullName), str(document.Name))

    def disconnect(self) -> None:
        self._target_full_name = None

    @property
    def connected(self) -> bool:
        if not self._target_full_name:
            return False
        try:
            self._find(self._target_full_name)
        except AutoCADConnectionError:
            self._target_full_name = None
            return False
        return True

    @property
    def target_document(self):
        if not self._target_full_name:
            raise AutoCADConnectionError("No AutoCAD drawing is selected.")
        try:
            return self._find(self._target_full_name)
        except AutoCADConnectionError:
            self._target_full_name = None
            raise AutoCADConnectionError("The selected AutoCAD drawing has been closed.")

    def _find(self, full_name: str):
        self.connect_application()
        wanted = full_name.casefold()
        active = _retry_com_read(
            lambda: getattr(self._application, "ActiveDocument", None)
        )
        if active is not None and str(active.FullName).casefold() == wanted:
            return active
        for document in _documents(self._application):
            if str(document.FullName).casefold() == wanted:
                item = getattr(self._application.Documents, "Item", None)
                if callable(item):
                    name = str(document.Name)
                    return _retry_com_read(
                        lambda item=item, name=name: item(name)
                    )
                return document
        raise AutoCADConnectionError(f"AutoCAD drawing is not open: {full_name}")


def _documents(application, *, attempts: int = 8) -> tuple:
    """Read the document collection through brief AutoCAD busy periods."""

    return _retry_com_read(lambda: tuple(application.Documents), attempts=attempts)


def _retry_com_read(operation, *, attempts: int = 8):
    """Retry an idempotent COM read while AutoCAD briefly rejects calls."""

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            hresult = getattr(error, "hresult", error.args[0] if error.args else None)
            if hresult != -2147418111 or attempt == attempts - 1:
                raise AutoCADConnectionError(
                    "AutoCAD is busy and its drawings cannot be read."
                ) from error
            sleep(0.1 * (attempt + 1))
    raise AssertionError("unreachable")
