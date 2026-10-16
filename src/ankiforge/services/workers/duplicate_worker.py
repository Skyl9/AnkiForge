"""Worker QThread de détection des doublons d'un paquet."""

import logging

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.services.cards.duplicate_manager import DuplicateManager

logger = logging.getLogger(__name__)


class DuplicateWorker(QThread):
    """Recherche les doublons d'un paquet en tâche de fond.

    Émet ``finished_processing`` avec la liste des conflits détectés, ou
    ``error_occurred`` si la recherche échoue.
    """

    finished_processing = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, deck_id: int, parent: QObject | None = None):
        super().__init__(parent)
        self.deck_id = deck_id

    def run(self) -> None:
        """Lance la recherche de doublons et publie le résultat sur les signaux du worker."""
        try:
            logger.info("Démarrage de la recherche de doublons pour le paquet ID=%d...", self.deck_id)
            conflicts = DuplicateManager.find_duplicates(self.deck_id)
            logger.info("Recherche de doublons terminée pour le paquet ID=%d : %d conflit(s) détecté(s)", self.deck_id, len(conflicts))
            self.finished_processing.emit(conflicts)
        except Exception as e:
            logger.error("Erreur DuplicateWorker pour le paquet ID=%d : %s", self.deck_id, e, exc_info=True)
            self.error_occurred.emit(str(e))
