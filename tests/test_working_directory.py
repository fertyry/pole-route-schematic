from PySide6.QtCore import QSettings

from pole_route.project.working_directory import WorkingDirectory


def test_working_directory_remembers_selected_file_across_instances(tmp_path) -> None:
    settings_path = tmp_path / "settings.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    directory = tmp_path / "project"
    directory.mkdir()
    selected = directory / "route.kml"

    WorkingDirectory(settings).remember_file(selected)
    settings.sync()
    reloaded = WorkingDirectory(
        QSettings(str(settings_path), QSettings.Format.IniFormat)
    )

    assert reloaded.directory() == directory.resolve()
    assert reloaded.initial_path("drawing.dxf") == str(
        directory.resolve() / "drawing.dxf"
    )


def test_working_directory_ignores_missing_saved_directory(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue(WorkingDirectory.SETTINGS_KEY, str(tmp_path / "missing"))

    assert WorkingDirectory(settings).directory().is_dir()
