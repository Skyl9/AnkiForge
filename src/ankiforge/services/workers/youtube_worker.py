import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, Signal

from ankiforge.services.parsing.youtube_parser import YouTubeParser

if TYPE_CHECKING:
    from ankiforge.services.ai.flexible_service import AIManager

logger = logging.getLogger(__name__)


class YouTubeWorkerSignals(QObject):
    """Signaux pour le worker YouTube."""

    finished = Signal(str)  # Contenu extrait
    error = Signal(str)
    progress = Signal(str)  # Avancement textuel du traitement
    cancelled = Signal()  # Notification d'annulation par l'utilisateur


class YouTubeWorker(QRunnable):
    """Worker pour extraire le texte d'une vidéo YouTube en asynchrone."""

    def __init__(self, url: str, ai_manager: "AIManager | None" = None):
        super().__init__()
        self.url = url
        self.ai_manager = ai_manager
        self.signals = YouTubeWorkerSignals()
        self.parser = YouTubeParser()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'interruption immédiate de l'extraction YouTube."""
        logger.info("Demande d'annulation reçue pour l'extraction YouTube : %s", self.url)
        self._is_cancelled = True

    def check_cancel(self) -> bool:
        """Indique si l'annulation a été demandée."""
        return self._is_cancelled

    def run(self) -> None:
        logger.info("Démarrage de l'extraction YouTube pour : %s", self.url)
        try:
            if self.check_cancel():
                self.signals.cancelled.emit()
                return

            content = self.parser.parse(
                self.url,
                self.ai_manager,
                progress_callback=self.signals.progress.emit,
                check_cancel=self.check_cancel,
            )

            if self.check_cancel():
                logger.info("Extraction YouTube interrompue pour %s.", self.url)
                self.signals.cancelled.emit()
                return

            if content:
                logger.info("Extraction YouTube réussie pour %s (%d caractères extraits)", self.url, len(content))
                self.signals.finished.emit(content)
            else:
                logger.warning("Impossible d'extraire le contenu de la vidéo YouTube : %s", self.url)
                self.signals.error.emit("Impossible d'extraire le contenu de la vidéo.")
        except Exception as e:
            if self.check_cancel():
                logger.info("Extraction YouTube interrompue suite à exception d'annulation pour %s.", self.url)
                self.signals.cancelled.emit()
                return
            logger.error("Erreur lors de l'extraction YouTube (%s) : %s", self.url, e, exc_info=True)
            self.signals.error.emit(f"Erreur d'extraction: {str(e)}")
