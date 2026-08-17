import hashlib
import logging
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.database.models import DocumentChunkModel, DocumentModel, LLMConfigModel, db
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.rag.vector_manager import VectorManager

logger = logging.getLogger(__name__)


class CoverageWorker(QThread):
    """
    Worker asynchrone pour la structuration documentaire et l'indexation RAG.
    Découpe un document en sections/pages (DocumentChunkModel) et construit son index FAISS.
    """

    progress_update = Signal(str)
    finished_processing = Signal()
    error_occurred = Signal(str)

    def __init__(self, document_id: int, llm_config_id: Optional[int] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.document_id = document_id
        self.llm_config_id = llm_config_id

    def _hash_content(self, text: str) -> str:
        """Génère un hash MD5 du texte."""
        return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

    def run(self) -> None:
        try:
            self.progress_update.emit("Initialisation de la structuration documentaire...")
            doc = DocumentModel.get_or_none(DocumentModel.id == self.document_id)
            if not doc:
                self.error_occurred.emit(f"Document {self.document_id} introuvable.")
                return

            # 1. DÉCOUPAGE DU DOCUMENT via ChunkingService
            extracted_chunks = ChunkingService.extract_chunks(doc.content)
            if not extracted_chunks:
                self.progress_update.emit("Document vide ou trop court.")
                self.finished_processing.emit()
                return

            self.progress_update.emit(f"Traitement de {len(extracted_chunks)} sections/paragraphes...")

            # 2. Persistance atomique des Chunks en base SQLite
            with db.atomic():
                # On met à jour les chunks existants ou on recrée
                DocumentChunkModel.delete().where(DocumentChunkModel.document == doc).execute()
                for chunk_data in extracted_chunks:
                    DocumentChunkModel.create(
                        document=doc,
                        chunk_index=chunk_data["index"],
                        content=chunk_data["content"],
                        page_number=chunk_data["page_number"],
                        heading_path=chunk_data["heading_path"],
                        content_hash=chunk_data["content_hash"],
                    )

            # 3. Construction de l'index vectoriel FAISS local
            self.progress_update.emit("Génération de l'index vectoriel FAISS...")
            cfg = LLMConfigModel.get_or_none(LLMConfigModel.id == self.llm_config_id) if self.llm_config_id else None
            vector_mgr = VectorManager(llm_config=cfg)
            vector_mgr.index_document(doc)

            self.progress_update.emit("Indexation et structuration terminées avec succès !")
            self.finished_processing.emit()

        except Exception as e:
            logger.exception("Erreur dans le CoverageWorker :")
            self.error_occurred.emit(str(e))
