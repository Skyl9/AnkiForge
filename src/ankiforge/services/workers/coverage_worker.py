import logging

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.services.reindex_service import REINDEX_EMPTY, REINDEX_OK, reindex_document

logger = logging.getLogger(__name__)


class CoverageWorker(QThread):
    """
    Worker asynchrone pour la structuration documentaire et l'indexation RAG.
    Découpe un document en sections/pages (DocumentChunkModel) et construit son index FAISS.
    Prend en charge le RAG Visuel (VisualRAGService) pour les albums et documents à base de pages.
    Délègue la logique métier à reindex_service.reindex_document (Qt-free et testable).
    """

    progress_update = Signal(str)
    finished_processing = Signal()
    error_occurred = Signal(str)

    def __init__(self, document_id: int, llm_config_id: int | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.document_id = document_id
        self.llm_config_id = llm_config_id

    def run(self) -> None:
        logger.info("CoverageWorker démarré pour le document ID=%d", self.document_id)
        status = reindex_document(
            self.document_id,
            llm_config_id=self.llm_config_id,
            progress_cb=self.progress_update.emit,
        )
        if status == REINDEX_OK:
            self.progress_update.emit("Indexation et structuration terminées avec succès !")
            self.finished_processing.emit()
        elif status == REINDEX_EMPTY:
            self.progress_update.emit("Document vide ou trop court.")
            self.finished_processing.emit()
        else:
            self.error_occurred.emit(f"Document {self.document_id} introuvable ou erreur d'indexation.")
