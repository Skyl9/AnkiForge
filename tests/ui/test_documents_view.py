import uuid
from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.views.documents_view import DocumentsView


def test_documents_view_selection_and_coverage(qtbot):
    """Vérifie le chargement des chapitres et les indicateurs de couverture dans DocumentsView."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Anatomie {uid}",
        content="# Chapitre 1 : Le Cœur\n\nLe cœur est un organe musculaire creux qui assure la circulation sanguine.\n\n# Chapitre 2 : Les Poumons\n\nLes poumons sont les organes de la respiration.",
        file_type="md",
    )

    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Anatomie > Chapitre 1 : Le Cœur",
        page_number=1,
        content="Le cœur est un organe musculaire creux qui assure la circulation sanguine.",
        content_hash=f"hash1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Anatomie > Chapitre 2 : Les Poumons",
        page_number=2,
        content="Les poumons sont les organes de la respiration.",
        content_hash=f"hash2_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Médecine {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )
    note1 = NoteModel.create(guid=uuid.uuid4().hex, deck=deck, note_type=nt, fields_data='{"Front": "Rôle du cœur ?", "Back": "Pompe sanguine"}')
    NoteChunkLinkModel.create(note=note1, chunk=chunk1)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    # Simuler la sélection du document
    view._current_doc_id = doc.id
    view._refresh_chapters_list()

    # Vérifications du sommaire
    assert view.chapters_list.count() == 2
    item1 = view.chapters_list.item(0)
    assert "🟢" in item1.text()
    assert "Couvert" in item1.text()

    item2 = view.chapters_list.item(1)
    assert "⚠️" in item2.text()
    assert "Non couvert" in item2.text()

    assert "50%" in view.lbl_coverage_summary.text()

    # Vérifier l'émission du signal de navigation vers la création
    emitted_nav = []
    view.request_navigation.connect(lambda target, payload: emitted_nav.append((target, payload)))

    view.chapters_list.setCurrentRow(1)
    view._on_forge_selected_chapter()

    assert len(emitted_nav) == 1
    target, payload = emitted_nav[0]
    assert target == "creation"
    assert "poumons" in payload["text_source"].lower()
