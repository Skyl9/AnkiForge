from typing import Optional
import logging

from PySide6.QtCore import QThread, Signal, QObject

from ankiforge.services.cards.duplicate_manager import DuplicateManager

logger = logging.getLogger(__name__)


class DuplicateWorker(QThread):
    finished_processing = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, deck_id: int, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.deck_id = deck_id

    def run(self):
        try:
            logger.info(f"Démarrage de la recherche de doublons pour le paquet {self.deck_id}...")
            conflicts = DuplicateManager.find_duplicates(self.deck_id)
            self.finished_processing.emit(conflicts)
        except Exception as e:
            logger.error(f"Erreur DuplicateWorker: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
