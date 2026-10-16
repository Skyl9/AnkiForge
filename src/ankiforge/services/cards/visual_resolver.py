"""Résolution déterministe des médias visuels associés à un fragment pour la charge utile RAG.

Sélectionne, encode et ordonne les images conformes transmises aux modèles de vision,
dans la limite de capacité du fournisseur (ADR 0018).
"""

from __future__ import annotations

import base64
import io
import logging
import mimetypes
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
)
from ankiforge.services.cards.album_service import AlbumService
from ankiforge.utils.paths import get_media_dir

logger = logging.getLogger(__name__)

ANTHROPIC_MAX_VISION_IMAGES = 20
DEFAULT_MAX_VISION_IMAGES = 50


def get_max_vision_images_for_provider(provider: str) -> int:
    """Retourne le nombre maximal d'images supporté en un seul appel par le fournisseur d'IA.

    Anthropic plafonne à 20 images par requête, les autres bénéficient d'un plafond de sécurité de 50.
    """
    if str(provider).strip().lower() == "anthropic":
        return ANTHROPIC_MAX_VISION_IMAGES
    return DEFAULT_MAX_VISION_IMAGES


class VisualPayloadResolver:
    """Couture unique de résolution visuelle de fragment (ADR 0018).

    Résout de façon déterministe les images conformes associées à un fragment ou une portée,
    en appliquant fidèlement la rotation durable des planches d'album (ADR 0011) et en unifiant
    l'acheminement des illustrations pour les générateurs (Studio, Batch) et le RAG.
    """

    def __init__(
        self,
        album_service: AlbumService | None = None,
        media_dir: Path | None = None,
    ) -> None:
        from ankiforge.services.cards.media_manager import MediaManager

        self.media_dir = media_dir or get_media_dir()
        mm = MediaManager(media_dir=self.media_dir)
        self.album_service = album_service or AlbumService(media_manager=mm)

    def resolve_visual_images(
        self,
        document_id: int | None = None,
        chunk: DocumentChunkModel | dict[str, Any] | None = None,
        page_numbers: Sequence[int] | None = None,
        media_dir: Path | None = None,
    ) -> list[dict[str, Any]]:
        """Résout et encode en Base64 les images correspondant au document ou fragment fourni.

        Args:
            document_id: ID du document source si connu.
            chunk: Modèle Peewee ou dictionnaire représentant le fragment à résoudre.
            page_numbers: Numéros de planches spécifiques à extraire.
            media_dir: Dossier des médias pour la résolution des fichiers physiques.

        Returns:
            Liste d'objets `{"type": "image_url", "image_url": {"url": "data:..."}}`.
        """
        effective_media_dir = media_dir or self.media_dir
        resolved_images: list[dict[str, Any]] = []

        from ankiforge.services.cards.media_manager import MediaManager

        album_service = self.album_service if effective_media_dir == self.media_dir else AlbumService(media_manager=MediaManager(media_dir=effective_media_dir))

        doc: DocumentModel | None = None
        doc_id = document_id
        if doc_id is None and chunk is not None:
            if isinstance(chunk, DocumentChunkModel):
                doc_id = chunk.document_id
            elif isinstance(chunk, dict) and "document_id" in chunk:
                doc_id = chunk["document_id"]

        if doc_id is not None:
            doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)

        is_album = doc is not None and doc.file_type == "album"

        # 1. Résolution pour un Album (application stricte de la couture ADR 0011)
        if is_album and doc is not None:
            pages_to_fetch: list[int] = []
            if page_numbers is not None and len(page_numbers) > 0:
                pages_to_fetch = [int(p) for p in page_numbers]
            elif chunk is not None:
                p_num = chunk.page_number if isinstance(chunk, DocumentChunkModel) else chunk.get("page_number")
                if p_num is not None:
                    pages_to_fetch = [int(p_num)]

            query = DocumentPageModel.select().where(DocumentPageModel.document == doc).order_by(DocumentPageModel.page_number.asc())
            if pages_to_fetch:
                query = query.where(DocumentPageModel.page_number.in_(pages_to_fetch))

            pages = list(query)
            for page in pages:
                try:
                    rendered_img = album_service.render_page_image(page)
                    try:
                        buffer = io.BytesIO()
                        rendered_img.save(buffer, format="PNG")
                        b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
                        resolved_images.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64_str}"},
                            }
                        )
                    finally:
                        rendered_img.close()
                except Exception as err:
                    logger.warning("Échec du rendu de la planche %s pour le payload visuel : %s", page.id, err)

            return resolved_images

        # 2. Résolution pour un fragment avec clé étrangère média liée (hors album, ex: PDF, docx)
        if chunk is not None:
            media_obj = None
            if isinstance(chunk, DocumentChunkModel):
                media_obj = chunk.media
            elif isinstance(chunk, dict) and "media" in chunk and chunk["media"]:
                media_obj = chunk["media"]

            if media_obj is not None:
                fname = getattr(media_obj, "filename", None)
                if not fname and isinstance(media_obj, dict):
                    fname = media_obj.get("filename")
                if fname:
                    file_path = effective_media_dir / str(fname)
                    if file_path.exists():
                        try:
                            with open(file_path, "rb") as fh:
                                b64 = base64.b64encode(fh.read()).decode("utf-8")
                            mtype, _ = mimetypes.guess_type(str(file_path))
                            if not mtype:
                                mtype = "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
                            resolved_images.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mtype};base64,{b64}"},
                                }
                            )
                        except Exception as err:
                            logger.warning("Impossible de lire l'image liée %s : %s", file_path, err)

        return resolved_images

    def list_document_figures(
        self,
        document_id: int,
        heading_path: str | None = None,
    ) -> list[DocumentChunkModel]:
        """Liste, **sans les encoder**, les fragments porteurs d'une figure d'un document.

        C'est la seule source de vérité pour « quelles illustrations ce document
        contient-il ? ». Elle applique le même critère que :meth:`resolve_visual_images`
        (un fragment à clé média liée). Interroger ``DocumentChunkModel.media`` ailleurs
        créerait une seconde règle de sélection qui divergerait de la résolution — ce que
        la couture ADR 0018 existe pour empêcher.

        Args:
            document_id: Le document dont on veut les figures.
            heading_path: Fil d'Ariane de la section à restreindre. ``None`` = tout le
                document.

        Returns:
            Les fragments en périmètre, ordonnés par position
            (index de fragment, puis id). Vide si le document est non indexé ou sans figure.
        """
        query = (
            DocumentChunkModel.select()
            .where((DocumentChunkModel.document == document_id) & (DocumentChunkModel.media.is_null(False)))
            .order_by(DocumentChunkModel.chunk_index.asc(), DocumentChunkModel.id.asc())
        )
        if heading_path:
            query = query.where(DocumentChunkModel.heading_path == heading_path)
        return list(query)

    def figure_media_path(self, chunk: DocumentChunkModel, media_dir: Path | None = None) -> Path | None:
        """Chemin physique de la figure portée par un fragment, ou ``None`` si le fichier manque.

        Le nom de fichier vient de la clé média du fragment, jamais d'une convention
        reconstruite côté appelant : une seule règle de localisation, comme pour l'encodage.
        """
        media = chunk.media
        if media is None or not getattr(media, "filename", None):
            return None
        path = (media_dir or self.media_dir) / str(media.filename)
        return path if path.exists() else None
