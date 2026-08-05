import hashlib
import logging
from typing import Optional
from PySide6.QtCore import QThread, Signal, QObject

from ankiforge.database.models import DocumentModel, DocumentChunkModel, CognitiveFacetModel, ChunkFacetRequirementModel, PersonaModel, LLMConfigModel, db
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.utils import AIReponseParser

logger = logging.getLogger(__name__)


class CoverageWorker(QThread):
    """
    Worker asynchrone pour le "Smart Coverage".
    Découpe un document, hache les paragraphes, et profile les facettes cognitives via l'IA.
    """

    progress_update = Signal(str)
    finished_processing = Signal()
    error_occurred = Signal(str)

    def __init__(self, document_id: int, llm_config_id: Optional[int] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.document_id = document_id
        self.llm_config_id = llm_config_id

    def _hash_content(self, text: str) -> str:
        """Génère un hash MD5 du texte pour éviter le re-calcul."""
        return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

    def run(self):
        try:
            self.progress_update.emit("Initialisation de l'analyse documentaire...")
            doc = DocumentModel.get_by_id(self.document_id)

            # 1. DÉCOUPAGE DU DOCUMENT (Basique par paragraphes pour l'exemple)
            # Dans un cas réel, tu peux utiliser ton `smart_chunk_text` existant
            raw_chunks = [p.strip() for p in doc.content.split("\n\n") if len(p.strip()) > 20]

            if not raw_chunks:
                self.progress_update.emit("Document vide ou trop court.")
                self.finished_processing.emit()
                return

            # 2. SMART CACHING : Hachage et détection du Delta
            chunks_to_profile = []

            with db.atomic():
                for idx, text in enumerate(raw_chunks):
                    content_hash = self._hash_content(text)

                    # Vérifier si ce chunk exact existe déjà en base
                    existing_chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.document == doc, DocumentChunkModel.content_hash == content_hash)

                    if not existing_chunk:
                        # Nouveau chunk ! On l'insère.
                        new_chunk = DocumentChunkModel.create(document=doc, chunk_index=idx, content=text, content_hash=content_hash, is_profiled=False)
                        chunks_to_profile.append({"id": new_chunk.id, "index": idx, "text": text})
                    elif not existing_chunk.is_profiled:
                        # Il existe mais l'IA a planté avant de le profiler la dernière fois
                        chunks_to_profile.append({"id": existing_chunk.id, "index": existing_chunk.chunk_index, "text": existing_chunk.content})

            # S'il n'y a rien de nouveau, on a fini instantanément !
            if not chunks_to_profile:
                self.progress_update.emit("Analyse terminée (100% en cache).")
                self.finished_processing.emit()
                return

            # 3. PRÉPARATION DE L'IA
            persona = PersonaModel.get(PersonaModel.name == "Profileur Cognitif")

            if self.llm_config_id:
                config = LLMConfigModel.get_by_id(self.llm_config_id)
                llm_provider = AIManager.create_provider_from_config(config)
            else:
                llm_provider = AIManager().provider

            # On récupère toutes les facettes valides pour les mapper plus tard
            facets_map = {f.name: f for f in CognitiveFacetModel.select()}

            # 4. APPEL IA PAR LOTS (Pour la sécurité de la structure JSON)
            batch_size = 20
            total_batches = (len(chunks_to_profile) + batch_size - 1) // batch_size

            for i in range(0, len(chunks_to_profile), batch_size):
                batch = chunks_to_profile[i : i + batch_size]
                current_batch = (i // batch_size) + 1

                self.progress_update.emit(f"Profilage cognitif en cours (Lot {current_batch}/{total_batches})...")

                # Formatage du prompt utilisateur (Index + Texte)
                user_content = "Voici les fragments à analyser :\n"
                for item in batch:
                    user_content += f"--- FRAGMENT {item['index']} ---\n{item['text']}\n\n"

                # Libération de SQLite avant l'appel réseau
                if not db.is_closed():
                    db.close()

                raw_response = llm_provider.generate(system_prompt=persona.system_prompt, user_prompt=user_content, response_format="json")

                db.connect(reuse_if_open=True)

                # 5. PARSING ET SAUVEGARDE (Avec Sécurité Transactionnelle)
                try:
                    results = AIReponseParser.parse(raw_response)
                    if not isinstance(results, list):
                        raise ValueError("L'IA n'a pas renvoyé une liste JSON.")

                    with db.atomic():
                        for res in results:
                            c_idx = res.get("chunk_index")
                            req_facets = res.get("facets", [])

                            # Retrouver le chunk correspondant en base
                            db_chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.document == doc, DocumentChunkModel.chunk_index == c_idx)

                            if db_chunk:
                                # Insérer les relations Facette <-> Chunk
                                for f_name in req_facets:
                                    if f_name in facets_map:
                                        ChunkFacetRequirementModel.get_or_create(chunk=db_chunk, facet=facets_map[f_name])
                                # Marquer comme profilé
                                db_chunk.is_profiled = True
                                db_chunk.save()

                except Exception as e:
                    logger.error(f"Erreur de parsing sur le lot {current_batch} du CoverageWorker: {e}", exc_info=True)

            self.progress_update.emit("Profilage terminé avec succès !")
            self.finished_processing.emit()

        except Exception as e:
            logger.error(f"Erreur fatale dans le CoverageWorker: {e}", exc_info=True)
            if db.is_closed():
                db.connect(reuse_if_open=True)
            self.error_occurred.emit(str(e))
