import os
import uuid
import logging
from typing import List

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from ankiforge.database.models import DocumentModel
from ankiforge.config import APP_DIR

logger = logging.getLogger(__name__)

VECTOR_DB_DIR = os.path.join(APP_DIR, "vectors")


class VectorManager:
    """Gère l'indexation et la recherche vectorielle via ChromaDB pour le RAG."""

    def __init__(self):
        os.makedirs(VECTOR_DB_DIR, exist_ok=True)
        # Initialize Persistent Client
        self.client = chromadb.PersistentClient(path=VECTOR_DB_DIR, settings=Settings(anonymized_telemetry=False))

        # Par défaut, ChromaDB utilise all-MiniLM-L6-v2 qui est très rapide et léger
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        """Découpe un long texte en segments (chunks) avec chevauchement."""
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i : i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        return chunks

    def index_document(self, document: DocumentModel) -> str:
        """
        Découpe et indexe un document dans ChromaDB.
        Met à jour le champ chroma_collection_name du DocumentModel.
        """
        collection_name = f"doc_{document.id}_{uuid.uuid4().hex[:8]}"

        collection = self.client.create_collection(name=collection_name, embedding_function=self.embedding_fn)

        logger.info(f"Découpage du document {document.id} en cours...")
        chunks = self.chunk_text(document.content, chunk_size=300, overlap=50)

        ids = [f"chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"document_id": document.id, "chunk_index": i} for i in range(len(chunks))]

        logger.info(f"Ajout de {len(chunks)} chunks dans la collection ChromaDB '{collection_name}'...")
        collection.add(documents=chunks, metadatas=metadatas, ids=ids)

        # Mise à jour de la BDD
        document.chroma_collection_name = collection_name
        document.save()

        logger.info(f"Document {document.id} indexé avec succès.")
        return collection_name

    def search(self, collection_name: str, query: str, n_results: int = 3) -> List[str]:
        """Recherche les chunks les plus pertinents pour une requête donnée."""
        try:
            collection = self.client.get_collection(name=collection_name, embedding_function=self.embedding_fn)
            results = collection.query(query_texts=[query], n_results=n_results)

            if results and results["documents"] and len(results["documents"]) > 0:
                return results["documents"][0]
            return []
        except Exception as e:
            logger.error(f"Erreur de recherche dans ChromaDB: {e}")
            return []
