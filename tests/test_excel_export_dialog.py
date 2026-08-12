from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from pole_route.ui.excel_export_dialog import ExcelExportDialog


def test_export_dialog_previews_paper_and_updates_settings(qtbot) -> None:
    source = QGraphicsScene()
    source_line = QGraphicsLineItem(0, 0, 100, 0)
    source.addItem(source_line)
    dialog = ExcelExportDialog(source)
    qtbot.addWidget(dialog)

    dialog.project_title.setText("My Project")
    dialog.paper_size.setCurrentText("A3")
    dialog.orientation.setCurrentText("Portrait")

    settings = dialog.settings()
    assert settings.project_title == "My Project"
    assert settings.paper_size == "A3"
    assert settings.orientation == "portrait"
    assert dialog.preview_scene.items()
    assert source_line.scene() is source


def test_repeated_preview_changes_keep_objects_and_source_scene(qtbot) -> None:
    source = QGraphicsScene()
    source_line = QGraphicsLineItem(0, 0, 300, 40)
    source.addItem(source_line)
    dialog = ExcelExportDialog(source)
    qtbot.addWidget(dialog)

    for index in range(20):
        dialog.project_title.setText(f"Project {index}")
        dialog.paper_size.setCurrentText("A3" if index % 2 else "A4")
        dialog.orientation.setCurrentText("Portrait" if index % 2 else "Landscape")
        assert dialog.preview_scene.items()
        assert dialog.preview.scene() is dialog.preview_scene
        assert source_line.scene() is source
