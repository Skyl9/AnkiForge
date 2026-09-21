import json
import uuid
from typing import Any

import pytest

from ankiforge.database.models import (
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.ui.components import ModalField, StyledTextEdit
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.views.ab_tests_view import ABTestsView
from ankiforge.ui.views.creation_view.widgets.document_editor import DocumentEditorWidget


class DummyABProviderA(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        return json.dumps(
            {
                "cards": [
                    {"Front": "Question Branche A", "Back": "Réponse Branche A"},
                ]
            }
        )


class DummyABProviderB(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        return json.dumps(
            {
                "cards": [
                    {"Front": "Question Branche B", "Back": "Réponse Branche B"},
                ]
            }
        )


class DummyABManager:
    def __init__(self, cfg_a_id: int):
        self.cfg_a_id = cfg_a_id

    def create_provider_from_config(self, config: Any) -> LLMProvider:
        if config and getattr(config, "id", None) == self.cfg_a_id:
            return DummyABProviderA()
        return DummyABProviderB()


class DummySingleABManager:
    def create_provider_from_config(self, config: Any) -> LLMProvider:
        return DummyABProviderA()


@pytest.mark.slow
@pytest.mark.ui
def test_ab_tests_view_engine_comparison(qtbot):
    """Vérifie le test A/B en Mode 0 : Comparer deux Moteurs IA et affichage des résultats."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"NoteType AB {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]',
        css_style=".card { font-family: arial; }",
    )
    deck = DeckModel.create(name=f"Deck AB {uid}")

    persona = PersonaModel.create(name=f"Agent Commun {uid}", system_prompt="Prompt Commun", output_format="json")

    cfg_a = LLMConfigModel.create(provider="mock_a", model_id=f"model_a_{uid}", display_name=f"Model A {uid}")
    cfg_b = LLMConfigModel.create(provider="mock_b", model_id=f"model_b_{uid}", display_name=f"Model B {uid}")

    ai_mgr = DummyABManager(cfg_a_id=cfg_a.id)

    view = ABTestsView(ai_manager=ai_mgr)
    qtbot.addWidget(view)

    view.refresh_data()

    # Mode 0 : Comparer deux moteurs
    view.mode_combo.setCurrentIndex(0)

    view._set_engine("A", cfg_a)
    view._set_engine("B", cfg_b)
    view._set_persona("common", persona)
    view._set_deck(deck)

    # Lancer le test A/B
    view.source_text_edit.setPlainText("Texte d'évaluation comparatif Moteurs A/B.")
    view._on_run_ab_test()

    # Attendre que les deux branches asynchrones terminent
    qtbot.waitUntil(lambda: view.btn_run.isEnabled() is True, timeout=7000)
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)

    assert len(view.cards_a) == 1
    assert view.cards_a[0]["Front"] == "Question Branche A"
    assert len(view.cards_b) == 1
    assert view.cards_b[0]["Front"] == "Question Branche B"

    # Vérification des KPIs affichés
    assert "s" in view.kpi_a.lbl_time.text()
    assert "1 carte" in view.kpi_a.lbl_cards.text()

    # L'exécution bascule automatiquement sur l'écran Résultats
    assert view.phase_stack.currentWidget() is view.results_page

    # Le modèle de carte sélectionné est injecté dans l'état (catalogue restreint + champs)
    nt = view.model_field.get_value()
    assert nt is not None
    assert view.orchestrator_a.state.get_variable("selected_models") == [nt]
    assert view.orchestrator_b.state.get_variable("selected_models") == [nt]
    assert view.orchestrator_a.state.get_variable("note_type") == nt.name
    assert view.orchestrator_a.state.get_variable("target_deck") == deck.name
    assert view.orchestrator_a.state.get_variable("fields") == ["Front", "Back"]
    assert view.orchestrator_a.state.get_variable("fields_str") == '"Front", "Back"'


@pytest.mark.ui
def test_ab_tests_view_prompt_and_pipeline_comparison(qtbot):
    """Vérifie le test A/B en Mode 1 (Prompts) et Mode 2 (Pipelines) ainsi que la navigation synchro."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"NoteType Prompt {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]',
        css_style=".card { font-family: arial; }",
    )

    PersonaModel.create(name=f"Agent Simple {uid}", system_prompt="Prompt Simple", output_format="json")
    PersonaModel.create(name=f"Agent Complexe {uid}", system_prompt="Prompt Complexe", output_format="json")

    PipelineModel.create(name=f"Pipe A {uid}")
    PipelineModel.create(name=f"Pipe B {uid}")

    LLMConfigModel.create(provider="mock", model_id=f"model_{uid}", display_name=f"Model Global {uid}")

    ai_mgr = DummySingleABManager()

    view = ABTestsView(ai_manager=ai_mgr)
    qtbot.addWidget(view)

    view.refresh_data()

    # Mode 1 : Comparer deux prompts
    view.mode_combo.setCurrentIndex(1)
    assert view.lbl_a.text() == "Prompt A :"
    assert view.lbl_b.text() == "Prompt B :"
    assert view.field_a.get_value() is not None  # défaut prompt persisté par branche

    # Mode 2 : Comparer deux pipelines
    view.mode_combo.setCurrentIndex(2)
    assert view.lbl_a.text() == "Pipeline A :"
    assert view.lbl_b.text() == "Pipeline B :"
    assert view.field_b.get_value() is not None  # défaut pipeline persisté par branche

    # Test navigation synchronisée
    view.cards_a = [{"Front": "A1"}, {"Front": "A2"}]
    view.cards_b = [{"Front": "B1"}, {"Front": "B2"}]
    view.index_a = 0
    view.index_b = 0
    view.chk_sync_nav.setChecked(True)

    view._next_a()
    assert view.index_a == 1
    assert view.index_b == 1

    view._prev_a()
    assert view.index_a == 0
    assert view.index_b == 0


@pytest.mark.ui
def test_ab_tests_view_features_and_theme_reactivity(qtbot):
    """Vérifie le commutateur de vue, la disposition splitter, les réglages toujours visibles, le winner badging et la réactivité du thème."""
    view = ABTestsView(ai_manager=None)
    qtbot.addWidget(view)
    view.show()

    # 1. Commutateur de vue
    view._switch_view_mode(1)  # Tableau des Champs
    assert view.stack_a.currentIndex() == 1
    assert view.stack_b.currentIndex() == 1

    view._switch_view_mode(2)  # JSON Brut
    assert view.stack_a.currentIndex() == 2
    assert view.stack_b.currentIndex() == 2

    view._switch_view_mode(0)  # Rendu Visuel
    assert view.stack_a.currentIndex() == 0
    assert view.stack_b.currentIndex() == 0

    # 2. Disposition splitter source | paramètres (l'espace est désormais occupé)
    assert hasattr(view, "config_splitter")
    assert hasattr(view, "config_panel")
    assert isinstance(view.source_text_edit, StyledTextEdit)
    assert isinstance(view.source_editor, DocumentEditorWidget)  # composant réutilisé de la vue Création
    assert not view.source_editor.btn_generate.isVisibleTo(view.source_editor)  # pas de "Générer" ici
    assert view.source_editor.minimumHeight() == 260
    assert view.source_editor.sizePolicy().horizontalPolicy() == view.source_editor.sizePolicy().Policy.Expanding
    assert view.doc_picker.minimumHeight() > 30  # plus d'écrasement du bouton document
    assert not hasattr(view, "btn_samples")  # exemples sources supprimés
    assert not hasattr(view, "config_bar_widget")
    assert not hasattr(view, "adv_drawer")
    assert not hasattr(view, "btn_toggle_source")
    assert not hasattr(view, "btn_adv_toggle")

    # 3. Branches à comparer sur l'écran Configuration (champs modaux cliquables)
    assert view.field_a.parent() is view.branches_block
    assert view.field_b.parent() is view.branches_block
    assert isinstance(view.deck_field, ModalField)
    assert isinstance(view.model_field, ModalField)
    assert hasattr(view, "lbl_branch_a")  # label lecture seule sur l'écran Résultats
    assert hasattr(view, "lbl_branch_b")

    # 3. Réglages Inférence toujours visibles : 1 barre globale OU 2 barres A/B, jamais les trois
    assert not view.global_adv_widget.isHidden()
    assert not view.chk_independent.isHidden()
    assert view.adv_branch_a_widget.isHidden()  # réglages indépendants A/B off par défaut
    assert view.adv_branch_b_widget.isHidden()
    view.chk_independent.setChecked(True)
    assert view.global_adv_widget.isHidden()
    assert not view.adv_branch_a_widget.isHidden()
    assert not view.adv_branch_b_widget.isHidden()
    view.chk_independent.setChecked(False)
    assert not view.global_adv_widget.isHidden()
    assert view.adv_branch_a_widget.isHidden()
    assert view.adv_branch_b_widget.isHidden()

    # 4. État initial idle des KPI : aucune métrique trompeuse (spéc #3)
    assert view.kpi_a.lbl_time.text() == "—"
    assert view.kpi_a.lbl_cards.text() == "—"
    assert view.kpi_b.lbl_time.text() == "—"
    assert view.kpi_b.lbl_cards.text() == "—"
    assert "Prêt" in view.kpi_a.lbl_status.text()

    # Aucun mécanisme de gagnant : badge et boutons supprimés (décision "tout retirer")
    assert not hasattr(view, "btn_adopt_winner")
    assert not hasattr(view.kpi_a, "badge_winner")
    assert not hasattr(view, "_evaluate_winner")

    # Aucun import de cartes depuis le Laboratoire A/B (progressive disclosure '2 écrans')
    assert not hasattr(view, "btn_import_a")
    assert not hasattr(view, "btn_import_b")
    assert not hasattr(view, "chk_import_current_a")
    assert not hasattr(view, "chk_import_current_b")
    assert not hasattr(view, "_on_import_branch_to_forge")
    assert not hasattr(view, "btn_flip_both")

    # 5. Progressive disclosure : 2 écrans (Configuration → Résultats)
    assert view.phase_stack.currentWidget() is view.config_page
    assert hasattr(view, "config_summary_bar")
    assert hasattr(view, "btn_back")
    assert view.btn_back.parent() is view.config_summary_bar
    assert view.config_summary_bar.minimumHeight() == 40  # 2 lignes + hauteur auto, plus de fixed 44px
    view._show_results_page()
    assert view.phase_stack.currentWidget() is view.results_page
    view._show_config_page()
    assert view.phase_stack.currentWidget() is view.config_page

    # Rendre les aperçus visibles pour tester l'état des flips
    view._show_results_page()
    view.results_page.show()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()

    # 6. Flip par panneau (visible seulement en Rendu Visuel) & Device mode
    view._switch_view_mode(1)  # Tableau : flips masqués
    assert not view.btn_flip_a.isVisibleTo(view)
    assert not view.btn_flip_b.isVisibleTo(view)

    view._switch_view_mode(0)  # Rendu Visuel : flips visibles
    assert view.btn_flip_a.isVisibleTo(view)
    assert view.btn_flip_b.isVisibleTo(view)

    assert view.preview_a.is_recto is True
    view.btn_flip_a.click()
    assert view.preview_a.is_recto is False
    view.btn_flip_a.click()
    assert view.preview_a.is_recto is True

    view.btn_flip_b.click()
    assert view.preview_b.is_recto is False
    view._set_both_device_mode("mobile")
    assert view.preview_a._device_mode == "mobile"
    assert view.preview_b._device_mode == "mobile"

    # 7. Theme reactivity
    engine = get_style_engine()
    light_profile = engine.get_theme("jetbrains_light")
    if light_profile:
        view.refresh_theme(light_profile)


@pytest.mark.ui
def test_ab_tests_view_inference_sliders_independent(qtbot):
    """Vérifie la persistance des sliders d'inférence et le calcul température/tokens par branche."""
    view = ABTestsView(ai_manager=None)
    qtbot.addWidget(view)

    assert view.global_temp_slider.value() == 70
    assert view.global_tok_slider.value() == 4096

    # Mode global : les deux branches héritent du réglage commun
    view.global_temp_slider.setValue(120)
    view.global_tok_slider.setValue(2048)
    assert view._effective_temperature("A") == 1.2
    assert view._effective_temperature("B") == 1.2
    assert view._effective_max_tokens("A") == 2048
    assert view._effective_max_tokens("B") == 2048

    # Mode indépendant : réglages propres à chaque branche
    view.chk_independent.setChecked(True)
    assert not view.adv_branch_a_widget.isHidden()
    view.temp_slider_a.setValue(30)
    view.tok_slider_a.setValue(1024)
    view.temp_slider_b.setValue(180)
    view.tok_slider_b.setValue(512)
    assert view._effective_temperature("A") == 0.3
    assert view._effective_temperature("B") == 1.8
    assert view._effective_max_tokens("A") == 1024
    assert view._effective_max_tokens("B") == 512


@pytest.mark.ui
def test_ab_tests_view_no_winner_or_adopt_mechanism(qtbot):
    """Vérifie que le mécanisme 'gagnant' (badge + Adopter) et la copie config A→B ont été supprimés."""

    view = ABTestsView(ai_manager=None)
    qtbot.addWidget(view)

    # KPIs démarrés en idle : pas d'état vide troublant
    assert view.kpi_a.lbl_time.text() == "—"
    assert view.kpi_b.lbl_time.text() == "—"

    # Plus de badge gagnant : aucune référence au mécanisme
    assert not hasattr(view, "btn_adopt_winner")
    assert not hasattr(view.kpi_a, "badge_winner")
    assert not hasattr(view, "_evaluate_winner")

    # Les deux branches restent indépendantes : résultats A sans impacter B
    view.kpi_a.set_results(elapsed=1.0, cards_count=2, tokens=300, cost_usd=0.001, is_success=True)
    view.kpi_b.set_results(elapsed=3.0, cards_count=2, tokens=350, cost_usd=0.002, is_success=True)
    assert view.kpi_a.lbl_time.text() == "1.00s"
    assert view.kpi_b.lbl_time.text() == "3.00s"


@pytest.mark.ui
def test_ab_tests_view_diff_and_copy_config(qtbot):
    """Vérifie le 4e niveau de vue Diff A↔B et le bouton 'Copier config A→B'."""
    view = ABTestsView(ai_manager=None)
    qtbot.addWidget(view)

    # Diff
    view.cards_a = [{"Front": "Question A", "Back": "Réponse A"}]
    view.cards_b = [{"Front": "Question B modifiée", "Back": "Réponse B"}]
    view.index_a = 0
    view.index_b = 0
    view._update_views()
    html_a = view.diff_a.toHtml()
    assert "Champ" in html_a
    assert "Question" in html_a

    view._switch_view_mode(3)
    assert view.stack_a.currentIndex() == 3
    assert view.stack_b.currentIndex() == 3

    # Copie config A -> B : mécanisme supprimé — chaque branche garde ses réglages indépendants
    assert not hasattr(view, "btn_copy_a_to_b")
    assert not hasattr(view, "_on_copy_config_a_to_b")

    # Indépendance conservée : régler A ne touche pas B
    view.temp_slider_a.setValue(88)
    view.tok_slider_a.setValue(600)
    assert view.temp_slider_b.value() == 70
    assert view.tok_slider_b.value() == 4096
    assert view.temp_slider_b.value() == 70  # inchangé
    assert view.tok_slider_b.value() == 4096


@pytest.mark.ui
def test_ab_tests_view_document_import(qtbot):
    """Vérifie l'import d'un document dans le texte source avec les vues Rendu Stylisé / Source."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Labo {uid}",
        content="# Titre du cours\n\nCeci est un extrait de cours en Markdown pour le laboratoire A/B.",
        file_type="md",
    )

    view = ABTestsView(ai_manager=None)
    qtbot.addWidget(view)

    # Bouton d'exemples supprimé, sélecteur de document conservé
    from ankiforge.ui.components import DocumentPickerButton

    assert not hasattr(view, "btn_samples")
    assert hasattr(view, "doc_picker")
    assert isinstance(view.doc_picker, DocumentPickerButton)

    # L'import d'un document active les vues stylisées du composant
    view._apply_document_to_source(doc)
    assert view.source_editor.doc_model is doc
    assert not view.source_editor.view_toggle_frame.isHidden()
    assert view.source_editor.btn_view_pdf.text() == "Rendu Stylisé"
    assert view.source_editor.btn_view_md.text() == "Source Markdown"
    # Vue "Rendu Stylisé" (markdown) active après l'import
    assert view.source_editor.editor_stack.currentWidget() is view.source_editor.markdown_viewer
    assert view.source_editor.get_text().startswith("# Titre du cours")

    # Bascule vers "Source Markdown" (éditeur brut)
    view.source_editor.btn_view_md.setChecked(True)
    view.source_editor._on_view_toggled("md")
    assert view.source_editor.editor_stack.currentWidget() is view.source_editor.raw_editor

    # Vider le document : retour au mode texte libre
    view._on_document_changed(None)
    assert view.source_editor.doc_model is None
    assert view.source_editor.view_toggle_frame.isHidden()


@pytest.mark.ui
def test_ab_tests_view_trash_clears_source_markdown(qtbot):
    """Vérifie que la poubelle efface le texte source et désélectionne le document (Markdown)."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Clear Md {uid}",
        content="# Chapitre\n\nContenu markdown à effacer.",
        file_type="md",
    )

    view = ABTestsView(ai_manager=None)
    qtbot.addWidget(view)

    view.doc_picker.set_document(doc)
    assert view.source_editor.doc_model.id == doc.id
    assert view.source_editor.get_text().startswith("# Chapitre")
    assert view.doc_picker.get_document().id == doc.id

    view._on_clear_source()

    assert view.doc_picker.get_document() is None
    assert view.doc_picker.title_label.text() == "Sélectionner un cours..."
    assert view.source_editor.doc_model is None
    assert view.source_editor.get_text() == ""
    assert view.source_editor.view_toggle_frame.isHidden()
    assert view.source_editor.editor_stack.currentWidget() is view.source_editor.raw_editor


@pytest.mark.ui
def test_ab_tests_view_trash_clears_source_pdf(qtbot):
    """Vérifie que la poubelle efface un document PDF dont la vue reste présentée."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Clear Pdf {uid}",
        content="Page 1\n<!-- PAGE: 2 -->\nPage 2",
        file_type="pdf",
        total_pages=2,
    )

    view = ABTestsView(ai_manager=None)
    qtbot.addWidget(view)

    view.doc_picker.set_document(doc)
    assert view.source_editor.doc_model.id == doc.id
    assert not view.source_editor.view_toggle_frame.isHidden()

    view._on_clear_source()

    assert view.doc_picker.get_document() is None
    assert view.source_editor.doc_model is None
    assert view.source_editor.get_text() == ""
    assert view.source_editor.view_toggle_frame.isHidden()
    assert view.source_editor.editor_stack.currentWidget() is view.source_editor.raw_editor


@pytest.mark.slow
@pytest.mark.ui
def test_ab_tests_view_config_summary_populated(qtbot):
    """Vérifie que la barre de résumé de configuration est peuplée correctement après un run."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"NoteType Summary {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]',
        css_style=".card { font-family: arial; }",
    )
    deck = DeckModel.create(name=f"Deck Summary {uid}")
    PersonaModel.create(name=f"Agent Summary {uid}", system_prompt="Prompt Summary", output_format="json")
    cfg_a = LLMConfigModel.create(provider="mock_a", model_id=f"model_a_summary_{uid}", display_name="Model Summary A")
    cfg_b = LLMConfigModel.create(provider="mock_b", model_id=f"model_b_summary_{uid}", display_name="Model Summary B")

    ai_mgr = DummyABManager(cfg_a_id=cfg_a.id)

    view = ABTestsView(ai_manager=ai_mgr)
    qtbot.addWidget(view)
    view.refresh_data()

    view.mode_combo.setCurrentIndex(0)
    view._set_engine("A", cfg_a)
    view._set_engine("B", cfg_b)
    view._set_deck(deck)

    view.source_text_edit.setPlainText("Texte de vérification du résumé.")
    view._on_run_ab_test()

    qtbot.waitUntil(lambda: view.btn_run.isEnabled() is True, timeout=7000)
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)

    # La barre de résumé reflète la configuration du run
    assert view.phase_stack.currentWidget() is view.results_page
    assert "Comparer deux Moteurs IA" in view.summary_labels["mode"].text()
    assert deck.name in view.summary_labels["deck"].text()
    assert "Model Summary A" in view.summary_labels["branch_a"].text()
    assert "Model Summary B" in view.summary_labels["branch_b"].text()
    assert "Moteur A" in view.lbl_branch_a.text()
    assert "Model Summary A" in view.lbl_branch_a.text()
    assert "Model Summary B" in view.lbl_branch_b.text()
    assert "0.70" in view.summary_labels["inf_a"].text()
    assert "4096" in view.summary_labels["inf_a"].text()


@pytest.mark.ui
def test_ab_tests_view_selectors_open_modals(qtbot):
    """Vérifie qu'un clic sur chaque champ sélectionnable ouvre la modale correspondante."""
    uid = uuid.uuid4().hex[:6]
    persona = PersonaModel.create(name=f"Agent Modal {uid}", system_prompt="Prompt Modal", output_format="json")
    pipeline = PipelineModel.create(name=f"Pipe Modal {uid}")

    view = ABTestsView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Clic sur chaque champ → la modale dédiée s'ouvre (pattern singleton + raise)
    view.deck_field.clicked.emit()
    assert view._deck_modal is not None
    assert view._deck_modal.isVisible()

    view.model_field.clicked.emit()
    assert view._model_modal is not None
    assert view._model_modal.isVisible()

    view._open_persona_modal("A")
    assert view._persona_modals["A"] is not None
    assert view._persona_modals["A"].isVisible()

    view._open_pipeline_modal("B")
    assert view._pipeline_modals["B"] is not None
    assert view._pipeline_modals["B"].isVisible()

    # Sélection depuis une modale → le champ est mis à jour avec le bon payload
    view._on_persona_selected_from_modal(persona.id, str(persona.name), "A")
    assert view.field_a.get_value() is not None
    assert view.field_a.get_value().id == persona.id

    view._on_pipeline_selected_from_modal(pipeline.id, str(pipeline.name), "B")
    assert view.field_b.get_value() is not None
    assert view.field_b.get_value().id == pipeline.id


class DummyCustomFieldProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        return json.dumps(
            {
                "notes": [
                    {"Question": "Requête Branche A", "Reponse": "Résultat Branche A"},
                ]
            }
        )


class DummyCustomFieldManager:
    def create_provider_from_config(self, config: Any) -> LLMProvider:
        return DummyCustomFieldProvider()


@pytest.mark.slow
@pytest.mark.ui
def test_ab_tests_view_custom_field_note_type_normalized(qtbot):
    """Vérifie que les cartes générées sont normalisées au schéma de champs du modèle de carte sélectionné."""
    uid = uuid.uuid4().hex[:6]
    nt_custom = NoteTypeModel.create(
        name=f"NoteType Custom {uid}",
        fields_schema='["QuestionCustom", "ReponseCustom"]',
        templates='[{"name": "Card 1", "qfmt": "{{QuestionCustom}}", "afmt": "{{FrontSide}}<hr>{{ReponseCustom}}"}]',
        css_style=".card { font-family: arial; }",
    )
    PersonaModel.create(name=f"Agent Custom {uid}", system_prompt="Prompt Custom", output_format="json")
    cfg_a = LLMConfigModel.create(provider="mock_a", model_id=f"model_custom_{uid}", display_name=f"Model Custom A {uid}")
    cfg_b = LLMConfigModel.create(provider="mock_b", model_id=f"model_custom_b_{uid}", display_name=f"Model Custom B {uid}")

    view = ABTestsView(ai_manager=DummyCustomFieldManager())
    qtbot.addWidget(view)
    view.refresh_data()

    view._set_engine("A", cfg_a)
    view._set_engine("B", cfg_b)
    view._set_model(nt_custom)

    view.source_text_edit.setPlainText("Texte d'évaluation des champs personnalisés.")
    view._on_run_ab_test()

    qtbot.waitUntil(lambda: view.btn_run.isEnabled() is True, timeout=7000)
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)

    # Les clés des deux branches correspondent strictement au schéma du modèle de carte
    assert view.cards_a and view.cards_a[0].get("QuestionCustom") == "Requête Branche A"
    assert view.cards_a and view.cards_a[0].get("ReponseCustom") == "Résultat Branche A"
    assert view.cards_b and view.cards_b[0].get("QuestionCustom") == "Requête Branche A"
    assert view.cards_b and view.cards_b[0].get("ReponseCustom") == "Résultat Branche A"
