"""Project metadata editor kept separate from export formatting."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout

from pole_route.exporters.excel_exporter import ExcelExportSettings


class ProjectInfoDialog(QDialog):
    def __init__(self, settings: ExcelExportSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project information")
        self.resize(520, 190)
        self.project_title = QLineEdit(settings.project_title)
        self.location = QLineEdit(settings.location)
        self.work_description = QLineEdit(settings.work_description)

        form = QFormLayout()
        form.addRow("Project title", self.project_title)
        form.addRow("Location", self.location)
        form.addRow("Work description", self.work_description)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str]:
        return (
            self.project_title.text().strip(),
            self.location.text().strip(),
            self.work_description.text().strip(),
        )
