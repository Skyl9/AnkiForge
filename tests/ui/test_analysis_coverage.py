import uuid
from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.views.analysis_view import DocumentInspectorPanel


def test_document_inspector_panel_chapter_coverage(qtbot):
    """Vérifie l'affichage de la heatmap et de l'inspecteur de fragments dans l'Audit de Document."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Droit {uid}",
        content="# Article 1\nLe contrat est un accord de volontés.\n\n# Article 2\nChacun est libre de contracter.",
        file_type="md",
    )

    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Droit > Article 1",
        content="Le contrat est un accord de volontés.",
        content_hash=f"hash1_{uid}",
    )
    chunk2 = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Droit > Article 2",
        content="Chacun est libre de contracter.",
        content_hash=f"hash2_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Droit {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model Droit {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )
    note1 = NoteModel.create(
        guid=uuid.uuid4().hex,
        deck=deck,
        note_type=nt,
        fields_data='{"Front": "Définition du contrat ?", "Back": "Accord de volontés."}',
    )
    NoteChunkLinkModel.create(note=note1, chunk=chunk1)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    panel.load_chunks()
    assert "Article 1" in panel.text_browser.toHtml()
    assert "🟢 Couvert" in panel.text_browser.toHtml()
    assert "⚠️ Non couvert" in panel.text_browser.toHtml()

    # Inspecter le chunk couvert (chunk 1)
    panel.inspect_chunk(chunk1.id)
    assert "1 carte(s) Anki associée(s)" in panel.facets_layout.itemAt(0).widget().text()

    # Inspecter le chunk orphelin (chunk 2)
    panel.inspect_chunk(chunk2.id)
    assert "Aucune flashcard" in panel.lbl_chunk_preview.text() or panel.facets_layout.count() >= 1
