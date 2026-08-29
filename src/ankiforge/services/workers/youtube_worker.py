import logging
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from ankiforge.services.parsing.youtube_parser import YouTubeParser

if TYPE_CHECKING:
    from ankiforge.services.ai.flexible_service import AIManager

logger = logging.getLogger(__name__)


class YouTubeWorkerSignals(QObject):
    """Signaux pour le worker YouTube."""

    finished = Signal(str)  # Contenu extrait
    error = Signal(str)


class YouTubeWorker(QRunnable):
    """Worker pour extraire le texte d'une vidéo YouTube en asynchrone."""

    def __init__(self, url: str, ai_manager: Optional["AIManager"] = None):
        super().__init__()
        self.url = url
        self.ai_manager = ai_manager
        self.signals = YouTubeWorkerSignals()
        self.parser = YouTubeParser()

    def run(self) -> None:
        logger.info("Démarrage de l'extraction YouTube pour : %s", self.url)
        try:
            content = self.parser.parse(self.url, self.ai_manager)
            if content:
                logger.info("Extraction YouTube réussie pour %s (%d caractères extraits)", self.url, len(content))
                self.signals.finished.emit(content)
            else:
                logger.warning("Impossible d'extraire le contenu de la vidéo YouTube : %s", self.url)
                self.signals.error.emit("Impossible d'extraire le contenu de la vidéo.")
        except Exception as e:
            logger.error("Erreur lors de l'extraction YouTube (%s) : %s", self.url, e, exc_info=True)
            self.signals.error.emit(f"Erreur d'extraction: {str(e)}")
