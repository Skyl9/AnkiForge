import logging
from typing import Any, Dict, List, Optional

from ankiforge.database.models import DocumentModel, LLMConfigModel
from ankiforge.services.rag.vector_manager import VectorManager

logger = logging.getLogger(__name__)


class RAGService:
    """
    Façade de Service RAG (Retrieval-Augmented Generation) pour l'orchestrateur DAG et l'UI.
    Délègue l'indexation matricielle et la recherche sémantique à VectorManager (FAISS).
    """

    def __init__(self, llm_config: Optional[LLMConfigModel] = None):
        self.vector_manager = VectorManager(llm_config=llm_config)

    def create_index(self, doc_id: int | str, text: Optional[str] = None) -> bool:
        """Crée ou met à jour l'index FAISS pour un document."""
        try:
            doc_id_int = int(doc_id)
            doc = DocumentModel.get_or_none(DocumentModel.id == doc_id_int)
            if not doc:
                logger.warning(f"Document {doc_id} introuvable pour la création de l'index RAG.")
                return False
            return self.vector_manager.index_document(doc)
        except Exception as e:
            logger.error(f"Erreur RAGService.create_index : {e}")
            return False

    def search(self, doc_id: int | str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Recherche sémantique dans le document."""
        try:
            return self.vector_manager.search(int(doc_id), query, top_k=top_k)
        except Exception as e:
            logger.error(f"Erreur RAGService.search : {e}")
            return []
