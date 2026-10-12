"""Worker QThread de re-indexation migratoire des documents stale.

Après une mise à jour qui change la stratégie de structuration (nouvelle
CHUNKING_VERSION), tous les documents indexés avec une ancienne version sont
re-structurés en arrière-plan au démarrage de l'application.

Le worker publie sa macro-progression (document courant / total) sur ses propres
signaux **et** sur le hub :class:`ReindexActivityService`, qui alimente le bandeau
d'activité global (ADR 0021). L'annulation est coopérative : elle n'intervient
qu'entre deux documents, jamais au milieu d'un document.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.database.models import DocumentModel
from ankiforge.services.reindex_activity_service import ReindexActivityService
from ankiforge.services.reindex_service import REINDEX_ERROR, reindex_document

logger = logging.getLogger(__name__)


class MigrationReindexWorker(QThread):
    """Re-indexe séquentiellement tous les documents stale d'un profil AnkiForge."""

    progress = Signal(int, int, str)  # document_number (1-based), total, doc_title
    finished_processing = Signal(int, int, int)  # documents, fragments, errors

    def __init__(
        self,
        documents: list[DocumentModel],
        activity: ReindexActivityService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.documents = documents
        self._process_docs: list[int] = [doc.id for doc in documents]
        self._activity = activity if activity is not None else ReindexActivityService.get_instance()
        self._current_doc_fragments = 0

    def _on_fragment(self, processed: int, total: int) -> None:
        """Micro-progression opportuniste du document courant (jamais bloquante)."""
        self._current_doc_fragments = total
        self._activity.report_fragments(processed, total)

    def run(self) -> None:
        total = len(self._process_docs)
        processed = 0
        fragments = 0
        errors = 0
        try:
            for idx, doc_id in enumerate(self._process_docs):
                if self._activity.is_cancel_requested():
                    logger.info(
                        "Re-indexation migratoire annulée après %d/%d document(s) : les suivants restent stale.",
                        idx,
                        total,
                    )
                    break
                doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
                if not doc:
                    errors += 1
                    continue

                self.progress.emit(idx + 1, total, doc.title)
                self._activity.report_document(idx + 1, total, doc.title)

                self._current_doc_fragments = 0
                try:
                    status = reindex_document(doc_id, fragment_cb=self._on_fragment)
                    if status == REINDEX_ERROR:
                        errors += 1
                    else:
                        processed += 1
                        fragments += self._current_doc_fragments
                except Exception as e:  # pragma: no cover - sécurité worker
                    logger.exception("Re-indexation migratoire en échec pour le document %d : %s", doc_id, e)
                    errors += 1
                if (idx + 1) % 5 == 0:
                    time.sleep(0.05)
        finally:
            logger.info(
                "Re-indexation migratoire terminée : %d traité(s), %d fragment(s), %d erreur(s).",
                processed,
                fragments,
                errors,
            )
            self._activity.finish(processed, fragments, errors)
            self.finished_processing.emit(processed, fragments, errors)
