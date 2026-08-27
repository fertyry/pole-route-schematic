"""Explicit, locked connection to an already-running AutoCAD drawing."""

from __future__ import annotations

from dataclasses import dataclass
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
            for doc in self._application.Documents
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
        for document in self._application.Documents:
            if str(document.FullName).casefold() == wanted:
                return document
        raise AutoCADConnectionError(f"AutoCAD drawing is not open: {full_name}")

