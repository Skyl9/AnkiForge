"""Worker Qt d'import web par lot (analyse uniquement — aucune écriture DB).

Chaque tâche produit un WebImportResult (sérialisé en dict pour les signaux Qt),
les erreurs sont catégorisées pour un affichage utilisateur lisible.
"""

import logging
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.services.parsing.web_importer import (
    WebImportError,
    WebImportRequest,
    result_to_payload,
)

logger = logging.getLogger(__name__)


@dataclass
class UrlImportTask:
    """Tâche d'analyse d'une URL du lot.

    index: position dans la liste du dialogue (pour la ligne du tableau).
    request: paramètres de l'import.
    rendered_html: HTML déjà rendu via JavaScript (repli WebEngine headless).
    base_url: URL finale utilisée pour résoudre les liens relatifs/images.
    """

    index: int
    request: WebImportRequest
    rendered_html: str | None = None
    base_url: str = ""


class UrlImportWorker(QThread):
    """Analyse séquentielle d'un lot d'URLs dans un thread dédié."""

    url_started = Signal(int, str)
    url_finished = Signal(int, dict)
    url_failed = Signal(int, str, str, str)  # index, url, message, catégorie
    log_signal = Signal(str)
    batch_finished = Signal(int, int)  # ok, échecs
    cancelled = Signal()

    def __init__(self, tasks: list[UrlImportTask], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.tasks = list(tasks)
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'annulation entre deux URLs du lot."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """Vérifie si le lot doit s'arrêter."""
        return self._is_cancelled

    def run(self) -> None:
        from ankiforge.services.parsing.web_importer import WebImporter

        importer = WebImporter()
        ok = 0
        failed = 0
        try:
            for task in self.tasks:
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                self.url_started.emit(task.index, task.request.url)
                try:
                    if task.rendered_html is not None:
                        if not task.rendered_html.strip():
                            raise WebImportError("La page n'a rien rendu après exécution du JavaScript.", category="empty")
                        result = importer.analyze_html(
                            task.rendered_html,
                            task.request,
                            base_url=task.base_url or task.request.url,
                            progress_callback=self.log_signal.emit,
                        )
                    else:
                        result = importer.analyze_url(task.request, progress_callback=self.log_signal.emit)
                    ok += 1
                    self.url_finished.emit(task.index, result_to_payload(result))
                except WebImportError as e:
                    failed += 1
                    if self._is_cancelled:
                        self.cancelled.emit()
                        return
                    self.url_failed.emit(task.index, task.request.url, e.message, e.category)
                except InterruptedError as e:
                    logger.info("Import web annulé : %s", e)
                    self.cancelled.emit()
                    return
                except Exception as e:
                    logger.exception("Erreur inattendue lors de l'import web de %s : %s", task.request.url, e)
                    failed += 1
                    self.url_failed.emit(task.index, task.request.url, str(e), "general")
                time.sleep(0.05)
        finally:
            self.batch_finished.emit(ok, failed)
