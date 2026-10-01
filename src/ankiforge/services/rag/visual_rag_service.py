"""
Service de RAG Visuel (Visual RAG) et d'Indexation Sémantique Dense.
Permet d'indexer et d'interroger directement des albums d'images, planches anatomiques,
schémas complexes et diaporamas sans dépendance lourde locale (approche VLM Dense Indexing).
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import UnidentifiedImageError

from ankiforge.database.base import db
from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    LLMConfigModel,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.ocr_service import OCRService
from ankiforge.services.cards.media_manager import MediaManager

if TYPE_CHECKING:
    from ankiforge.services.rag.vector_manager import VectorManager

logger = logging.getLogger(__name__)

DEFAULT_DENSE_PROMPT = (
    "Tu es un analyste visuel pour un système de recherche documentaire et de mémorisation (Visual RAG). "
    "Analyse minutieusement cette image/page (diagramme, schéma, carte, planche anatomique ou document scanné). "
    "Produis une description sémantique visuelle dense et structurée comprenant :\n"
    "1. **Titre et Sujet Principal** du visuel.\n"
    "2. **Entités et Concepts Visibles** (organes, composants, termes clés).\n"
    "3. **Relations Spatiales et Fonctionnelles** (flèches, flux, légendes, causalités, hiérarchies).\n"
    "4. **Textes et Légendes Explicites** visibles dans l'image.\n"
    "5. **Formules ou Données Numériques** éventuelles.\n\n"
    "Ne donne aucune formule de politesse, uniquement la description analytique dense en Markdown."
)


class VisualRAGService:
    """Service d'orchestration pour l'indexation visuelle dense et la recherche multimodale."""

    def __init__(
        self,
        llm_config: LLMConfigModel | None = None,
        media_manager: MediaManager | None = None,
        ocr_service: OCRService | None = None,
    ) -> None:
        self.llm_config = llm_config
        self.media_manager = media_manager or MediaManager()
        self.ocr_service = ocr_service or OCRService(media_manager=self.media_manager)

    def generate_dense_description(
        self,
        image_path: str | Path,
        provider_override: LLMProvider | None = None,
    ) -> str:
        """
        Génère une description sémantique visuelle dense d'une image/page via VLM.
        Utilise en priorité la catégorie 'visual_rag' configurée par l'utilisateur.
        En cas d'échec ou d'absence d'API, retourne une description minimale basée sur le fichier.
        """
        p = Path(image_path)
        if not p.exists():
            logger.warning("Fichier image introuvable pour Visual RAG : %s", image_path)
            return ""

        try:
            desc = self.ocr_service.transcribe_image(
                image_path=p,
                category_id="visual_rag",
                provider_override=provider_override,
            )
            if desc and desc.strip():
                return desc.strip()
        except Exception as e:
            logger.warning("Échec de l'analyse visuelle VLM pour %s : %s", p.name, e)

        # Repli gracieux hors-ligne
        return f"[Image : {p.name}] - Planche visuelle importée. Configurez une clé d'API Vision pour la description sémantique automatique."

    def _describe_page(self, page: DocumentPageModel, provider_override: LLMProvider | None) -> str:
        """
        Décrit la planche **par la couture** (ADR 0011) : la description dense doit
        décrire la planche telle que l'utilisateur la voit, sinon le fragment indexé
        répond à la mauvaise question tout en paraissant exact.

        La couture rend une image en mémoire ; on la materialise dans un fichier
        éphémère parce que c'est le chemin que parlent déjà les transducteurs.
        """
        from ankiforge.services.ai.ocr_service import save_rendered_page
        from ankiforge.services.cards.album_service import AlbumService

        album_service = AlbumService(media_manager=self.media_manager)
        try:
            rendered = album_service.render_page_image(page)
        except FileNotFoundError:
            logger.warning("Planche %d sans fichier image : description dense ignorée", page.id)
            return ""
        except (UnidentifiedImageError, OSError) as e:
            # Une planche illisible est un défaut d'entrée, pas une raison d'abandonner
            # l'album : les 199 autres planches méritent leur description. `OSError` couvre
            # la bombe de décompression et les E/S directs du volume ; sans lui, une seule
            # planche tronquée interrompait les descriptions de tout l'album.
            logger.warning("Planche %d : fichier image illisible (%s), description dense ignorée", page.id, e)
            return ""

        # Suffixe et contenu viennent de la couture : lire le média brut pour l'extension
        # rouvrait un second chemin de lecture, celui que ADR 0011 a supprimé.
        suffix = album_service.page_media_path(page).suffix or ".png"
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                save_rendered_page(rendered, handle.name, suffix)
                temp_path = Path(handle.name)
            return self.generate_dense_description(temp_path, provider_override=provider_override)
        finally:
            rendered.close()
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def prepare_visual_chunks(
        self,
        document: DocumentModel,
        force_recompute: bool = False,
        provider_override: LLMProvider | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        page_numbers: Sequence[int] | None = None,
    ) -> list[DocumentChunkModel]:
        """
        Génère ou met à jour les DocumentChunkModel pour chaque page d'un album ou document visuel.
        Chaque chunk conserve la référence vers le MediaModel de la page, le numéro de page,
        et la description visuelle dense.

        `page_numbers` restreint le recalcul aux planches visées. Sans lui, la seule option
        après rotation d'une planche serait de réindexer l'album entier ou de la laisser
        définitivement périmée (ADR 0011).
        """
        query = DocumentPageModel.select().where(DocumentPageModel.document == document)
        if page_numbers is not None:
            query = query.where(DocumentPageModel.page_number.in_(list(page_numbers)))
        pages = list(query.order_by(DocumentPageModel.page_number.asc()))
        if not pages:
            logger.warning("Aucune page DocumentPageModel trouvée pour le document ID=%s", document.id)
            return []

        total_pages = DocumentPageModel.select().where(DocumentPageModel.document == document).count()
        chunks: list[DocumentChunkModel] = []
        aggregated_pages_content: list[str] = []

        # Audits "writes-outside-atomic" : les chunks de pages et le contenu agrégé du document sont
        # propagés dans UNE seule transaction (all-or-nothing). En cas d'interruption, on ne laisse
        # jamais un état incohérent (chunks écrits mais document agrégé obsolète, ou l'inverse).
        with db.atomic():
            for idx, page in enumerate(pages):
                page_num = page.page_number
                if progress_callback:
                    progress_callback(idx + 1, total_pages, f"Analyse sémantique de la page {page_num}/{total_pages}...")

                # 1. Vérifier si un chunk existe déjà pour cette page
                existing_chunk = DocumentChunkModel.select().where((DocumentChunkModel.document == document) & (DocumentChunkModel.page_number == page_num)).first()

                # 2. Déterminer si le texte dense doit être généré
                has_dense_content = bool(existing_chunk and existing_chunk.content and len(existing_chunk.content.strip()) > 40)
                chunk_content = ""

                if has_dense_content and not force_recompute and existing_chunk:
                    chunk_content = existing_chunk.content
                    chunk_model = existing_chunk
                else:
                    # La planche est décrite dans son orientation propre, par la couture.
                    dense_desc = self._describe_page(page, provider_override=provider_override)

                    # Combiner avec l'OCR textuel préalable si existant
                    text_parts: list[str] = []
                    if page.ocr_text and page.ocr_text.strip():
                        text_parts.append(f"#### Texte & Transcription :\n{page.ocr_text.strip()}")
                    if dense_desc and dense_desc != page.ocr_text:
                        text_parts.append(f"#### Analyse Visuelle & Schémas :\n{dense_desc}")

                    combined_body = "\n\n".join(text_parts) if text_parts else (dense_desc or f"Page {page_num}")
                    chunk_content = f"<!-- PAGE: {page_num} -->\n### Page {page_num}\n\n{combined_body}\n"

                    content_hash = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()

                    if existing_chunk:
                        existing_chunk.content = chunk_content
                        existing_chunk.content_hash = content_hash
                        existing_chunk.media = page.media
                        existing_chunk.heading_path = f"Page {page_num}"
                        existing_chunk.save()
                        chunk_model = existing_chunk
                    else:
                        chunk_model = DocumentChunkModel.create(
                            document=document,
                            chunk_index=idx,
                            content=chunk_content,
                            content_hash=content_hash,
                            page_number=page_num,
                            heading_path=f"Page {page_num}",
                            media=page.media,
                        )

                    # Met à jour ocr_text de la page si vide
                    if not page.ocr_text or not page.ocr_text.strip():
                        page.ocr_text = dense_desc
                        page.save()

                chunks.append(chunk_model)
                aggregated_pages_content.append(chunk_content)

            # Le contenu agrégé est reconstruit depuis **tous** les fragments persistés, pas
            # seulement ceux de ce passage : un recalcul ciblé ne doit pas tronquer l'album
            # aux planches qu'il vient de rafraîchir. Même règle que l'invalidation de rotation.
            from ankiforge.services.cards.album_service import reaggregate_document_content

            # L'estampillage de version est **avant** la reconstruction, et l'agrégat est la
            # dernière écriture de la transaction. Peewee réécrit toutes les colonnes à
            # chaque `save()` : un `mark_document_version(document)` postérieur, appelé sur
            # l'objet en mémoire — dont `content` est la copie vide d'avant ce passage —
            # écrasait l'agrégat fraîchement calculé. Un album décrit depuis la base se
            # retrouvait donc sans contenu, silencieusement.
            from ankiforge.services.reindex_service import mark_document_version

            document.total_pages = total_pages
            mark_document_version(document)
            reaggregate_document_content(document.id)

        logger.info(
            "VisualRAGService: %d fragments visuels préparés pour le document '%s' (ID %d)",
            len(chunks),
            document.title,
            document.id,
        )
        return chunks

    def index_visual_document(
        self,
        document: DocumentModel,
        vector_manager: VectorManager | None = None,
        force_recompute: bool = False,
        provider_override: LLMProvider | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> bool:
        """
        Indexation complète d'un document visuel/album :
        1. Préparation des chunks avec descriptions denses VLM et liens MediaModel.
        2. Construction des index FAISS (Dense) et BM25 (Sparse) via VectorManager.
        """
        try:
            chunks = self.prepare_visual_chunks(
                document=document,
                force_recompute=force_recompute,
                provider_override=provider_override,
                progress_callback=progress_callback,
            )
            if not chunks:
                logger.warning("VisualRAGService : Aucun chunk visuel à indexer pour doc %d", document.id)
                return False

            from ankiforge.services.rag.vector_manager import VectorManager as VM

            vm = vector_manager or VM(llm_config=self.llm_config)
            # vector_manager.index_document utilisera les chunks déjà créés en base
            return vm.index_document(document)
        except Exception as e:
            logger.error("Erreur VisualRAGService.index_visual_document : %s", e, exc_info=True)
            return False
