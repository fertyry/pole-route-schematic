from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from pole_route.exporters.excel_exporter import ExcelExportSettings, collect_scene_objects
from pole_route.ui.excel_export_dialog import ExcelExportDialog


def test_export_dialog_previews_paper_and_updates_settings(qtbot) -> None:
    source = QGraphicsScene()
    source_line = QGraphicsLineItem(0, 0, 100, 0)
    source.addItem(source_line)
    dialog = ExcelExportDialog(collect_scene_objects(source))
    qtbot.addWidget(dialog)

    dialog.project_title.setText("My Project")
    dialog.work_description.setText("144 poles and New Cable Tray 1 Set")
    dialog.paper_size.setCurrentText("A3")
    dialog.orientation.setCurrentText("Portrait")

    settings = dialog.settings()
    assert settings.project_title == "My Project"
    assert settings.work_description == "144 poles and New Cable Tray 1 Set"
    assert settings.paper_size == "A3"
    assert settings.orientation == "portrait"
    assert dialog.preview_scene.items()
    assert source_line.scene() is source


def test_export_dialog_restores_saved_project_metadata(qtbot) -> None:
    source = QGraphicsScene()
    source.addLine(0, 0, 100, 0)
    saved = ExcelExportSettings(
        project_title="Saved project",
        location="Saved route",
        work_description="Saved work details",
        paper_size="A3",
        page_count=7,
    )

    dialog = ExcelExportDialog(
        collect_scene_objects(source), initial_settings=saved
    )
    qtbot.addWidget(dialog)

    assert dialog.project_title.text() == "Saved project"
    assert dialog.location.text() == "Saved route"
    assert dialog.work_description.text() == "Saved work details"
    assert dialog.paper_size.currentText() == "A3"
    assert dialog.page_count.value() == 7


def test_repeated_preview_changes_keep_objects_and_source_scene(qtbot) -> None:
    source = QGraphicsScene()
    source_line = QGraphicsLineItem(0, 0, 300, 40)
    source.addItem(source_line)
    dialog = ExcelExportDialog(collect_scene_objects(source))
    qtbot.addWidget(dialog)
    preview_scene = dialog.preview_scene

    for index in range(20):
        dialog.project_title.setText(f"Project {index}")
        dialog.paper_size.setCurrentText("A3" if index % 2 else "A4")
        dialog.orientation.setCurrentText("Portrait" if index % 2 else "Landscape")
        assert dialog.preview_scene.items()
        assert dialog.preview_scene is preview_scene
        assert dialog.preview.scene() is dialog.preview_scene
        assert source_line.scene() is source

    qtbot.wait(150)
    assert dialog.preview_scene is preview_scene


def test_confirmed_export_uses_snapshot_even_if_source_scene_later_changes(qtbot) -> None:
    source = QGraphicsScene()
    source_line = QGraphicsLineItem(0, 0, 300, 40)
    source.addItem(source_line)
    dialog = ExcelExportDialog(collect_scene_objects(source))
    qtbot.addWidget(dialog)
    expected_count = len(dialog.export_objects())

    source.clear()

    assert expected_count > 0
    assert len(dialog.export_objects()) == expected_count
    assert dialog.preview_scene.items()


def test_dialog_destruction_cannot_modify_source_scene(qtbot) -> None:
    source = QGraphicsScene()
    source_line = QGraphicsLineItem(0, 0, 300, 40)
    source.addItem(source_line)
    snapshot = collect_scene_objects(source)
    dialog = ExcelExportDialog(snapshot)
    qtbot.addWidget(dialog)
    dialog.project_title.setText("Changed in review")
    dialog.accept()
    dialog.deleteLater()
    qtbot.wait(10)

    assert source_line.scene() is source
    assert source.items() == [source_line]
    assert snapshot


def test_dialog_reviews_each_requested_sheet(qtbot) -> None:
    source = QGraphicsScene()
    source.addLine(0, 0, 1000, 100)
    dialog = ExcelExportDialog(collect_scene_objects(source))
    qtbot.addWidget(dialog)

    dialog.page_count.setValue(3)

    assert len(dialog.export_pages()) == 3
    assert dialog.page_label.text() == "Sheet 1 / 3"
    qtbot.mouseClick(dialog.next_page, Qt.MouseButton.LeftButton)
    assert dialog.page_label.text() == "Sheet 2 / 3"
