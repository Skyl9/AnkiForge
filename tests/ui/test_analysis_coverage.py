import uuid
from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.views.analysis_view import DocumentInspectorPanel, AISourcesDiagnosticTab


def test_document_inspector_panel_chapter_coverage(qtbot):
    """Vérifie l'affichage du sommaire et des cartes liées dans DocumentInspectorPanel."""
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

    # Vérification du sommaire (2 items)
    assert panel.chapters_list.count() == 2
    item1 = panel.chapters_list.item(0)
    assert "🟢" in item1.text()
    assert "1 carte" in item1.text()

    item2 = panel.chapters_list.item(1)
    assert "⚠️" in item2.text()
    assert "0 carte" in item2.text()

    # Inspecter le chunk couvert (chunk 1)
    panel.inspect_chunk(chunk1.id)
    assert "1 carte(s) Anki forgée(s)" in panel.cards_layout.itemAt(0).widget().text()

    # Inspecter le chunk orphelin (chunk 2)
    panel.inspect_chunk(chunk2.id)
    assert panel.cards_layout.count() >= 1

    # Navigation vers création
    emitted = []
    panel.request_navigation.connect(lambda target, payload: emitted.append((target, payload)))
    panel._on_forge_chunk(chunk2.id)
    assert len(emitted) == 1
    assert emitted[0][0] == "creation"
    assert "contracter" in emitted[0][1]["text_source"].lower()


def test_ai_sources_diagnostic_tab_grid_and_kpis(qtbot):
    """Vérifie la grille de diagnostic des sources et les KPIs globaux de la Forge."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Test {uid}",
        content="# Section 1\nContenu A\n\n# Section 2\nContenu B",
        file_type="md",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Section 1",
        content="Contenu A",
        content_hash=f"h1_{uid}",
    )

    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    tab.refresh_data()
    assert "Documents :" in tab.lbl_kpi_docs.text()
    assert "Couverture Moyenne :" in tab.lbl_kpi_coverage.text()
    assert tab.grid_layout.count() >= 1

    # Test switch to inspector
    tab.show_inspector(doc.id)
    assert tab.stack.currentIndex() == 1
