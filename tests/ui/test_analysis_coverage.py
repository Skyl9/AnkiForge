import uuid
from typing import Any

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.components.duplicate_widgets import (
    DuplicateMatrixTable,
    DuplicateMergeInspector,
)
from ankiforge.ui.components.linter_widgets import WozniakCardItemWidget
from ankiforge.ui.views.analysis_view import (
    AISourcesDiagnosticTab,
    AITokensSrsTab,
    AIWozniakLinterTab,
    AnalysisView,
    DocumentInspectorPanel,
)


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
    note1 = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note1.add_version({"Front": "Définition du contrat ?", "Back": "Accord de volontés."}, source="manual")
    CardModel.create(note=note1, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note1, chunk=chunk1)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    panel.load_chunks()

    # Vérification du sommaire (2 items)
    assert panel.chapters_list.count() == 2
    item1 = panel.chapters_list.item(0)
    assert "1 carte" in item1.text()

    item2 = panel.chapters_list.item(1)
    assert "0 carte" in item2.text() or "Trou" in item2.text()

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
    assert tab.lbl_kpi_docs_val.text() != "--"
    assert tab.grid_layout.count() >= 1

    # Test switch to inspector
    tab.show_inspector(doc.id)
    assert tab.stack.currentIndex() == 1


def test_ai_wozniak_linter_tab_and_widgets(qtbot):
    """Vérifie l'onglet Linter Wozniak, la sélection de catégorie et l'inspection de carte."""
    tab = AIWozniakLinterTab()
    qtbot.addWidget(tab)

    assert "Score :" in tab.score_badge.text()
    assert len(tab.kpi_cards) == 4

    # Tester le basculement de catégorie
    tab.on_category_kpi_clicked("cat-katex")
    assert tab.active_category == "cat-katex"

    # Tester le widget de carte problème Wozniak
    item_data: dict[str, Any] = {
        "title": "Carte #42 - Liste trop longue",
        "badge": "Viol Atomicité",
        "badge_color": "#f87171",
        "original": {"Recto": "Quels sont les 10 principes ?", "Verso": "1, 2, 3..."},
        "proposal": {"Recto": "Quel est le principe 1 ?", "Verso": "1"},
        "proposal_summary": "Scission en cartes atomiques univoques",
    }
    card_w = WozniakCardItemWidget(item_data)
    qtbot.addWidget(card_w)

    assert card_w.inspector_widget.isHidden()
    card_w.toggle_inspector()
    assert not card_w.inspector_widget.isHidden()


def test_ai_tokens_srs_tab(qtbot):
    """Vérifie le simulateur économique de jetons IA et d'impact SRS FSRS-4.5."""
    tab = AITokensSrsTab()
    qtbot.addWidget(tab)

    assert "Dépenses" in tab.lbl_spent.text()
    assert "carte" in tab.lbl_cost.text()
    tab.refresh_stats()
    assert tab.kpi_grid.count() == 4


def test_ai_duplicates_merge_tab_and_inspector(qtbot):
    """Vérifie l'inspecteur de fusion à 3 panneaux et la matrice de doublons."""
    matrix = DuplicateMatrixTable()
    qtbot.addWidget(matrix)
    assert matrix.table.columnCount() == 6

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name="Model Dup Test",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style="",
    )
    note_a = NoteModel.create(guid="guid_a", note_type=nt)
    note_b = NoteModel.create(guid="guid_b", note_type=nt)

    inspector = DuplicateMergeInspector()
    qtbot.addWidget(inspector)

    # Tester la permutation A <-> B
    inspector.current_conflict = {
        "note_a": note_a,
        "content_a": {"Recto": "Question A", "Verso": "Réponse A"},
        "note_b": note_b,
        "content_b": {"Recto": "Question B", "Verso": "Réponse B"},
        "similarity": 0.92,
    }
    inspector.on_swap()
    assert inspector.current_conflict["content_a"]["Recto"] == "Question B"


def test_analysis_view_main_container(qtbot):
    """Vérifie l'initialisation du conteneur principal de l'Hôpital (AnalysisView)."""
    view = AnalysisView()
    qtbot.addWidget(view)

    assert view is not None
    assert view.main_panel.content_stack.count() == 4  # 4 onglets : Wozniak, Sources, Jetons/SRS, Doublons
