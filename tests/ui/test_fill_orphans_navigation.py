import uuid
from typing import Any

import pytest

from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    LLMConfigModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.ui.views.analysis_view.tabs.sources_tab import (
    AISourcesDiagnosticTab,
    DocumentInspectorPanel,
)
from ankiforge.ui.views.creation_view import CreationView
from ankiforge.utils.region_address import parse_region_address

pytestmark = pytest.mark.ui


class DummyCreationAIManager:
    """Mock minimal de gestionnaire IA pour CreationView."""

    def create_provider_from_config(self, _config: Any) -> Any:
        return None


def test_fill_orphans_navigates_to_creation_with_document_and_orphan_sections(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que le bouton 'Générer les cartes manquantes' transmet le document et pré-sélectionne les sections orphelines."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"Type {uid}", fields_schema='["Front", "Back"]')
    deck = DeckModel.create(name=f"Deck {uid}")
    pipe = PipelineModel.create(name=f"Pipe {uid}")
    persona = PersonaModel.create(name=f"Persona {uid}", system_prompt="Sys", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_type="LLM_PROMPT", step_order=1)
    LLMConfigModel.create(provider="mock", model_id=f"m_{uid}", display_name=f"Model {uid}")

    doc = DocumentModel.create(title=f"Cours Neuro {uid}", file_type="md", content="Neuro content")
    c1 = DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Introduction", content="Contenu intro", token_count=20)
    DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Cortex", content="Contenu cortex", token_count=30)
    DocumentChunkModel.create(document=doc, chunk_index=2, heading_path="Cervelet", content="Contenu cervelet", token_count=40)

    # c1 (Introduction) est déjà couvert par une carte
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, fields='{"Front": "Q", "Back": "A"}')
    NoteChunkLinkModel.create(note=note, chunk=c1)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    nav_events: list[tuple[str, dict[str, Any]]] = []
    panel.request_navigation.connect(lambda view, data: nav_events.append((view, data)))

    # Déclencher le bouton « Générer les cartes manquantes »
    panel.btn_fill_orphans.click()

    assert len(nav_events) == 1
    target_view, payload = nav_events[0]
    assert target_view == "creation"
    assert payload["doc_id"] == doc.id
    assert "scope_result" in payload

    scope_res = payload["scope_result"]
    assert scope_res["selection_mode"] == "sections"
    assert set(scope_res["selected_headings"]) == {"Cortex", "Cervelet"}
    assert "Introduction" not in scope_res["selected_headings"]
    assert len(scope_res["chunks"]) == 2
    assert {c["title"] for c in scope_res["chunks"]} == {"Cortex", "Cervelet"}

    # Atterrissage dans CreationView
    ai_mgr = DummyCreationAIManager()
    creation = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(creation)
    creation.current_deck = deck
    creation.current_model = nt
    creation.refresh_data()

    creation.load_context(payload)

    # Vérifications des critères d'acceptation dans CreationView
    assert creation._current_selected_doc is not None
    assert creation._current_selected_doc.id == doc.id
    assert creation.current_source_doc_id == doc.id

    # La portée est pré-sélectionnée sur les sections lacunaires
    assert "2 section(s)" in creation.segment_inspector.lbl_active_scope_title.text()
    active_segs = creation.segment_inspector.get_active_segments()
    assert len(active_segs) == 2
    assert {s["title"] for s in active_segs} == {"Cortex", "Cervelet"}

    # Lancement de la génération et récapitulatif
    creation._on_generate()
    assert creation.orchestrator is not None
    state = creation.orchestrator.state
    assert state is not None
    assert state.get_variable("document_id") == doc.id
    assert state.get_variable("document_title") == doc.title

    text_source = state.get_variable("text_source")
    assert "Contenu cortex" in text_source
    assert "Contenu cervelet" in text_source
    assert "Contenu intro" not in text_source

    # Vérification du récapitulatif dans les logs console
    console_text = creation.generation_logs_console.toPlainText()
    assert doc.title in console_text
    assert "Portée :" in console_text
    assert "Cortex" in console_text or "Cervelet" in console_text


def test_fill_orphans_all_covered_shows_toast_and_no_navigation(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Vérifie qu'un document 100% couvert affiche un toast informatif sans déclencher de navigation."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"Type {uid}", fields_schema='["Front", "Back"]')
    doc = DocumentModel.create(title=f"Cours Couvert {uid}", file_type="md", content="Plein")
    c1 = DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Unique", content="Contenu", token_count=10)
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, fields='{"Front": "Q", "Back": "A"}')
    NoteChunkLinkModel.create(note=note, chunk=c1)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    toasts: list[str] = []
    from ankiforge.ui.views.analysis_view.tabs import sources_tab

    monkeypatch.setattr(sources_tab, "show_toast", lambda _parent, msg, **_kw: toasts.append(msg))

    nav_events: list[Any] = []
    panel.request_navigation.connect(lambda view, data: nav_events.append((view, data)))

    panel.btn_fill_orphans.click()

    assert len(nav_events) == 0
    assert len(toasts) == 1
    assert "déjà couvertes" in toasts[0]


def test_fill_orphans_not_indexed_shows_toast_and_no_navigation(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Vérifie qu'un document non couvrable (sans fragment indexé) informe l'utilisateur."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc Vide {uid}", file_type="md", content="")

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    toasts: list[str] = []
    from ankiforge.ui.views.analysis_view.tabs import sources_tab

    monkeypatch.setattr(sources_tab, "show_toast", lambda _parent, msg, **_kw: toasts.append(msg))

    nav_events: list[Any] = []
    panel.request_navigation.connect(lambda view, data: nav_events.append((view, data)))

    panel.btn_fill_orphans.click()

    assert len(nav_events) == 0
    assert len(toasts) == 1
    assert "aucun fragment indexé" in toasts[0]


def test_fill_orphans_all_excluded_shows_toast_and_no_navigation(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Vérifie qu'un document dont toutes les sections sont exclues informe l'utilisateur sans naviguer."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc Exclu {uid}", file_type="md", content="Contenu")
    DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Exclu 1", content="C1", token_count=10)
    DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Exclu 2", content="C2", token_count=10)

    repo = DocumentRepository()
    repo.set_region_excluded(doc.id, parse_region_address("heading:Exclu 1"), True)
    repo.set_region_excluded(doc.id, parse_region_address("heading:Exclu 2"), True)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    toasts: list[str] = []
    from ankiforge.ui.views.analysis_view.tabs import sources_tab

    monkeypatch.setattr(sources_tab, "show_toast", lambda _parent, msg, **_kw: toasts.append(msg))

    nav_events: list[Any] = []
    panel.request_navigation.connect(lambda view, data: nav_events.append((view, data)))

    panel.btn_fill_orphans.click()

    assert len(nav_events) == 0
    assert len(toasts) == 1
    assert "exclues" in toasts[0]


def test_card_forge_orphan_requested_diagnostic_tab(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que le déclencheur d'orphelines depuis la grille des cours transmet également document + portée."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"Type {uid}", fields_schema='["Front", "Back"]')
    doc = DocumentModel.create(title=f"Doc Grid {uid}", file_type="md", content="Contenu")
    c1 = DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Couvert", content="C1", token_count=10)
    DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Manquant", content="C2", token_count=15)

    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, fields='{"Front": "Q", "Back": "A"}')
    NoteChunkLinkModel.create(note=note, chunk=c1)

    diag_tab = AISourcesDiagnosticTab()
    qtbot.addWidget(diag_tab)

    nav_events: list[tuple[str, dict[str, Any]]] = []
    diag_tab.request_navigation.connect(lambda view, data: nav_events.append((view, data)))

    diag_tab._on_card_forge_orphan_requested(doc.id)

    assert len(nav_events) == 1
    view_name, payload = nav_events[0]
    assert view_name == "creation"
    assert payload["doc_id"] == doc.id
    assert "scope_result" in payload
    assert payload["scope_result"]["selected_headings"] == ["Manquant"]


def test_fill_orphans_paginated_document_without_headings(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que pour un document paginé sans titres (PDF brut), la portée orpheline sélectionne les pages manquantes."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"Type {uid}", fields_schema='["Front", "Back"]')
    doc = DocumentModel.create(title=f"Doc PDF {uid}", file_type="pdf", total_pages=3)
    c1 = DocumentChunkModel.create(document=doc, chunk_index=0, page_number=1, content="Page 1", token_count=10)
    DocumentChunkModel.create(document=doc, chunk_index=1, page_number=2, content="Page 2", token_count=10)
    DocumentChunkModel.create(document=doc, chunk_index=2, page_number=3, content="Page 3", token_count=10)

    # Page 1 couverte
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, fields='{"Front": "Q", "Back": "A"}')
    NoteChunkLinkModel.create(note=note, chunk=c1)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    nav_events: list[tuple[str, dict[str, Any]]] = []
    panel.request_navigation.connect(lambda view, data: nav_events.append((view, data)))

    panel.btn_fill_orphans.click()

    assert len(nav_events) == 1
    _view, payload = nav_events[0]
    assert payload["doc_id"] == doc.id
    scope_res = payload["scope_result"]
    assert scope_res["selection_mode"] == "pages"
    assert scope_res["selected_pages"] == [2, 3]
