import uuid
from PySide6.QtCore import Qt

from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.views.documents_view import (
    DocumentDelimitationDialog,
    DocumentsView,
    RAGTestDialog,
)


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
    note1 = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note1.add_version({"Front": "Rôle du cœur ?", "Back": "Pompe sanguine"}, source="manual")
    from ankiforge.database.models import CardModel

    CardModel.create(note=note1, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note1, chunk=chunk1)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    # Simuler la sélection du document
    view._current_doc_id = doc.id
    view._refresh_chapters_list()
    view._update_rag_status_pill()

    # Vérifications du sommaire
    assert view.chapters_list.count() == 2
    item1 = view.chapters_list.item(0)
    assert "🟢" in item1.text()
    assert "Couvert" in item1.text()

    item2 = view.chapters_list.item(1)
    assert "⚠️" in item2.text()
    assert "Non couvert" in item2.text()

    assert "50%" in view.lbl_coverage_summary.text()
    assert "2 chunks" in view.rag_status_pill.text()

    # Vérifier l'émission du signal de navigation vers la création
    emitted_nav = []
    view.request_navigation.connect(lambda target, payload: emitted_nav.append((target, payload)))

    view.chapters_list.setCurrentRow(1)
    view._on_forge_selected_chapter()

    assert len(emitted_nav) == 1
    target, payload = emitted_nav[0]
    assert target == "creation"
    assert "poumons" in payload["text_source"].lower()


def test_document_delimitation_dialog(qtbot):
    """Vérifie la modale de délimitation de pages et de filtrage des chapitres."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Livre Biologie {uid}",
        content="# Sommaire\n\nPage 1.\n\n# Chapitre 1 : La Cellule\n\nStructure cellulaire.\n\n# Bibliographie\n\nOuvrages de référence.",
        file_type="md",
    )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Vérifier les sections peuplées
    assert dlg.sections_list.count() == 3

    # Sommaire et Bibliographie doivent être décochés par le filtre initial
    assert dlg.sections_list.item(0).checkState() == Qt.CheckState.Unchecked
    assert dlg.sections_list.item(1).checkState() == Qt.CheckState.Checked
    assert dlg.sections_list.item(2).checkState() == Qt.CheckState.Unchecked

    # Appliquer la délimitation
    dlg.chk_revectorize.setChecked(False)
    dlg._on_apply()

    # Vérifier les chunks mis à jour en base
    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert len(chunks) == 1
    assert "Cellule" in chunks[0].heading_path


def test_rag_test_dialog(qtbot):
    """Vérifie le dialogue de recherche sémantique interactive RAG."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc RAG {uid}",
        content="Les mitochondries produisent l'énergie sous forme d'ATP.",
        file_type="md",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Bioénergétique",
        page_number=5,
        content="Les mitochondries produisent l'énergie sous forme d'ATP.",
        content_hash=f"hash_{uid}",
    )

    from ankiforge.services.ai.rag_service import RAGService

    rag = RAGService()
    rag.create_index(doc.id)

    dlg = RAGTestDialog(doc)
    qtbot.addWidget(dlg)

    dlg.search_input.setText("ATP")
    dlg._on_search()

    assert dlg.results_list.count() >= 1
    res_text = dlg.results_list.item(0).text()
    assert "Bioénergétique" in res_text or "ATP" in res_text
