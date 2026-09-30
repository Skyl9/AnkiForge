import logging
import pathlib
import time
from urllib.parse import urlparse

from PySide6.QtCore import QThread, Signal

from ankiforge.services.parsing.document_parser import DocumentParser, is_web_source

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 50


def derive_document_title(source: str) -> str:
    """Déduit le titre d'un document depuis son chemin local ou son URL.

    Point de partage entre le worker unitaire et le worker par lot pour garantir
    qu'une même source produit toujours la même fiche quel que soit le chemin d'import.
    """
    if is_web_source(source):
        parsed_url = urlparse(source)
        # On essaie de prendre le dernier mot de l'URL, sinon le nom de domaine
        raw_title = parsed_url.path.strip("/").split("/")[-1]
        if not raw_title:
            raw_title = parsed_url.netloc
        title = f"Web - {raw_title}"
    else:
        title = pathlib.Path(source).stem
    return title[:MAX_TITLE_LENGTH]


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

    def __init__(self, file_path: str, doc_id_to_update: int | None = None) -> None:
        """
        Initialise le worker d'extraction.

        Args:
            file_path (str): Chemin vers le fichier ou URL de la page web.
            doc_id_to_update (int | None): Identifiant du document existant à mettre à jour.
        """
        super().__init__()
        self.file_path = file_path
        self.doc_id_to_update = doc_id_to_update
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'annulation de l'extraction."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """Vérifie si le worker doit s'arrêter."""
        return self._is_cancelled

    def run(self) -> None:
        """Exécute le parseur approprié et retourne le texte extrait."""
        logger.info("Démarrage de l'analyse documentaire pour : %s", self.file_path)
        t0 = time.perf_counter()
        try:
            parser = DocumentParser()
            title = derive_document_title(self.file_path)
            content = parser.parse_document(self.file_path, progress_callback=self.log_signal.emit, check_cancel=self.is_cancelled)
            if not self._is_cancelled:
                elapsed = time.perf_counter() - t0
                logger.info(
                    "Analyse documentaire terminée avec succès pour '%s' (%d caractères extraits en %.2fs)",
                    title,
                    len(content),
                    elapsed,
                )
                self.finished_signal.emit(title, content)
        except InterruptedError as e:
            logger.info("Analyse annulée par l'utilisateur : %s", e)
            self.log_signal.emit(f"\n {str(e)}")
            self.cancelled_signal.emit()
        except Exception as e:
            logger.exception("Erreur lors de l'analyse du document (%s) : %s", self.file_path, e)
            self.error_signal.emit(str(e))
