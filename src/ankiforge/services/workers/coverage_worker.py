import logging

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.database.models import DocumentModel
from ankiforge.services.reindex_activity_service import ReindexActivityService
from ankiforge.services.reindex_service import REINDEX_EMPTY, REINDEX_OK, reindex_document

logger = logging.getLogger(__name__)


class CoverageWorker(QThread):
    """
    Worker asynchrone pour la structuration documentaire et l'indexation RAG.
    Découpe un document en sections/pages (DocumentChunkModel) et construit son index FAISS.
    Prend en charge le RAG Visuel (VisualRAGService) pour les albums et documents à base de pages.
    Délègue la logique métier à reindex_service.reindex_document (Qt-free et testable).

    La passe d'un seul document est déclarée sur le hub ReindexActivityService (ADR 0021) :
    le worker publie le document courant et sa micro-progression en fragments, puis clôt la
    passe dans un ``finally`` — une exception ne doit jamais laisser le bandeau actif pour
    toujours.
    """

    progress_update = Signal(str)
    finished_processing = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        document_id: int,
        llm_config_id: int | None = None,
        activity: ReindexActivityService | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.document_id = document_id
        self.llm_config_id = llm_config_id
        self._activity = activity if activity is not None else ReindexActivityService.get_instance()

    def run(self) -> None:
        logger.info("CoverageWorker démarré pour le document ID=%d", self.document_id)
        documents = 0
        fragments = 0
        errors = 0
        try:
            doc = DocumentModel.get_or_none(DocumentModel.id == self.document_id)
            self._activity.report_document(1, 1, doc.title if doc else "")

            doc_fragments: list[int] = [0]

            def _on_fragment(processed_fragments: int, total_fragments: int) -> None:
                doc_fragments[0] = total_fragments
                self._activity.report_fragments(processed_fragments, total_fragments)

            status = reindex_document(
                self.document_id,
                llm_config_id=self.llm_config_id,
                progress_cb=self.progress_update.emit,
                fragment_cb=_on_fragment,
            )
            if status == REINDEX_OK:
                documents = 1
                fragments = doc_fragments[0]
                self.progress_update.emit("Indexation et structuration terminées avec succès !")
                self.finished_processing.emit()
            elif status == REINDEX_EMPTY:
                documents = 1
                self.progress_update.emit("Document vide ou trop court.")
                self.finished_processing.emit()
            else:
                errors = 1
                self.error_occurred.emit(f"Document {self.document_id} introuvable ou erreur d'indexation.")
        except Exception:  # pragma: no cover - sécurité worker
            errors = 1
            raise
        finally:
            self._activity.finish(documents, fragments, errors)
