import logging
from typing import Optional

from PySide6.QtCore import QThread, Signal, QObject

from ankiforge.database.models import DocumentModel
from ankiforge.services.rag.vector_manager import VectorManager

logger = logging.getLogger(__name__)


class VectorWorker(QThread):
    finished_indexing = Signal(str)  # Renvoie le nom de la collection
    error_occurred = Signal(str)

    def __init__(self, document_id: int, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.document_id = document_id
        self.manager = VectorManager()

    def run(self):
        try:
            document = DocumentModel.get_by_id(self.document_id)
            logger.info(f"VectorWorker: Démarrage de la vectorisation du document {document.title}")
            collection_name = self.manager.index_document(document)
            self.finished_indexing.emit(collection_name)
        except Exception as e:
            logger.error(f"Erreur lors de la vectorisation (RAG) : {e}", exc_info=True)
            self.error_occurred.emit(str(e))
