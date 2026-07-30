import json
import logging
import numpy as np
import faiss
from openai import OpenAI

from ankiforge.database.models import LLMConfigModel
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class RAGService:
    """
    Service de Recherche Vectorielle (RAG) avec FAISS.
    Permet d'indexer des documents longs et d'y effectuer des recherches sémantiques
    sans dépendre de lourds frameworks comme LangChain.
    """

    def __init__(self, llm_config: LLMConfigModel):
        p_name = str(llm_config.provider).lower()
        base_url = "https://api.openai.com/v1" if p_name == "openai" else "http://localhost:11434/v1"
        api_key_str = str(llm_config.api_key) if llm_config.api_key else "dummy_key"

        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key_str,
        )
        # On peut forcer un modèle d'embedding, Ollama gère nativement `mxbai-embed-large`
        self.embedding_model = "mxbai-embed-large"

        self.faiss_dir = get_app_data_dir() / "faiss_indexes"
        self.faiss_dir.mkdir(parents=True, exist_ok=True)

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
        """
        Découpage natif pur Python (par double sauts de ligne puis par taille).
        Évite d'installer langchain-text-splitters.
        """
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            if len(current_chunk) + len(p) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                # Garder le chevauchement (overlap)
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + " " + p
            else:
                current_chunk += " " + p if current_chunk else p

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _get_embeddings(self, texts: list[str]) -> np.ndarray:
        """Appelle l'API OpenAI / Ollama pour récupérer les vecteurs (embeddings)."""
        response = self.client.embeddings.create(model=self.embedding_model, input=texts)
        embeddings = [data.embedding for data in response.data]
        return np.array(embeddings, dtype=np.float32)

    def create_index(self, doc_id: str, text: str) -> None:
        """
        Découpe un texte, récupère ses embeddings et sauvegarde l'index FAISS
        ainsi que les chunks sur le disque (Persistance).
        """
        chunks = self._chunk_text(text)
        if not chunks:
            logger.warning(f"Aucun texte à indexer pour le document {doc_id}")
            return

        logger.info(f"Création de l'index FAISS pour {doc_id} ({len(chunks)} chunks)...")

        # Batching par 10 pour ne pas surcharger Ollama/OpenAI
        all_embeddings = []
        batch_size = 10
        for i in range(0, len(chunks), batch_size):
            batch_texts = chunks[i : i + batch_size]
            emb = self._get_embeddings(batch_texts)
            all_embeddings.append(emb)

        final_embeddings = np.vstack(all_embeddings)

        # Création de l'index FAISS (L2 distance)
        dimension = final_embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(final_embeddings)

        # Sauvegarde sur disque
        doc_dir = self.faiss_dir / str(doc_id)
        doc_dir.mkdir(parents=True, exist_ok=True)

        faiss.write_index(index, str(doc_dir / "index.faiss"))
        with open(doc_dir / "chunks.json", "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        logger.info(f"Index FAISS sauvegardé pour {doc_id}.")

    def search(self, doc_id: str, query: str, top_k: int = 5) -> list[str]:
        """Recherche dans l'index FAISS d'un document spécifique."""
        doc_dir = self.faiss_dir / str(doc_id)
        index_path = doc_dir / "index.faiss"
        chunks_path = doc_dir / "chunks.json"

        if not index_path.exists() or not chunks_path.exists():
            logger.warning(f"L'index FAISS pour {doc_id} n'existe pas. Impossible de chercher.")
            return []

        # Charger l'index et les chunks
        index = faiss.read_index(str(index_path))
        with open(chunks_path, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        # Embed de la requête
        query_emb = self._get_embeddings([query])

        # Recherche
        distances, indices = index.search(query_emb, top_k)

        results = []
        for i in indices[0]:
            if i != -1 and i < len(chunks):
                results.append(chunks[i])

        return results
