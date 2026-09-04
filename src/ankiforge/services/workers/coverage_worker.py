import hashlib
import logging
import time

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    LLMConfigModel,
    db,
)
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.rag.vector_manager import VectorManager
from ankiforge.services.rag.visual_rag_service import VisualRAGService

logger = logging.getLogger(__name__)


class CoverageWorker(QThread):
    """
    Worker asynchrone pour la structuration documentaire et l'indexation RAG.
    Découpe un document en sections/pages (DocumentChunkModel) et construit son index FAISS.
    Prend en charge le RAG Visuel (VisualRAGService) pour les albums et documents à base de pages.
    """

    progress_update = Signal(str)
    finished_processing = Signal()
    error_occurred = Signal(str)

    def __init__(self, document_id: int, llm_config_id: int | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.document_id = document_id
        self.llm_config_id = llm_config_id

    def _hash_content(self, text: str) -> str:
        """Génère un hash MD5 du texte."""
        return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

    def run(self) -> None:
        logger.info("CoverageWorker démarré pour le document ID=%d", self.document_id)
        t0 = time.perf_counter()
        try:
            self.progress_update.emit("Initialisation de la structuration documentaire...")
            doc = DocumentModel.get_or_none(DocumentModel.id == self.document_id)
            if not doc:
                logger.error("CoverageWorker : Document ID=%d introuvable en base.", self.document_id)
                self.error_occurred.emit(f"Document {self.document_id} introuvable.")
                return

            # 1. CAS VISUEL : Album d'images ou Document avec pages DocumentPageModel
            has_pages = DocumentPageModel.select().where(DocumentPageModel.document == doc).exists()
            if doc.file_type == "album" or has_pages:
                self.progress_update.emit("Indexation RAG Visuel des planches / pages de l'album...")
                cfg = LLMConfigModel.get_or_none(LLMConfigModel.id == self.llm_config_id) if self.llm_config_id else None
                vector_mgr = VectorManager(llm_config=cfg)
                visual_rag = VisualRAGService(llm_config=cfg)

                def _on_visual_progress(cur: int, tot: int, msg: str) -> None:
                    self.progress_update.emit(f"[{cur}/{tot}] {msg}")

                success = visual_rag.index_visual_document(
                    doc,
                    vector_manager=vector_mgr,
                    progress_callback=_on_visual_progress,
                )
                if not success:
                    self.error_occurred.emit("Échec de l'indexation RAG Visuel.")
                    return

                elapsed = time.perf_counter() - t0
                logger.info(
                    "CoverageWorker terminé avec succès pour l'album '%s' (Visual RAG) en %.2fs",
                    doc.title,
                    elapsed,
                )
                self.progress_update.emit("Indexation RAG Visuel terminée avec succès !")
                self.finished_processing.emit()
                return

            # 2. CAS TEXTUEL : DÉCOUPAGE DU DOCUMENT via ChunkingService
            extracted_chunks = ChunkingService.extract_chunks(doc.content, file_type=doc.file_type)
            if not extracted_chunks:
                logger.warning("Document '%s' vide ou trop court pour générer des chunks.", doc.title)
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
            logger.info("Persistance de %d chunks en BDD pour le document '%s'", len(extracted_chunks), doc.title)

            # 3. Construction de l'index vectoriel FAISS local
            self.progress_update.emit("Génération de l'index vectoriel FAISS...")
            cfg = LLMConfigModel.get_or_none(LLMConfigModel.id == self.llm_config_id) if self.llm_config_id else None
            vector_mgr = VectorManager(llm_config=cfg)
            vector_mgr.index_document(doc)

            elapsed = time.perf_counter() - t0
            logger.info(
                "CoverageWorker terminé avec succès pour '%s' (%d chunks, indexation FAISS) en %.2fs",
                doc.title,
                len(extracted_chunks),
                elapsed,
            )
            self.progress_update.emit("Indexation et structuration terminées avec succès !")
            self.finished_processing.emit()

        except Exception as e:
            logger.exception("Erreur dans le CoverageWorker pour document ID=%d : %s", self.document_id, e)
            self.error_occurred.emit(str(e))
