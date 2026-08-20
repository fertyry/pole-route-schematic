"""Application-local working-directory preference for file dialogs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


class WorkingDirectory:
    """Keep file dialogs together without storing machine paths in project files."""

    SETTINGS_KEY = "paths/working_directory"

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings()

    def directory(self) -> Path:
        stored = self._settings.value(self.SETTINGS_KEY, "", type=str)
        if stored:
            candidate = Path(stored)
            if candidate.is_dir():
                return candidate
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        return Path(documents) if documents else Path.cwd()

    def initial_path(self, suggested_name: str = "") -> str:
        directory = self.directory()
        return str(directory / suggested_name) if suggested_name else str(directory)

    def remember_file(self, path: str | Path) -> None:
        selected = Path(path)
        directory = selected if selected.is_dir() else selected.parent
        if directory.is_dir():
            self._settings.setValue(self.SETTINGS_KEY, str(directory.resolve()))

