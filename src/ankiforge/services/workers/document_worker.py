import logging
import pathlib
from urllib.parse import urlparse

from PySide6.QtCore import QThread, Signal

from ankiforge.services.parsing.document_parser import DocumentParser

logger = logging.getLogger(__name__)


class DocumentWorker(QThread):
    """
    Worker d'analyse de document source.

    Gère l'extraction initiale du texte brut d'un document local ou d'une URL
    en utilisant les différents parseurs disponibles.
    """

    finished_signal = Signal(str, str)
    error_signal = Signal(str)
    log_signal = Signal(str)
    cancelled_signal = Signal()

    def __init__(self, file_path: str):
        """
        Initialise le worker d'extraction.

        Args:
            file_path (str): Chemin vers le fichier ou URL de la page web.
        """
        super().__init__()
        self.file_path = file_path
        self._is_cancelled = False

    def cancel(self):
        """Demande l'annulation de l'extraction."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """Vérifie si le worker doit s'arrêter."""
        return self._is_cancelled

    def run(self):
        """Exécute le parseur approprié et retourne le texte extrait."""
        try:
            parser = DocumentParser()
            if self.file_path.startswith("http"):
                parsed_url = urlparse(self.file_path)
                # On essaie de prendre le dernier mot de l'URL, sinon le nom de domaine
                raw_title = parsed_url.path.strip("/").split("/")[-1]
                if not raw_title:
                    raw_title = parsed_url.netloc
                title = f"Web - {raw_title}"
            else:
                title = pathlib.Path(self.file_path).stem
            title = title[:50]
            content = parser.parse_document(self.file_path, progress_callback=self.log_signal.emit, check_cancel=self.is_cancelled)
            if not self._is_cancelled:
                self.finished_signal.emit(title, content)
        except InterruptedError as e:
            logger.info(f"Analyse annulée par l'utilisateur : {str(e)}")
            self.log_signal.emit(f"\n {str(e)}")
            self.cancelled_signal.emit()
        except Exception as e:
            logger.exception("Erreur lors de l'analyse du document :")
            self.error_signal.emit(str(e))
