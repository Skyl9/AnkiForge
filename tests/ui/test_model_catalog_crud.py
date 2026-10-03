"""Tests unitaires et UI pour le CRUD du catalogue de modèles LLM dans SettingsModal."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.model_catalog import ModelCatalog
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components.model_selector.dialog import ModelCardWidget, ModelDiscoveryDialog
from ankiforge.ui.components.model_selector.selector import ModelSelectorWidget
from ankiforge.ui.widgets.settings_modal.dialogs.model_config_dialog import ModelConfigDialog
from ankiforge.ui.widgets.settings_modal.tabs.ai_engines_tab import AIEnginesTab

pytestmark = pytest.mark.ui


@pytest.fixture
def clean_llm_configs():
    """Prépare un jeu de données propre pour tester les moteurs IA."""
    LLMConfigModel.delete().execute()
    cfg1 = LLMConfigModel.create(
        display_name="Gemini Test Flash",
        provider="gemini",
        model_id="gemini-2.5-flash",
        context_limit=1048576,
        max_tokens=65536,
        temperature=0.7,
        supports_vision=True,
        supports_thinking=True,
        supports_json=True,
        is_free=False,
        sort_order=10,
    )
    cfg2 = LLMConfigModel.create(
        display_name="Ollama Local Test",
        provider="ollama",
        model_id="llama3:latest",
        context_limit=131072,
        max_tokens=16384,
        temperature=0.5,
        supports_vision=False,
        supports_thinking=False,
        supports_json=True,
        is_free=True,
        sort_order=20,
    )
    yield cfg1, cfg2
    LLMConfigModel.delete().execute()


def test_model_config_dialog_new_model_creation(qtbot):
    """Vérifie la création d'un nouveau modèle IA avec validation et sauvegarde."""
    dlg = ModelConfigDialog(config=None)
    qtbot.addWidget(dlg)
    dlg.show()

    # 1. Validation : nom ou model_id vide doit afficher une erreur
    dlg.le_display_name.setText("")
    dlg.le_model_id.setText("")
    dlg._on_save()
    assert not dlg.lbl_error.isHidden()
    assert "nom affiché" in dlg.lbl_error.text().lower()

    # Remplir uniquement le nom
    dlg.le_display_name.setText("Mon Modèle Unique")
    dlg._on_save()
    assert not dlg.lbl_error.isHidden()
    assert "identifiant" in dlg.lbl_error.text().lower()

    # 2. Remplir correctement tous les champs
    dlg.le_model_id.setText("mon-modele-v1")
    dlg.spin_context.setValue(65536)
    dlg.spin_max_tokens.setValue(8192)
    dlg.spin_temp.setValue(0.42)
    dlg.chk_vision.setChecked(True)
    dlg.chk_thinking.setChecked(False)
    dlg.chk_free.setChecked(True)
    dlg.le_description.setText("Modèle expérimental interne.")

    dlg._on_save()
    assert dlg.result() == ModelConfigDialog.DialogCode.Accepted
    created = dlg.get_config()
    assert created is not None
    assert created.display_name == "Mon Modèle Unique"
    assert created.model_id == "mon-modele-v1"
    assert created.context_limit == 65536
    assert created.max_tokens == 8192
    assert abs(created.temperature - 0.42) < 0.01
    assert created.supports_vision is True
    assert created.is_free is True
    assert created.description == "Modèle expérimental interne."


def test_model_config_dialog_preset_filling(qtbot):
    """Vérifie le pré-remplissage des champs depuis un modèle officiel du catalogue."""
    dlg = ModelConfigDialog(config=None)
    qtbot.addWidget(dlg)

    spec = ModelCatalog.get_model_spec("gemini", "gemini-2.5-flash")
    assert spec is not None
    dlg._apply_spec(spec)

    assert dlg.le_display_name.text() == spec.display_name
    assert dlg.le_model_id.text() == spec.model_id
    assert dlg.spin_context.value() == spec.context_window
    assert dlg.spin_max_tokens.value() == spec.max_tokens
    assert dlg.chk_vision.isChecked() == spec.supports_vision
    assert dlg.chk_thinking.isChecked() == spec.supports_thinking


def test_model_config_dialog_edit_existing_model(qtbot, clean_llm_configs):
    """Vérifie la modification d'un modèle IA existant."""
    cfg1, _ = clean_llm_configs
    dlg = ModelConfigDialog(config=cfg1)
    qtbot.addWidget(dlg)

    # Vérifier le peuplement initial
    assert dlg.le_display_name.text() == "Gemini Test Flash"
    assert dlg.le_model_id.text() == "gemini-2.5-flash"
    assert dlg.chk_vision.isChecked() is True

    # Modifier plusieurs propriétés
    dlg.le_display_name.setText("Gemini Test Flash Renamed")
    dlg.spin_context.setValue(2000000)
    dlg.spin_max_tokens.setValue(32768)
    dlg.spin_temp.setValue(0.95)
    dlg.chk_vision.setChecked(False)
    dlg.chk_free.setChecked(True)
    dlg.le_description.setText("Description mise à jour")

    dlg._on_save()
    assert dlg.result() == ModelConfigDialog.DialogCode.Accepted

    # Recharger depuis la BDD
    reloaded = LLMConfigModel.get_by_id(cfg1.id)
    assert reloaded.display_name == "Gemini Test Flash Renamed"
    assert reloaded.context_limit == 2000000
    assert reloaded.max_tokens == 32768
    assert abs(reloaded.temperature - 0.95) < 0.01
    assert reloaded.supports_vision is False
    assert reloaded.is_free is True
    assert reloaded.description == "Description mise à jour"


def test_model_discovery_dialog_catalog_crud_buttons(qtbot, clean_llm_configs):
    """Vérifie que les cartes de modèles configurés affichent les boutons Modifier et Supprimer en mode catalogue."""
    dlg = ModelDiscoveryDialog(picker_mode=False)
    qtbot.addWidget(dlg)
    dlg.show()

    # Trouver les cartes installées
    cards = dlg.cards_container.findChildren(ModelCardWidget)
    installed_cards = [c for c in cards if c.is_installed]
    assert len(installed_cards) >= 2

    # Les cartes installées doivent avoir btn_edit et btn_delete
    for card in installed_cards:
        assert hasattr(card, "btn_edit")
        assert hasattr(card, "btn_delete")
        assert card.btn_edit.text() == "Modifier"
        assert card.btn_delete.toolTip() == "Supprimer ce modèle du catalogue"

    # Vérifier la présence du bouton "+ Modèle Personnalisé" dans l'en-tête
    assert hasattr(dlg, "btn_add_custom")
    assert dlg.btn_add_custom.text() == "+ Modèle Personnalisé"


def test_model_discovery_dialog_activate_does_not_close_in_catalog_mode(qtbot, clean_llm_configs):
    """Vérifie que cliquer sur Activer un modèle catalogue l'installe sans fermer la modale d'exploration."""
    dlg = ModelDiscoveryDialog(picker_mode=False)
    qtbot.addWidget(dlg)
    dlg.show()

    initial_installed = LLMConfigModel.select().count()

    # Trouver une carte non installée
    cards = dlg.cards_container.findChildren(ModelCardWidget)
    uninstalled_cards = [c for c in cards if not c.is_installed]
    assert len(uninstalled_cards) > 0

    target_card = uninstalled_cards[0]
    target_card.btn_select.click()

    # En mode catalogue, la boîte de dialogue doit rester ouverte et le modèle être créé
    assert not dlg.isHidden()
    assert LLMConfigModel.select().count() == initial_installed + 1


def test_model_discovery_dialog_delete_model(qtbot, clean_llm_configs):
    """Vérifie la suppression d'un modèle depuis ModelDiscoveryDialog avec confirmation."""
    cfg1, _ = clean_llm_configs
    dlg = ModelDiscoveryDialog(picker_mode=False)
    qtbot.addWidget(dlg)
    dlg.show()

    # Simuler confirmation 'Oui' sur la boîte de dialogue
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        dlg._on_delete_model(cfg1)

    assert not LLMConfigModel.select().where(LLMConfigModel.id == cfg1.id).exists()


def test_ai_engines_tab_crud_workflow(qtbot, clean_llm_configs):
    """Vérifie l'intégration complète du CRUD dans l'onglet AIEnginesTab."""
    cfg1, cfg2 = clean_llm_configs
    tab = AIEnginesTab()
    qtbot.addWidget(tab)

    # 1. Vérifier la présence du bouton Modifier et Supprimer dans la barre d'outils
    assert hasattr(tab, "btn_edit_engine")
    assert tab.btn_edit_engine.text() == "Modifier"
    assert hasattr(tab, "btn_del_engine")

    # 2. Vérifier le menu d'ajout étendu
    actions = [a.text() for a in tab.menu_add.actions()]
    assert "Depuis le catalogue officiel..." in actions
    assert "Modèle personnalisé..." in actions

    # 3. Définir le modèle par défaut sur cfg1
    SettingsService.set("ai/default_model_id", cfg1.model_id, category="ai")
    tab.refresh_data()
    assert tab.cb_default_model.currentData() == cfg1.model_id

    # 4. Supprimer cfg1 avec confirmation=False
    tab._del_engine(engine_id=cfg1.id, confirm=False)
    assert not LLMConfigModel.select().where(LLMConfigModel.id == cfg1.id).exists()

    # Le modèle par défaut doit avoir été réinitialisé
    assert SettingsService.get("ai/default_model_id") == ""

    # 5. Modifier cfg2 via _edit_selected_engine
    with patch.object(ModelConfigDialog, "exec", return_value=1), patch.object(ModelConfigDialog, "get_config", return_value=cfg2):
        tab._edit_selected_engine(engine_id=cfg2.id)

    # La table doit être rafraîchie
    assert tab.table_engines.rowCount() == 1


def test_model_selector_widget_dynamic_refresh_on_crud_event(qtbot, clean_llm_configs):
    """Vérifie que ModelSelectorWidget se rafraîchit automatiquement lors d'un ajout ou suppression de modèle."""
    cfg1, _ = clean_llm_configs
    selector = ModelSelectorWidget(allow_inherit=False)
    qtbot.addWidget(selector)
    selector.show()

    # Initialement 2 modèles configurés
    assert selector.count() == 2
    selector.set_current_model_id(cfg1.id)
    assert selector.get_current_model_id() == cfg1.id

    # 1. Création d'un 3e modèle via ModelConfigDialog
    dlg = ModelConfigDialog(config=None)
    qtbot.addWidget(dlg)
    dlg.le_display_name.setText("Modèle Dynamique Test")
    dlg.le_model_id.setText("dynamique-v1")
    dlg._on_save()

    # Le sélecteur doit s'être mis à jour dynamiquement via l'event bus
    assert selector.count() == 3

    # 2. Suppression du modèle actif cfg1 via AIEnginesTab
    tab = AIEnginesTab()
    qtbot.addWidget(tab)
    tab._del_engine(engine_id=cfg1.id, confirm=False)

    # Le sélecteur doit s'être mis à jour : 2 modèles restants et repli propre
    assert selector.count() == 2
    assert selector.get_current_model_id() != cfg1.id

    selector.close()
