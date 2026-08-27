from PySide6.QtCore import QObject, Signal, QRunnable
from typing import Optional, TYPE_CHECKING
from ankiforge.services.parsing.youtube_parser import YouTubeParser

if TYPE_CHECKING:
    from ankiforge.services.ai.flexible_service import AIManager


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

    def run(self):
        try:
            content = self.parser.parse(self.url, self.ai_manager)
            if content:
                self.signals.finished.emit(content)
            else:
                self.signals.error.emit("Impossible d'extraire le contenu de la vidéo.")
        except Exception as e:
            self.signals.error.emit(f"Erreur d'extraction: {str(e)}")
