import logging

from PySide6.QtCore import QThread, Signal

from ankiforge.services.cards.store_manager import StoreManager

logger = logging.getLogger(__name__)


class ImportCardsWorker(QThread):
    """Gère l'importation lourde d'une archive Anki (.apkg) de manière asynchrone."""

    progress = Signal(str)
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(self, store_manager: StoreManager, path: str):
        super().__init__()
        self.store_manager = store_manager
        self.path = path

    def run(self) -> None:
        try:
            self.store_manager.store_collection(self.path, progress_callback=self.progress.emit)
            self.finished_signal.emit()
        except Exception as e:
            logger.exception("Erreur lors de l'importation d'un paquet Anki :")
            self.error_signal.emit(str(e))
