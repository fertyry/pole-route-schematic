from pole_route.exporters.excel_exporter import ExcelExportSettings
from pole_route.ui.project_info_dialog import ProjectInfoDialog


def test_project_info_dialog_edits_export_header_metadata(qtbot) -> None:
    dialog = ProjectInfoDialog(
        ExcelExportSettings(
            project_title="Original project",
            location="Original location",
            work_description="Original work",
        )
    )
    qtbot.addWidget(dialog)

    dialog.project_title.setText("New project")
    dialog.location.setText("New location")
    dialog.work_description.setText("New work")

    assert dialog.values() == ("New project", "New location", "New work")
