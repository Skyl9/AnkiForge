"""Service de RAG Visuel (Visual RAG) et d'Indexation Sémantique Dense.

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
        """Génère une description sémantique visuelle dense d'une image/page via VLM.

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
        """Décrit la planche **par la couture** (ADR 0011).

        La description dense doit décrire la planche telle que l'utilisateur la voit,
        sinon le fragment indexé répond à la mauvaise question tout en paraissant exact.

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
        """Génère ou met à jour les DocumentChunkModel pour chaque page d'un album ou document visuel.

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

        total_pages = len(pages)  # pages déjà en liste : pas de requête .count() redondante
        chunks: list[DocumentChunkModel] = []
        aggregated_pages_content: list[str] = []

        # Requête groupée : précharger tous les chunks existants du document en une seule
        # requête, indexés par numéro de page (élimine le N+1 de la boucle).
        existing_chunks: dict[int, DocumentChunkModel] = {}
        for chunk in DocumentChunkModel.select().where((DocumentChunkModel.document == document) & (DocumentChunkModel.page_number.in_([p.page_number for p in pages]))):
            page_num = chunk.page_number
            if page_num is not None:
                existing_chunks[page_num] = chunk

        # Phase 1 : décrire les planches nécessitant un recalcul HORS transaction SQLite
        # (les appels VLM sont des appels réseau lents qui ne doivent jamais verrouiller
        # la base). Les contenus sont mis en mémoire pour écriture groupée ci-dessous.
        page_descriptions: dict[int, str] = {}
        page_chunk_contents: dict[int, str] = {}
        page_content_hashes: dict[int, str] = {}
        pages_need_ocr_update: dict[int, str] = {}

        for idx, page in enumerate(pages):
            page_num = page.page_number
            if progress_callback:
                progress_callback(idx + 1, total_pages, f"Analyse sémantique de la page {page_num}/{total_pages}...")

            existing_chunk = existing_chunks.get(page_num)
            has_dense_content = bool(existing_chunk and existing_chunk.content and len(existing_chunk.content.strip()) > 40)

            if has_dense_content and not force_recompute and existing_chunk:
                page_chunk_contents[page_num] = existing_chunk.content
                continue

            # Appel VLM hors transaction (pas de verrou BDD prolongé pendant l'appel réseau).
            dense_desc = self._describe_page(page, provider_override=provider_override)

            text_parts: list[str] = []
            if page.ocr_text and page.ocr_text.strip():
                text_parts.append(f"#### Texte & Transcription :\n{page.ocr_text.strip()}")
            if dense_desc and dense_desc != page.ocr_text:
                text_parts.append(f"#### Analyse Visuelle & Schémas :\n{dense_desc}")

            combined_body = "\n\n".join(text_parts) if text_parts else (dense_desc or f"Page {page_num}")
            chunk_content = f"<!-- PAGE: {page_num} -->\n### Page {page_num}\n\n{combined_body}\n"
            content_hash = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()

            page_descriptions[page_num] = dense_desc
            page_chunk_contents[page_num] = chunk_content
            page_content_hashes[page_num] = content_hash
            if not page.ocr_text or not page.ocr_text.strip():
                pages_need_ocr_update[page_num] = dense_desc

        # Phase 2 : toutes les écritures BDD dans une unique transaction (all-or-nothing).
        with db.atomic():
            for idx, page in enumerate(pages):
                page_num = page.page_number
                existing_chunk = existing_chunks.get(page_num)
                chunk_content = page_chunk_contents.get(page_num, "")

                if existing_chunk and page_num not in page_descriptions:
                    # Contenu déjà en cache, pas de réécriture.
                    chunk_model = existing_chunk
                elif existing_chunk:
                    existing_chunk.content = chunk_content
                    existing_chunk.content_hash = page_content_hashes[page_num]
                    existing_chunk.media = page.media
                    existing_chunk.bounding_box = page.crop_data
                    existing_chunk.heading_path = f"Page {page_num}"
                    existing_chunk.save()
                    chunk_model = existing_chunk
                else:
                    chunk_model = DocumentChunkModel.create(
                        document=document,
                        chunk_index=idx,
                        content=chunk_content,
                        content_hash=page_content_hashes[page_num],
                        page_number=page_num,
                        heading_path=f"Page {page_num}",
                        media=page.media,
                        bounding_box=page.crop_data,
                    )

                if page_num in pages_need_ocr_update:
                    page.ocr_text = pages_need_ocr_update[page_num]
                    page.save()

                chunks.append(chunk_model)
                aggregated_pages_content.append(chunk_content)

            from ankiforge.services.cards.album_service import reaggregate_document_content
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
        """Indexation complète d'un document visuel/album.

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
