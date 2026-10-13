"""
Tests de la couture de listing des figures (`VisualPayloadResolver`).

La couture ne se contente pas de résoudre des images : elle doit aussi **dire quelles
figures existent**, sans les encoder. Ces tests verrouillent cette seconde responsabilité,
puisque c'est elle qui alimente la galerie de l'onglet « Figures ».
"""

from __future__ import annotations

import pytest
from PIL import Image

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    MediaModel,
)
from ankiforge.services.cards.visual_resolver import VisualPayloadResolver

pytestmark = pytest.mark.unit


@pytest.fixture
def figures_doc(tmp_path, monkeypatch):
    """Un document non-album à trois fragments, dont deux porteurs de figure."""
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("ankiforge.utils.paths.get_media_dir", lambda *args, **kwargs: media_dir)

    for name in ("fig_a.png", "fig_b.png"):
        Image.new("RGB", (60, 40), color="white").save(media_dir / name)

    doc = DocumentModel.create(title="Cours illustré", file_type="pdf", total_pages=4, content="")
    media_a = MediaModel.create(
        filename="fig_a.png",
        media_type="image",
        original_name="fig_a.png",
        checksum="chk_a",
        mime_type="image/png",
    )
    media_b = MediaModel.create(
        filename="fig_b.png",
        media_type="image",
        original_name="fig_b.png",
        checksum="chk_b",
        mime_type="image/png",
    )

    text_only = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Introduction",
        content="Un paragraphe sans illustration.",
        content_hash="h0",
    )
    fig_1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Mécanique",
        content="Un schéma de mécanique.",
        content_hash="h1",
        media=media_a,
        page_number=2,
    )
    fig_2 = DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        heading_path="Mécanique",
        content="Un second schéma de mécanique.",
        content_hash="h2",
        media=media_b,
        page_number=3,
    )
    return doc, [text_only, fig_1, fig_2], media_dir


def test_list_document_figures_only_returns_media_chunks(figures_doc):
    doc, chunks, media_dir = figures_doc
    resolver = VisualPayloadResolver(media_dir=media_dir)

    figures = resolver.list_document_figures(doc.id)

    assert [c.id for c in figures] == [chunks[1].id, chunks[2].id]
    assert all(c.media is not None for c in figures)


def test_list_document_figures_is_ordered_by_chunk_index(figures_doc):
    doc, chunks, media_dir = figures_doc
    resolver = VisualPayloadResolver(media_dir=media_dir)

    figures = resolver.list_document_figures(doc.id)

    assert [c.chunk_index for c in figures] == [1, 2]


def test_list_document_figures_filters_by_section(figures_doc):
    doc, chunks, media_dir = figures_doc
    resolver = VisualPayloadResolver(media_dir=media_dir)

    figures = resolver.list_document_figures(doc.id, heading_path="Introduction")
    assert figures == []

    figures = resolver.list_document_figures(doc.id, heading_path="Mécanique")
    assert [c.id for c in figures] == [chunks[1].id, chunks[2].id]


def test_list_document_figures_is_empty_for_unindexed_document(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    doc = DocumentModel.create(title="Vide", file_type="md", content="")
    resolver = VisualPayloadResolver(media_dir=media_dir)

    assert resolver.list_document_figures(doc.id) == []


def test_figure_media_path_resolves_existing_file(figures_doc):
    doc, chunks, media_dir = figures_doc
    resolver = VisualPayloadResolver(media_dir=media_dir)

    path = resolver.figure_media_path(chunks[1])
    assert path == media_dir / "fig_a.png"
    assert path is not None and path.exists()


def test_figure_media_path_is_none_when_file_missing(figures_doc):
    doc, chunks, media_dir = figures_doc
    resolver = VisualPayloadResolver(media_dir=media_dir)
    (media_dir / "fig_a.png").unlink()

    assert resolver.figure_media_path(chunks[1]) is None


def test_figure_media_path_is_none_for_text_chunk(figures_doc):
    doc, chunks, media_dir = figures_doc
    resolver = VisualPayloadResolver(media_dir=media_dir)

    assert resolver.figure_media_path(chunks[0]) is None
