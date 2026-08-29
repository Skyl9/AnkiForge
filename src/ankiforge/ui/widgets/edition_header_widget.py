import qtawesome
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ankiforge.ui.components.components import ActionButton, HeaderLabel, PrimaryButton


class EditionHeaderWidget(QWidget):
    """
    Header toolbar for the Edition view.
    """

    import_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(HeaderLabel(self.tr("Cards & Notes Navigator")))
        layout.addStretch()

        self.btn_load_col = ActionButton("fa5s.folder-open", self.tr(" Import a deck"))
        self.btn_export = PrimaryButton(qtawesome.icon("fa5s.box", color="white"), self.tr(" Export to Anki"))
        self.btn_export.setEnabled(False)

        layout.addWidget(self.btn_load_col)
        layout.addWidget(self.btn_export)

    def _connect_signals(self) -> None:
        self.btn_load_col.clicked.connect(self.import_requested.emit)
        self.btn_export.clicked.connect(self.export_requested.emit)

    def set_export_enabled(self, enabled: bool) -> None:
        self.btn_export.setEnabled(enabled)

    def set_import_enabled(self, enabled: bool) -> None:
        self.btn_load_col.setEnabled(enabled)
