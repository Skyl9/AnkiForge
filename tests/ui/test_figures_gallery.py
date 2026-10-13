"""
Tests headless du widget « Figures » de l'Inspecteur.

Le widget ne fait que deux choses : lire la couture visuelle et émettre un désir d'occlusion.
Ces tests verrouillent la lecture (portée, tri-state) et l'émission, jamais le rendu d'une
vignette (qui est asynchrone et appartient à la plaque de vignettes).
"""

from __future__ import annotations

import uuid

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    MediaModel,
)
from ankiforge.services.cards.visual_resolver import VisualPayloadResolver
from ankiforge.ui.components import EmptyStateWidget
from ankiforge.ui.views.documents_view.widgets.figures_gallery import (
    FigureCard,
    FiguresGalleryWidget,
)

pytestmark = pytest.mark.ui


def _figure_cards(gallery: FiguresGalleryWidget) -> list[FigureCard]:
    cards: list[FigureCard] = []
    for i in range(gallery.cards_layout.count()):
        widget = gallery.cards_layout.itemAt(i).widget()
        if isinstance(widget, FigureCard):
            cards.append(widget)
    return cards


def _empty_title(gallery: FiguresGalleryWidget) -> str | None:
    for i in range(gallery.cards_layout.count()):
        widget = gallery.cards_layout.itemAt(i).widget()
        if isinstance(widget, EmptyStateWidget):
            return widget.title_lbl.text()
    return None


@pytest.fixture
def media_dir(tmp_path):
    d = tmp_path / "media"
    d.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color="white").save(d / "fig.png")
    return d


def _make_doc_with_figure(media_dir_path) -> tuple[DocumentModel, DocumentChunkModel]:
    doc = DocumentModel.create(title="Cours", file_type="pdf", content="")
    media = MediaModel.create(
        filename="fig.png",
        media_type="image",
        original_name="fig.png",
        checksum=uuid.uuid4().hex,
        mime_type="image/png",
    )
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Mécanique",
        content="Un schéma.",
        content_hash=uuid.uuid4().hex,
        media=media,
        page_number=2,
    )
    return doc, chunk


def test_gallery_without_document_shows_neutral_empty(qtbot):
    gallery = FiguresGalleryWidget(resolver=VisualPayloadResolver())
    qtbot.addWidget(gallery)
    gallery.load(None, None)

    assert _empty_title(gallery) == "Aucun document sélectionné"
    assert _figure_cards(gallery) == []


def test_gallery_unindexed_document_shows_non_indexed_empty(qtbot, media_dir):
    gallery = FiguresGalleryWidget(resolver=VisualPayloadResolver(media_dir=media_dir))
    qtbot.addWidget(gallery)
    doc = DocumentModel.create(title="Vide", file_type="md", content="")
    gallery.load(doc, None)

    assert _empty_title(gallery) == "Document non indexé"


def test_gallery_indexed_without_figure_shows_no_figure_empty(qtbot, media_dir):
    gallery = FiguresGalleryWidget(resolver=VisualPayloadResolver(media_dir=media_dir))
    qtbot.addWidget(gallery)
    doc = DocumentModel.create(title="Texte", file_type="md", content="")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Intro",
        content="Texte seul.",
        content_hash=uuid.uuid4().hex,
    )
    gallery.load(doc, None)

    assert _empty_title(gallery) == "Aucune figure"


def test_gallery_lists_figures_of_document(qtbot, media_dir):
    gallery = FiguresGalleryWidget(resolver=VisualPayloadResolver(media_dir=media_dir))
    qtbot.addWidget(gallery)
    doc, chunk = _make_doc_with_figure(media_dir)
    gallery.load(doc, None)

    cards = _figure_cards(gallery)
    assert len(cards) == 1
    assert cards[0].chunk_id == chunk.id
    assert _empty_title(gallery) is None


def test_gallery_filters_by_section(qtbot, media_dir):
    gallery = FiguresGalleryWidget(resolver=VisualPayloadResolver(media_dir=media_dir))
    qtbot.addWidget(gallery)
    doc, _chunk = _make_doc_with_figure(media_dir)

    gallery.load(doc, "Section inexistante")
    assert _figure_cards(gallery) == []
    assert _empty_title(gallery) == "Aucune figure dans cette section"

    gallery.load(doc, "Mécanique")
    assert len(_figure_cards(gallery)) == 1


def test_gallery_whole_document_toggle_ignores_section(qtbot, media_dir):
    gallery = FiguresGalleryWidget(resolver=VisualPayloadResolver(media_dir=media_dir))
    qtbot.addWidget(gallery)
    doc, _chunk = _make_doc_with_figure(media_dir)

    gallery.load(doc, "Section inexistante")
    assert _figure_cards(gallery) == []

    gallery.load(doc, "Section inexistante", whole_document=True)
    assert len(_figure_cards(gallery)) == 1


def test_gallery_album_document_defers_to_album_view(qtbot, media_dir):
    gallery = FiguresGalleryWidget(resolver=VisualPayloadResolver(media_dir=media_dir))
    qtbot.addWidget(gallery)
    album = DocumentModel.create(title="Planches", file_type="album", content="")
    gallery.load(album, None)

    assert _empty_title(gallery) == "Document album"


def test_card_action_emits_occlusion_requested(qtbot, media_dir):
    gallery = FiguresGalleryWidget(resolver=VisualPayloadResolver(media_dir=media_dir))
    qtbot.addWidget(gallery)
    doc, chunk = _make_doc_with_figure(media_dir)
    gallery.load(doc, None)

    received: list[int] = []
    gallery.occlusion_requested.connect(received.append)
    card = _figure_cards(gallery)[0]
    qtbot.mouseClick(card.btn_occlude, Qt.MouseButton.LeftButton)

    assert received == [chunk.id]
