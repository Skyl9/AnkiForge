"""
Tests unitaires et d'intégration de la persistance de tous les toggles et options IA.
Vérifie le cycle complet de sauvegarde, restauration et prise en compte par le backend
(SettingsService, AIEnginesTab, CreationView, BatchView, WozniakTab, DelimitationDialog, ABTestsView).
"""

from unittest.mock import patch

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    PipelineModel,
    SettingModel,
)
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.views.ab_tests_view.view import ABTestsView
from ankiforge.ui.views.analysis_view.tabs.wozniak_tab import AIWozniakLinterTab
from ankiforge.ui.views.batch_view.view import BatchView
from ankiforge.ui.views.creation_view.view import CreationView
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog
from ankiforge.ui.widgets.settings_modal.tabs.ai_engines_tab import AIEnginesTab
from ankiforge.utils.environment import get_app_qsettings


@pytest.fixture(autouse=True)
def clean_db_and_settings():
    """Prépare un environnement de test propre."""
    SettingModel.delete().execute()
    get_app_qsettings().clear()
    LLMConfigModel.delete().execute()
    PipelineModel.delete().execute()
    CardModel.delete().execute()
    NoteModel.delete().execute()
    NoteTypeModel.delete().execute()
    DeckModel.delete().execute()
    DocumentModel.delete().execute()

    LLMConfigModel.create(
        display_name="Gemini Flash",
        provider="gemini",
        model_id="gemini-3.5-flash-lite",
        max_tokens=65536,
        sort_order=0,
        is_free=True,
    )
    LLMConfigModel.create(
        display_name="GPT-4o",
        provider="openai",
        model_id="gpt-4o",
        max_tokens=16384,
        sort_order=10,
        is_free=False,
    )
    PipelineModel.create(name="Pipeline Alpha", description="Test pipeline")
    PipelineModel.create(name="Pipeline Beta", description="Test pipeline 2")


def test_ai_engines_tab_global_prefs_persistence(qtbot):
    """Vérifie la persistance et la restauration des options IA globales dans AIEnginesTab."""
    tab1 = AIEnginesTab()
    qtbot.addWidget(tab1)
    tab1.refresh_data()

    # Sélection du modèle gpt-4o
    idx_gpt4o = -1
    for i in range(tab1.cb_default_model.count()):
        if tab1.cb_default_model.itemData(i) == "gpt-4o":
            idx_gpt4o = i
            break
    assert idx_gpt4o != -1
    tab1.cb_default_model.setCurrentIndex(idx_gpt4o)

    # Modification des sliders et combos de génération
    tab1.slider_temp.setValue(85)  # 0.85
    assert tab1.lbl_temp_val.text() == "0.85"

    for i in range(tab1.cb_max_tokens.count()):
        if tab1.cb_max_tokens.itemData(i) == 32768:
            tab1.cb_max_tokens.setCurrentIndex(i)
            break

    for i in range(tab1.cb_thinking.count()):
        if tab1.cb_thinking.itemData(i) == 4096:
            tab1.cb_thinking.setCurrentIndex(i)
            break

    # Modification des 4 toggles
    tab1.toggle_streaming.set_checked(False)
    tab1.toggle_vision.set_checked(False)
    tab1.toggle_autoval.set_checked(True)
    tab1.toggle_linter.set_checked(False)

    # Modification des sliders RAG
    tab1.slider_rag_topk.setValue(8)
    assert tab1.lbl_rag_topk_val.text() == "8"
    tab1.slider_rag_sim.setValue(85)
    assert tab1.lbl_rag_sim_val.text() == "85%"

    # Sauvegarde
    tab1.save_tab()

    # Vérification SettingsService
    assert SettingsService.get("ai/default_model_id") == "gpt-4o"
    assert SettingsService.get("ai/temperature") == 0.85
    assert SettingsService.get("ai/max_tokens") == 32768
    assert SettingsService.get("ai/thinking_budget") == 4096
    assert SettingsService.get("ai/streaming") is False
    assert SettingsService.get("ai/vision_enabled") is False
    assert SettingsService.get("ai/auto_validation") is True
    assert SettingsService.get("ai/auto_linter") is False
    assert SettingsService.get("ai/rag_top_k") == 8
    assert SettingsService.get("ai/rag_similarity_threshold") == 0.85

    # Instanciation d'un second onglet et vérification de la restauration
    tab2 = AIEnginesTab()
    qtbot.addWidget(tab2)
    tab2.refresh_data()

    assert tab2.cb_default_model.currentData() == "gpt-4o"
    assert tab2.slider_temp.value() == 85
    assert tab2.lbl_temp_val.text() == "0.85"
    assert tab2.cb_max_tokens.currentData() == 32768
    assert tab2.cb_thinking.currentData() == 4096
    assert tab2.toggle_streaming.is_checked() is False
    assert tab2.toggle_vision.is_checked() is False
    assert tab2.toggle_autoval.is_checked() is True
    assert tab2.toggle_linter.is_checked() is False
    assert tab2.slider_rag_topk.value() == 8
    assert tab2.lbl_rag_topk_val.text() == "8"
    assert tab2.slider_rag_sim.value() == 85
    assert tab2.lbl_rag_sim_val.text() == "85%"


def test_backend_default_model_and_rag_top_k_honor_settings():
    """Vérifie que AIManager et RAGService honorent le modèle par défaut et le top_k configurés."""
    SettingsService.set("ai/default_model_id", "gpt-4o", category="ai")
    SettingsService.set("ai/rag_top_k", 7, category="ai")

    ai_mgr = AIManager()
    ai_mgr.reload_provider()
    # Le modèle actif doit être gpt-4o
    assert ai_mgr.current_model == "gpt-4o"

    rag = RAGService()
    with patch.object(rag.vector_manager, "search", return_value=[]) as mock_search:
        rag.search(1, "test query")
        # top_k doit avoir été pris depuis SettingsService (7)
        assert mock_search.call_args[1]["top_k"] == 7


def test_creation_view_ai_persistence(qtbot):
    """Vérifie la persistance du moteur, pipeline et toggle vision dans CreationView."""
    view = CreationView()
    qtbot.addWidget(view)
    view.refresh_data()

    # Sélection du 2ème moteur et du 2ème pipeline
    if view.engine_combo.count() > 1:
        view.engine_combo.setCurrentIndex(1)
        selected_engine = view.engine_combo.currentData()
        assert SettingsService.get("creation/engine_id") == selected_engine.id

    if view.pipeline_combo.count() > 1:
        view.pipeline_combo.setCurrentIndex(1)
        selected_pipeline = view.pipeline_combo.currentData()
        assert SettingsService.get("creation/pipeline_id") == selected_pipeline.id

    view.vision_cb.setChecked(True)
    assert SettingsService.get("creation/use_vision") is True

    # Rafraîchissement : doit restaurer ces sélections
    view.refresh_data()
    if view.engine_combo.count() > 1:
        assert view.engine_combo.currentData().id == selected_engine.id
    if view.pipeline_combo.count() > 1:
        assert view.pipeline_combo.currentData().id == selected_pipeline.id
    assert view.vision_cb.isChecked() is True


def test_batch_view_ai_persistence(qtbot):
    """Vérifie la persistance des paramètres et toggles IA dans BatchView."""
    view = BatchView()
    qtbot.addWidget(view)
    view.refresh_data()

    if view.engine_combo.count() > 1:
        view.engine_combo.setCurrentIndex(1)
        selected_engine = view.engine_combo.currentData()
        assert SettingsService.get("batch/engine_id") == selected_engine.id

    if view.pipeline_combo.count() > 1:
        view.pipeline_combo.setCurrentIndex(1)
        selected_pipeline = view.pipeline_combo.currentData()
        assert SettingsService.get("batch/pipeline_id") == selected_pipeline.id

    # Toggles
    view.cb_vision.set_checked(False)
    assert SettingsService.get("batch/use_vision") is False

    view.cb_autoval.set_checked(False)
    assert SettingsService.get("batch/auto_validation") is False

    # Sliders
    view.slider_temp.setValue(9)  # 0.9
    assert SettingsService.get("batch/temperature") == 0.9

    view.slider_tokens.setValue(32)  # 32768
    assert SettingsService.get("batch/max_tokens") == 32768


def test_wozniak_delimitation_and_ab_test_persistence(qtbot):
    """Vérifie la persistance pour Cloze (Wozniak), Délimitation et Synchronisation A/B."""
    # 1. WozniakTab
    w_tab = AIWozniakLinterTab()
    qtbot.addWidget(w_tab)
    w_tab.toggle_cloze.setChecked(False)
    assert SettingsService.get("analysis/toggle_cloze") is False

    # 2. DelimitationDialog
    doc = DocumentModel.create(title="Cours Test", content="# Chapitre 1\nContenu", file_type="md")
    dialog = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dialog)
    dialog.chk_revectorize.setChecked(False)
    assert SettingsService.get("documents/revectorize_after_delimitation") is False

    # 3. ABTestsView
    ab_view = ABTestsView()
    qtbot.addWidget(ab_view)
    ab_view.chk_sync_nav.setChecked(False)
    assert SettingsService.get("ab_test/sync_nav") is False
