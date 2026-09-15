import logging
import time

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.database.models import DocumentModel
from ankiforge.services.rag.vector_manager import VectorManager

logger = logging.getLogger(__name__)


class VectorWorker(QThread):
    finished_indexing = Signal(str)  # Renvoie le nom de la collection
    error_occurred = Signal(str)

    def __init__(self, document_id: int, parent: QObject | None = None):
        super().__init__(parent)
        self.document_id = document_id
        self.manager = VectorManager()

    def run(self) -> None:
        t0 = time.perf_counter()
        try:
            document = DocumentModel.get_by_id(self.document_id)
            logger.info("VectorWorker: Démarrage de la vectorisation du document '%s' (ID: %d)", document.title, document.id)
            success = self.manager.index_document(document)
            collection_name = f"doc_{document.id}" if success else ""
            elapsed = time.perf_counter() - t0
            logger.info(
                "VectorWorker: Indexation RAG terminée avec succès pour '%s' (collection: %s) en %.2fs",
                document.title,
                collection_name,
                elapsed,
            )
            self.finished_indexing.emit(collection_name)

        except Exception as e:
            logger.error("Erreur lors de la vectorisation (RAG) du document ID=%d : %s", self.document_id, e, exc_info=True)
            self.error_occurred.emit(str(e))
