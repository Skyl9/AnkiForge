import json
import logging
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from openai import OpenAI

from ankiforge.database.models import DocumentChunkModel, DocumentModel, LLMConfigModel
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class VectorManager:
    """
    Gestionnaire d'Indexation et de Recherche Vectorielle RAG avec FAISS 100% local.
    S'appuie sur Peewee DocumentChunkModel pour le stockage des métadonnées (titre, page, hash).
    """

    def __init__(self, llm_config: Optional[LLMConfigModel] = None):
        self.llm_config = llm_config
        self.faiss_dir = get_app_data_dir() / "faiss_indexes"
        self.faiss_dir.mkdir(parents=True, exist_ok=True)

        if llm_config:
            p_name = str(llm_config.provider).lower()
            base_url = "https://api.openai.com/v1" if p_name == "openai" else "http://localhost:11434/v1"
            api_key_str = str(llm_config.api_key) if llm_config.api_key else "dummy_key"
            self.client: Optional[OpenAI] = OpenAI(base_url=base_url, api_key=api_key_str)
            self.embedding_model = "mxbai-embed-large" if p_name == "ollama" else "text-embedding-3-small"
        else:
            self.client = None
            self.embedding_model = "mxbai-embed-large"

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Récupère les embeddings pour une liste de textes.
        Si aucun client API n'est configuré (ex: hors ligne ou tests), utilise un fallback déterministe.
        """
        if self.client:
            try:
                response = self.client.embeddings.create(model=self.embedding_model, input=texts)
                embeddings = [data.embedding for data in response.data]
                return np.array(embeddings, dtype=np.float32)
            except Exception as e:
                logger.warning(f"Impossible de contacter l'API d'embeddings ({e}). Repli sur hash vectoriel.")

        # Fallback local pseudo-embedding (vecteur normalisé basé sur hash de fréquence)
        dim = 128
        vectors = []
        for text in texts:
            vec = np.zeros(dim, dtype=np.float32)
            for word in text.lower().split():
                h = hash(word) % dim
                vec[h] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)

    def index_document(self, document: DocumentModel) -> bool:
        """
        Découpe un DocumentModel en DocumentChunkModel (s'ils n'existent pas encore)
        et construit l'index binaire FAISS correspondant.
        """
        try:
            chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == document).order_by(DocumentChunkModel.chunk_index))

            # Si aucun chunk n'existe en base, on utilise ChunkingService
            if not chunks:
                extracted = ChunkingService.extract_chunks(document.content, file_type=document.file_type)
                with DocumentChunkModel._meta.database.atomic():
                    for item in extracted:
                        c = DocumentChunkModel.create(
                            document=document,
                            chunk_index=item["index"],
                            content=item["content"],
                            page_number=item["page_number"],
                            heading_path=item["heading_path"],
                            content_hash=item["content_hash"],
                        )
                        chunks.append(c)

            if not chunks:
                logger.warning(f"Aucun fragment à indexer pour le document {document.id}")
                return False

            chunk_texts = [c.content for c in chunks]
            embeddings = self._get_embeddings(chunk_texts)

            # Création de l'index FAISS (L2 distance)
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(embeddings)

            # Persistance sur le disque
            doc_dir = self.faiss_dir / f"doc_{document.id}"
            doc_dir.mkdir(parents=True, exist_ok=True)

            index_path = doc_dir / "index.faiss"
            faiss.write_index(index, str(index_path))

            # Mapping des chunk_ids dans chunks_map.json
            chunk_ids = [c.id for c in chunks]
            with open(doc_dir / "chunk_ids.json", "w", encoding="utf-8") as f:
                json.dump(chunk_ids, f)

            logger.info(f"Document {document.id} ({len(chunks)} fragments) indexé avec succès dans FAISS.")
            return True
        except Exception as e:
            logger.exception(f"Erreur lors de l'indexation FAISS du document {document.id} : {e}")
            return False

    def search(self, document_id: int, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Recherche sémantique des fragments les plus pertinents pour un document donné.
        Retourne une liste de dictionnaires avec 'chunk_id', 'content', 'heading_path', 'page_number', 'score'.
        """
        doc_dir = self.faiss_dir / f"doc_{document_id}"
        index_path = doc_dir / "index.faiss"
        map_path = doc_dir / "chunk_ids.json"

        if not index_path.exists() or not map_path.exists():
            logger.info(f"Index FAISS inexistant pour le document {document_id}, recherche directe en BDD.")
            # Fallback direct en BDD (recherche par mots-clés)
            terms = [t.lower() for t in query.split() if len(t) > 2]
            query_filter = None
            for t in terms:
                cond = DocumentChunkModel.content.contains(t)
                query_filter = cond if query_filter is None else (query_filter | cond)

            q = DocumentChunkModel.select().where(DocumentChunkModel.document_id == document_id)
            if query_filter is not None:
                q = q.where(query_filter)
            chunks = list(q.limit(top_k))

            return [
                {
                    "chunk_id": c.id,
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "heading_path": c.heading_path,
                    "page_number": c.page_number,
                    "score": 1.0,
                }
                for c in chunks
            ]

        try:
            index = faiss.read_index(str(index_path))
            with open(map_path, "r", encoding="utf-8") as f:
                chunk_ids = json.load(f)

            query_emb = self._get_embeddings([query])
            distances, indices = index.search(query_emb, top_k)

            selected_ids = []
            results = []
            for idx in indices[0]:
                if idx != -1 and idx < len(chunk_ids):
                    selected_ids.append(chunk_ids[idx])

            if selected_ids:
                chunks_by_id = {c.id: c for c in DocumentChunkModel.select().where(DocumentChunkModel.id.in_(selected_ids))}
                for rank, idx in enumerate(indices[0]):
                    if idx != -1 and idx < len(chunk_ids):
                        c_id = chunk_ids[idx]
                        chunk = chunks_by_id.get(c_id)
                        if chunk:
                            results.append(
                                {
                                    "chunk_id": chunk.id,
                                    "chunk_index": chunk.chunk_index,
                                    "content": chunk.content,
                                    "heading_path": chunk.heading_path,
                                    "page_number": chunk.page_number,
                                    "score": float(distances[0][rank]),
                                }
                            )

            return results
        except Exception as e:
            logger.exception(f"Erreur lors de la recherche FAISS pour le document {document_id} : {e}")
            return []
