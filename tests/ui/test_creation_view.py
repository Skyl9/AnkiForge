import json
import uuid
from typing import Any

import pytest

from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    LLMConfigModel,
    MediaModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.ui.dialogs.human_validation_dialog import HumanValidationDialog
from ankiforge.ui.views.creation_view import CreationView
from ankiforge.ui.views.creation_view.widgets.document_editor import DocumentEditorWidget


class DummyCreationProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        return json.dumps(
            {
                "cards": [
                    {"Front": "Qu'est-ce que le DAG ?", "Back": "Un graphe orienté acyclique."},
                    {"Front": "Rôle du Copilote ?", "Back": "Validation humaine interactive."},
                ]
            }
        )


class DummyCreationAIManager:
    def create_provider_from_config(self, config: Any) -> LLMProvider:
        return DummyCreationProvider()


@pytest.mark.ui
def test_creation_view_creation(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'instanciation de base de la vue de création."""
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None


@pytest.mark.slow
@pytest.mark.ui
def test_creation_view_dag_generation_flow(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le déclenchement asynchrone de la génération DAG et la réception des cartes."""

    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Test {uid}")
    nt = NoteTypeModel.create(
        name=f"Modèle Test {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]',
        css_style=".card { font-family: arial; }",
    )
    pipe = PipelineModel.create(name=f"Pipeline Test DAG {uid}")
    persona = PersonaModel.create(name=f"Créateur {uid}", system_prompt="Créer cartes", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_type="LLM_PROMPT", step_order=1)

    LLMConfigModel.create(provider="mock", model_id=f"dummy_{uid}", display_name=f"Mock IA {uid}")

    ai_mgr = DummyCreationAIManager()

    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)

    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    # Sélectionner le pipeline et le moteur dans les combos de l'IHM
    for i in range(view.pipeline_combo.count()):
        if view.pipeline_combo.itemData(i) and getattr(view.pipeline_combo.itemData(i), "id", None) == pipe.id:
            view.pipeline_combo.setCurrentIndex(i)
            break

    for i in range(view.engine_combo.count()):
        data = view.engine_combo.itemData(i)
        if data and getattr(data, "model_id", "") == f"dummy_{uid}":
            view.engine_combo.setCurrentIndex(i)
            break

    # Déclencher la génération asynchrone
    view._on_generate(text_source="Texte source sur le DAG et le Copilote", source_title="Test Document")

    # Attendre que le thread termine la génération et mette à jour le tableau
    qtbot.waitUntil(lambda: view.results_table.rowCount() == 2, timeout=6000)

    assert len(view.generated_cards) == 2
    assert view.generated_cards[0]["Front"] == "Qu'est-ce que le DAG ?"
    assert view.generated_cards[0]["Back"] == "Un graphe orienté acyclique."
    assert view.results_table.rowCount() == 2

    view.thread_pool.waitForDone(2000)


@pytest.mark.ui
def test_human_validation_dialog(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le fonctionnement de la modale HumanValidationDialog."""
    from ankiforge.services.ai.state import PipelineRunState

    state = PipelineRunState()
    state.set_variable("last_output", {"concepts_cles": ["Concept 1", "Concept 2"]})
    state.set_variable("human_validation_config", {"human_title": "Pause Personnalisée", "human_message": "Veuillez valider."})

    dlg = HumanValidationDialog(state=state)
    qtbot.addWidget(dlg)

    assert "Concept 1" in dlg.editor.toPlainText()

    # Tester le formateur JSON
    dlg.editor.setPlainText('{"concepts_cles":["A","B"]}')
    dlg._format_json()
    assert "\n" in dlg.editor.toPlainText()

    # Modifier le texte et valider
    dlg.editor.setPlainText('{"concepts_cles": ["Concept 1 Modifié"]}')
    dlg._on_validate_clicked()

    assert state.get_variable("last_output") == {"concepts_cles": ["Concept 1 Modifié"]}
    assert state.get_variable("map_items") == ["Concept 1 Modifié"]


@pytest.mark.ui
def test_creation_view_cancellation(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'annulation propre de la génération dans CreationView."""
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)

    view._on_cancel_generation()
    assert view.orchestrator is None or view.orchestrator._is_cancelled


@pytest.mark.ui
def test_creation_view_album_context_and_scope(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'affichage adaptatif d'un album (scope, vision, galerie, presets) dans CreationView."""
    uid = uuid.uuid4().hex[:6]
    media = MediaModel.create(
        filename=f"page_{uid}.png",
        original_name=f"orig_{uid}.png",
        checksum=f"chk_{uid}",
        mime_type="image/png",
    )
    doc = DocumentModel.create(
        title=f"Album Neuro {uid}",
        file_type="album",
        total_pages=3,
        content="",
    )
    DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="Schéma du neurone")
    DocumentPageModel.create(document=doc, media=media, page_number=2, ocr_text="Synapse chimique")
    DocumentPageModel.create(document=doc, media=media, page_number=3, ocr_text="")
    DocumentChunkModel.create(document=doc, chunk_index=1, page_number=3, content="Figure 3: Potentiel d'action")

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Charger le document via navigation externe / load_context
    view.load_context({"doc_id": doc.id})

    # Vérifications de l'adaptation multimodale
    assert view.lbl_scope.text() == "PORTÉE DE L'ALBUM"
    assert not view.scope_card.isHidden()
    assert not view.vision_card.isHidden()
    assert view.lbl_vision_title.text() == "Vision Multimodale"

    # Vérifier l'éditeur ouvert
    editor = view.open_editors.get(doc.title)
    assert editor is not None
    content = editor.get_text()
    assert "Schéma du neurone" in content
    assert "Synapse chimique" in content
    assert "Potentiel d'action" in content

    # Tester preset Planche 1
    view.btn_preset_page.click()
    assert view.input_page_scope.text() == "1"
    assert "1 planche" in view.scope_badge.text()

    # Tester changement de portée
    view.input_page_scope.setText("1-2")
    assert "2 planches" in view.scope_badge.text()
    assert editor._album_cards[1].badge.text() == "Portée"
    assert editor._album_cards[2].badge.text() == "Portée"
    assert editor._album_cards[3].badge.text() == "Hors portée"


@pytest.mark.ui
def test_creation_view_multimodal_formats_scope(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'adaptation des unités et titres de portée pour PPTX, EPUB et Audio."""
    uid = uuid.uuid4().hex[:6]
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)

    # 1. PPTX
    pptx_doc = DocumentModel.create(title=f"Diapo {uid}", file_type="pptx", total_pages=5, content="Contenu pptx")
    view._update_scope_and_vision_for_doc(pptx_doc)
    assert view.lbl_scope.text() == "PORTÉE DU DIAPORAMA"
    assert "diapos" in view.scope_badge.text()
    assert not view.vision_card.isHidden()

    # 2. EPUB
    epub_doc = DocumentModel.create(title=f"Livre {uid}", file_type="epub", total_pages=4, content="Contenu epub")
    view._update_scope_and_vision_for_doc(epub_doc)
    assert view.lbl_scope.text() == "PORTÉE DU LIVRE"
    assert "chapitres" in view.scope_badge.text()
    assert view.vision_card.isHidden()

    # 3. Audio
    audio_doc = DocumentModel.create(title=f"Podcast {uid}", file_type="audio", total_pages=3, content="Transcription")
    view._update_scope_and_vision_for_doc(audio_doc)
    assert view.lbl_scope.text() == "PORTÉE AUDIO"
    assert "segments" in view.scope_badge.text()
    assert view.vision_card.isHidden()


@pytest.mark.ui
def test_document_editor_modes_and_album_gallery(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le commutateur de vues (Galerie / Texte) et les cartes d'album."""
    uid = uuid.uuid4().hex[:6]
    media = MediaModel.create(
        filename=f"album_{uid}.png",
        original_name=f"orig_{uid}.png",
        checksum=f"chk_{uid}",
        mime_type="image/png",
    )
    doc = DocumentModel.create(title=f"Album Test {uid}", file_type="album", total_pages=2, content="Doc content")
    DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="Texte P1")
    DocumentPageModel.create(document=doc, media=media, page_number=2, ocr_text="Texte P2")

    editor = DocumentEditorWidget(content="Contenu Markdown", source_title="Test Album", doc_model=doc)
    qtbot.addWidget(editor)

    assert editor.album_container is not None
    assert len(editor._album_cards) == 2

    # Commutation de vue : Document / Album vers Markdown
    assert editor.btn_view_pdf.isChecked()
    editor.btn_view_md.click()
    assert editor.btn_view_md.isChecked()
    assert editor.editor_stack.currentWidget() == editor.markdown_viewer

    # Retour à l'aperçu Album
    editor.btn_view_pdf.click()
    assert editor.editor_stack.currentWidget() == editor.album_container


@pytest.mark.ui
def test_creation_view_multimodal_variables_in_generation(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que use_vision, document_id, file_type et scope_pages sont bien transmis à l'état DAG."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Multi {uid}")
    nt = NoteTypeModel.create(
        name=f"Modèle Multi {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style=".card {}",
    )
    pipe = PipelineModel.create(name=f"Pipeline Multi {uid}")
    persona = PersonaModel.create(name=f"Persona Multi {uid}", system_prompt="Test", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_type="LLM_PROMPT", step_order=1)
    LLMConfigModel.create(provider="mock", model_id=f"dummy_{uid}", display_name=f"Mock IA {uid}")

    media = MediaModel.create(
        filename=f"gen_{uid}.png",
        original_name=f"orig_{uid}.png",
        checksum=f"chk_{uid}",
        mime_type="image/png",
    )
    doc = DocumentModel.create(title=f"Album Gen {uid}", file_type="album", total_pages=2, content="Texte P1")
    DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="Texte P1")

    ai_mgr = DummyCreationAIManager()
    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)

    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    view.load_context({"doc_id": doc.id})
    view.vision_cb.setChecked(True)
    view.input_page_scope.setText("1")

    for i in range(view.pipeline_combo.count()):
        if view.pipeline_combo.itemData(i) and getattr(view.pipeline_combo.itemData(i), "id", None) == pipe.id:
            view.pipeline_combo.setCurrentIndex(i)
            break

    for i in range(view.engine_combo.count()):
        data = view.engine_combo.itemData(i)
        if data and getattr(data, "model_id", "") == f"dummy_{uid}":
            view.engine_combo.setCurrentIndex(i)
            break

    # Déclencher la génération
    view._on_generate(text_source="Contenu d'album", source_title=doc.title)

    # Vérifier les variables injectées dans state
    assert view.orchestrator is not None
    state = view.orchestrator.state
    assert state.get_variable("document_id") == doc.id
    assert state.get_variable("file_type") == "album"
    assert state.get_variable("use_vision") is True
    assert state.get_variable("scope_pages") == [1]

    view.thread_pool.waitForDone(2000)
