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
from ankiforge.ui.views.creation_view.dialogs import CardEditDialog
from ankiforge.ui.views.creation_view.widgets.document_editor import DocumentEditorWidget


class DummyCreationProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json", max_tokens: int | None = None) -> str:
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


@pytest.mark.ui
def test_free_input_remains_editable_for_generation(qtbot: Any, mock_db: Any) -> None:
    """Une saisie libre doit rester éditable et transmettre le texte modifié."""
    editor = DocumentEditorWidget("Texte initial", source_title="Nouvelle Saisie")
    qtbot.addWidget(editor)

    assert editor.editor_stack.currentWidget() is editor.raw_editor
    editor.raw_editor.setPlainText("Texte modifié avant génération")

    emitted: list[tuple[str, str]] = []
    editor.generate_requested.connect(lambda text, title: emitted.append((text, title)))
    editor._on_generate_clicked()

    assert emitted == [("Texte modifié avant génération", "Nouvelle Saisie")]


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


@pytest.mark.ui
def test_creation_view_generation_logs_tab(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la présence et le bon fonctionnement de l'onglet de logs d'exécution."""
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)

    # 1. Vérifier la présence des 3 onglets dans le results_panel
    assert len(view.results_panel.tabs_bar.tabs) == 3
    assert "Cartes Générées" in view.results_panel.tabs_bar.tabs[CreationView.TAB_INDEX_CARDS].text()
    assert "Journal d'Exécution" in view.results_panel.tabs_bar.tabs[CreationView.TAB_INDEX_LOGS].text()
    assert "Journal des Erreurs" in view.results_panel.tabs_bar.tabs[CreationView.TAB_INDEX_ERRORS].text()

    # 2. Vérifier les composants de la console de logs
    assert hasattr(view, "generation_logs_console")
    assert hasattr(view, "cb_autoscroll")
    assert hasattr(view, "btn_copy_logs")
    assert hasattr(view, "btn_clear_logs")
    assert hasattr(view, "btn_copy_errors")
    assert view.cb_autoscroll.isChecked()

    # 3. Tester l'ajout de logs via _append_generation_log
    view._append_generation_log("Test log step", level="STEP")
    assert "▶" in view.generation_logs_console.toPlainText()
    assert "Test log step" in view.generation_logs_console.toPlainText()

    # 4. Tester l'effacement du journal
    view._on_clear_logs()
    assert view.generation_logs_console.toPlainText() == ""

    # 5. Tester l'enregistrement d'erreur
    view._on_generation_error("Erreur critique d'API")
    assert "❌" in view.generation_logs_console.toPlainText()
    assert "Erreur critique d'API" in view.err_lbl.text()
    assert "Journal des Erreurs (1)" in view.results_panel.tabs_bar.tabs[CreationView.TAB_INDEX_ERRORS].text()


@pytest.mark.ui
def test_creation_view_generation_logs_flow(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le cycle de vie complet des logs lors d'une génération asynchrone."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Logs {uid}")
    nt = NoteTypeModel.create(
        name=f"Modèle Logs {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style=".card {}",
    )
    pipe = PipelineModel.create(name=f"Pipeline Logs {uid}")
    persona = PersonaModel.create(name=f"Créateur {uid}", system_prompt="Créer cartes", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_type="LLM_PROMPT", step_order=1)
    LLMConfigModel.create(provider="mock", model_id=f"dummy_{uid}", display_name=f"Mock IA {uid}")

    ai_mgr = DummyCreationAIManager()
    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)

    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    for i in range(view.pipeline_combo.count()):
        if view.pipeline_combo.itemData(i) and getattr(view.pipeline_combo.itemData(i), "id", None) == pipe.id:
            view.pipeline_combo.setCurrentIndex(i)
            break

    for i in range(view.engine_combo.count()):
        data = view.engine_combo.itemData(i)
        if data and getattr(data, "model_id", "") == f"dummy_{uid}":
            view.engine_combo.setCurrentIndex(i)
            break

    # Lancer la génération
    view._on_generate(text_source="Texte pour test logs", source_title="Doc Logs")

    # Immédiatement après lancement, l'onglet actif doit être le Journal d'Exécution
    assert view.results_panel.content_stack.currentIndex() == CreationView.TAB_INDEX_LOGS
    assert view.results_panel.tabs_bar.tabs[CreationView.TAB_INDEX_LOGS].isChecked()
    assert "Démarrage du pipeline" in view.generation_logs_console.toPlainText()

    # Attendre la fin de génération
    qtbot.waitUntil(lambda: view.results_table.rowCount() == 2, timeout=6000)

    # Après complétion réussie avec cartes, l'onglet actif doit être Cartes Générées
    assert view.results_panel.content_stack.currentIndex() == CreationView.TAB_INDEX_CARDS
    assert view.results_panel.tabs_bar.tabs[CreationView.TAB_INDEX_CARDS].isChecked()
    assert "Pipeline terminé avec succès" in view.generation_logs_console.toPlainText()

    view.thread_pool.waitForDone(2000)


@pytest.mark.ui
def test_validate_and_reject_card_feedback(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Vérifie que la validation et le rejet de cartes ne déclenchent pas de toast unitaire

    et mettent à jour le badge d'état in-situ dans FlashcardPreview.
    """
    from ankiforge.ui.widgets.toast import ToastManager

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)

    view.generated_cards = [
        {"Front": "Question 1", "Back": "Réponse 1", "status": "À valider"},
        {"Front": "Question 2", "Back": "Réponse 2", "status": "À valider"},
    ]
    view.current_preview_index = 0
    view._populate_results_table()
    view._update_card_preview()

    # Le badge initial est "À valider ⏳"
    assert "À valider" in view.preview_widget.status_badge.text()

    toasts_emitted: list[str] = []

    def mock_show_toast(parent: Any, msg: str, *args: Any, **kwargs: Any) -> None:
        toasts_emitted.append(msg)

    monkeypatch.setattr("ankiforge.ui.views.creation_view.view.show_toast", mock_show_toast)

    # 1. Validation de la 1ère carte
    view._on_validate_card()

    # Aucun toast unitaire "Carte acceptée !" ne doit être émis
    assert not any("acceptée" in t for t in toasts_emitted)
    assert view.generated_cards[0]["status"] == "Validée"
    # L'index a avancé à 1
    assert view.current_preview_index == 1
    assert "À valider" in view.preview_widget.status_badge.text()

    # Revenir sur la 1ère carte et vérifier son badge
    view.current_preview_index = 0
    view._update_card_preview()
    assert "Validée" in view.preview_widget.status_badge.text()

    # 2. Rejet de la 2ème carte (dernière carte)
    view.current_preview_index = 1
    view._update_card_preview()
    view._on_reject_card()

    # Aucun toast individuel "marquée Refusée"
    assert not any("marquée Refusée" in t for t in toasts_emitted)
    assert view.generated_cards[1]["status"] == "Refusée"
    assert "Refusée" in view.preview_widget.status_badge.text()

    # Mais le toast récapitulatif de fin de revue DOIT être émis
    assert any("Toutes les cartes ont été passées en revue" in t for t in toasts_emitted)

    # 3. Vérifier le plafonnement MAX_ACTIVE_TOASTS = 3 du ToastManager
    tm = ToastManager.get_instance()
    tm.clear()
    assert len(tm._active_toasts) == 0
    for i in range(5):
        tm.show(parent=view, message=f"Toast {i}")
    assert len(tm._active_toasts) <= 3
    tm.clear()


@pytest.mark.ui
def test_card_edit_dialog_dynamic_fields(qtbot: Any) -> None:
    """Vérifie que CardEditDialog génère dynamiquement tous les champs et permet leur édition."""
    card_data = {
        "Mot": "Schadenfreude",
        "Lecture": "ˈʃaːdn̩ˌfʁɔɪ̯də",
        "Sens": "Joie éprouvée face au malheur d'autrui",
        "Exemple": "Er empfand Schadenfreude.",
        "model": "Vocabulaire Allemand",
        "status": "À valider",
    }
    field_names = ["Mot", "Lecture", "Sens", "Exemple"]

    dlg = CardEditDialog(card_data=card_data, field_names=field_names)
    qtbot.addWidget(dlg)

    # Vérifier que tous les champs sont présents
    assert set(dlg.field_edits.keys()) == set(field_names)
    assert dlg.field_edits["Mot"].toPlainText() == "Schadenfreude"
    assert dlg.field_edits["Lecture"].toPlainText() == "ˈʃaːdn̩ˌfʁɔɪ̯də"
    assert dlg.field_edits["Sens"].toPlainText() == "Joie éprouvée face au malheur d'autrui"
    assert dlg.field_edits["Exemple"].toPlainText() == "Er empfand Schadenfreude."

    # Modifier un champ
    dlg.field_edits["Sens"].setPlainText("Plaisir malicieux")

    # Vérifier get_fields()
    updated = dlg.get_fields()
    assert updated["Mot"] == "Schadenfreude"
    assert updated["Sens"] == "Plaisir malicieux"

    # Vérifier get_data() rétrocompatible
    first, second = dlg.get_data()
    assert first == "Schadenfreude"
    assert second == "ˈʃaːdn̩ˌfʁɔɪ̯də"


@pytest.mark.ui
def test_creation_view_dynamic_table_columns_heterogeneous_cards(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que le tableau des résultats adapte ses colonnes à l'union des champs et grise les champs non applicables."""
    from PySide6.QtCore import Qt

    # Créer 2 modèles distincts
    nt_basic = NoteTypeModel.create(
        name="Basique Test",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style=".card {}",
    )
    nt_cloze = NoteTypeModel.create(
        name="Cloze Test",
        fields_schema='["Texte", "Remarques extra"]',
        templates='[{"name": "C1", "qfmt": "{{cloze:Texte}}", "afmt": "{{cloze:Texte}}<br>{{Remarques extra}}"}]',
        css_style=".card {}",
    )

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.models_cache = [nt_basic, nt_cloze]
    view.current_model = nt_basic

    view.generated_cards = [
        {"model": "Basique Test", "Front": "Question 1", "Back": "Réponse 1", "status": "À valider"},
        {"model": "Cloze Test", "Texte": "La capitale est {{c1::Paris}}", "Remarques extra": "France", "status": "À valider"},
    ]
    view._populate_results_table()

    # En-têtes attendus : Modèle + Union ordonnée [Front, Back, Texte, Remarques extra] + Statut
    expected_headers = ["Modèle", "Front", "Back", "Texte", "Remarques extra", "Statut"]
    actual_headers = []
    for i in range(view.results_table.columnCount()):
        header_item = view.results_table.horizontalHeaderItem(i)
        assert header_item is not None
        actual_headers.append(header_item.text())
    assert actual_headers == expected_headers

    # Ligne 0 (Basique Test) : Front et Back remplis, Texte et Remarques extra grisés ("—")
    item_0_1 = view.results_table.item(0, 1)
    item_0_2 = view.results_table.item(0, 2)
    assert item_0_1 is not None and item_0_1.text() == "Question 1"
    assert item_0_2 is not None and item_0_2.text() == "Réponse 1"

    item_texte_row0 = view.results_table.item(0, 3)
    assert item_texte_row0 is not None
    assert item_texte_row0.text() == "—"
    assert not (item_texte_row0.flags() & Qt.ItemFlag.ItemIsEditable)

    item_extra_row0 = view.results_table.item(0, 4)
    assert item_extra_row0 is not None
    assert item_extra_row0.text() == "—"
    assert not (item_extra_row0.flags() & Qt.ItemFlag.ItemIsEditable)

    # Ligne 1 (Cloze Test) : Front et Back grisés ("—"), Texte et Remarques extra remplis
    item_front_row1 = view.results_table.item(1, 1)
    assert item_front_row1 is not None
    assert item_front_row1.text() == "—"
    assert not (item_front_row1.flags() & Qt.ItemFlag.ItemIsEditable)

    item_1_3 = view.results_table.item(1, 3)
    item_1_4 = view.results_table.item(1, 4)
    assert item_1_3 is not None and item_1_3.text() == "La capitale est {{c1::Paris}}"
    assert item_1_4 is not None and item_1_4.text() == "France"

    # Tester l'édition directe en cellule
    item_front_row0 = view.results_table.item(0, 1)
    assert item_front_row0 is not None
    item_front_row0.setText("Question Modifiée Directement")
    # Déclencher _on_cell_edited
    view._on_cell_edited(item_front_row0)
    assert view.generated_cards[0]["Front"] == "Question Modifiée Directement"

    # Tester l'édition directe d'un champ Cloze
    item_texte_row1 = view.results_table.item(1, 3)
    assert item_texte_row1 is not None
    item_texte_row1.setText("Texte Modifié")
    view._on_cell_edited(item_texte_row1)
    assert view.generated_cards[1]["Texte"] == "Texte Modifié"


@pytest.mark.ui
def test_creation_view_on_edit_card_flow(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Vérifie l'ouverture et la prise en compte des modifications via _on_edit_card."""
    from PySide6.QtWidgets import QDialog

    nt_custom = NoteTypeModel.create(
        name="Custom 3 Fields",
        fields_schema='["Concept", "Explication", "Source"]',
        templates='[{"name": "C1", "qfmt": "{{Concept}}", "afmt": "{{Explication}}"}]',
        css_style=".card {}",
    )

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.models_cache = [nt_custom]
    view.current_model = nt_custom

    view.generated_cards = [
        {"model": "Custom 3 Fields", "Concept": "Python", "Explication": "Langage", "Source": "Livre", "status": "À valider"},
    ]
    view.current_preview_index = 0
    view._populate_results_table()

    # Mocker CardEditDialog pour simuler la modification des 3 champs
    def mock_exec(self: Any) -> int:
        self.field_edits["Concept"].setPlainText("Python 3.12")
        self.field_edits["Explication"].setPlainText("Langage typé moderne")
        self.field_edits["Source"].setPlainText("Docs officielles")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CardEditDialog, "exec", mock_exec)

    view._on_edit_card()

    # Vérifier que les 3 champs ont été mis à jour
    assert view.generated_cards[0]["Concept"] == "Python 3.12"
    assert view.generated_cards[0]["Explication"] == "Langage typé moderne"
    assert view.generated_cards[0]["Source"] == "Docs officielles"
    item_res_1 = view.results_table.item(0, 1)
    item_res_2 = view.results_table.item(0, 2)
    item_res_3 = view.results_table.item(0, 3)
    assert item_res_1 is not None and item_res_1.text() == "Python 3.12"
    assert item_res_2 is not None and item_res_2.text() == "Langage typé moderne"
    assert item_res_3 is not None and item_res_3.text() == "Docs officielles"
