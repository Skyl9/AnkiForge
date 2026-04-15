import logging

from PySide6.QtCore import QThread, Signal

from ankiforge.services.cards.store_manager import StoreManager

logger = logging.getLogger(__name__)


class ImportCardsWorker(QThread):
    """
    Worker d'importation massive de cartes (.apkg).

    Permet de charger une collection Anki entière en arrière-plan
    en déléguant le travail au StoreManager.
    """

    progress = Signal(str)
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(self, store_manager: StoreManager, path: str):
        """
        Initialise le worker d'importation.

        Args:
            store_manager (StoreManager): Le gestionnaire d'import.
            path (str): Chemin local vers le fichier (.apkg, .colpkg ou .txt).
        """
        super().__init__()
        self.store_manager = store_manager
        self.path = path

    def run(self) -> None:
        """Lance l'importation asynchrone."""
        try:
            self.store_manager.store_collection(self.path, progress_callback=self.progress.emit)
            self.finished_signal.emit()
        except Exception as e:
            logger.exception("Erreur lors de l'importation d'un paquet Anki :")
            self.error_signal.emit(str(e))
