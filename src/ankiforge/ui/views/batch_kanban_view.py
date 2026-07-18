import logging
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QTreeWidget, QAbstractItemView, QFrame

from ankiforge.ui.components.components import RoundedPanel

logger = logging.getLogger(__name__)


class KanbanColumn(RoundedPanel):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(10, 10, 10, 10)

        lbl = QLabel(title)
        lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_main.addWidget(lbl)
        self.layout_main.addSpacing(5)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        self.tree.viewport().setAutoFillBackground(False)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        self.layout_main.addWidget(self.tree)


class BatchKanbanView(QWidget):
    """
    Card Factory View (Batch Processing) - Kanban Variant.
    Allows visualizing batch jobs in a kanban board format.
    """

    def __init__(self, ai_manager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        header = QLabel(self.tr("Kanban Batch Factory"))
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: palette(text);")
        self.main_layout.addWidget(header)

        self.kanban_layout = QHBoxLayout()
        self.kanban_layout.setSpacing(15)

        self.col_todo = KanbanColumn(self.tr("À traiter"))
        self.col_progress = KanbanColumn(self.tr("En Cours (IA)"))
        self.col_validation = KanbanColumn(self.tr("Validation Requise"))
        self.col_done = KanbanColumn(self.tr("Terminé (Prêt Anki)"))

        self.kanban_layout.addWidget(self.col_todo)
        self.kanban_layout.addWidget(self.col_progress)
        self.kanban_layout.addWidget(self.col_validation)
        self.kanban_layout.addWidget(self.col_done)

        self.main_layout.addLayout(self.kanban_layout)

    @Slot()
    def refresh_data(self) -> None:
        # Stub for now
        pass
