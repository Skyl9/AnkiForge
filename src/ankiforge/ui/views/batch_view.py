import logging
from PySide6.QtCore import QSettings, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

from ankiforge.ui.views.batch_cicd_view import BatchCicdView
from ankiforge.ui.views.batch_kanban_view import BatchKanbanView
from ankiforge.ui.views.batch_wizard_view import BatchWizardView

logger = logging.getLogger(__name__)


class BatchTab(QWidget):
    """
    Conteneur qui switch entre les 3 variantes de Batch Factory
    selon les paramètres de l'application.
    """

    def __init__(self, ai_manager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # Initialisation des 3 sous-vues
        self._cicd = BatchCicdView(self.ai_manager)
        self._kanban = BatchKanbanView(self.ai_manager)
        self._wizard = BatchWizardView(self.ai_manager)

        self.stack.addWidget(self._cicd)
        self.stack.addWidget(self._kanban)
        self.stack.addWidget(self._wizard)

        self._load_style()

    def _load_style(self) -> None:
        """Lit le style depuis QSettings et affiche la bonne vue."""
        settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")
        style = settings.value("batch_factory_style", "cicd")

        if style == "kanban":
            self.stack.setCurrentWidget(self._kanban)
        elif style == "wizard":
            self.stack.setCurrentWidget(self._wizard)
        else:
            self.stack.setCurrentWidget(self._cicd)

    @Slot()
    def refresh_data(self) -> None:
        """Appelle refresh_data sur toutes les sous-vues."""
        self._cicd.refresh_data()
        self._kanban.refresh_data()
        self._wizard.refresh_data()
