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
