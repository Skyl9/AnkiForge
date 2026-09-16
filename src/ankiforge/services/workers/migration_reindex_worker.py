"""Worker QThread de re-indexation migratoire des documents stale.

Après une mise à jour qui change la stratégie de structuration (nouvelle
CHUNKING_VERSION), tous les documents indexés avec une ancienne version sont
re-structurés en arrière-plan au démarrage de l'application.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.database.models import DocumentModel
from ankiforge.services.reindex_service import REINDEX_ERROR, reindex_document

logger = logging.getLogger(__name__)


class MigrationReindexWorker(QThread):
    """Re-indexe séquentiellement tous les documents stale d'un profil AnkiForge."""

    progress = Signal(int, int, str)  # doc_index, total, doc_title
    finished_processing = Signal(int, int)  # processed_count, error_count

    def __init__(self, documents: list[DocumentModel], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.documents = documents
        self._process_docs: list[int] = [doc.id for doc in documents]

    def run(self) -> None:
        total = len(self._process_docs)
        processed = 0
        errors = 0
        for idx, doc_id in enumerate(self._process_docs):
            doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
            if not doc:
                errors += 1
                continue
            self.progress.emit(idx, total, doc.title)
            try:
                status = reindex_document(doc_id)
                if status == REINDEX_ERROR:
                    errors += 1
                else:
                    processed += 1
            except Exception as e:  # pragma: no cover - sécurité worker
                logger.exception("Re-indexation migratoire en échec pour le document %d : %s", doc_id, e)
                errors += 1
            if (idx + 1) % 5 == 0:
                time.sleep(0.05)

        logger.info("Re-indexation migratoire terminée : %d traité(s), %d erreur(s).", processed, errors)
        self.finished_processing.emit(processed, errors)
