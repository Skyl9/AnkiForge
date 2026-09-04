"""
Tests d'interface graphique (PySide6 / pytest-qt) pour le gestionnaire d'addons et l'onglet Extensions.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from ankiforge.services.plugins.plugin_manager import PluginManager
from ankiforge.ui.dialogs.addon_manager_dialog import (
    AddonConfigForm,
    AddonDetailWidget,
    AddonManagerWidget,
)
from ankiforge.ui.widgets.settings_modal import SettingsModal


@pytest.fixture
def dummy_plugin_env():
    """Crée un environnement avec un plugin actif et un plugin avec erreur pour tester l'IHM."""
    temp_dir = tempfile.mkdtemp(prefix="ankiforge_ui_plugins_")
    addons_dir = Path(temp_dir)

    # Addon 1 : Valide
    p1 = addons_dir / "tts_plugin"
    p1.mkdir(parents=True)
    m1 = {
        "id": "tts_plugin",
        "name": "TTS Vocalizer",
        "version": "1.0.0",
        "author": "VoiceLab",
        "description": "Génération de voix de synthèse.",
    }
    (p1 / "manifest.json").write_text(json.dumps(m1), encoding="utf-8")
    (p1 / "config.json").write_text(json.dumps({"rate": 150, "enabled": True, "voice": "French_1"}), encoding="utf-8")
    (p1 / "config.md").write_text("# Guide TTS\nOptions de voix.", encoding="utf-8")
    (p1 / "__init__.py").write_text("def init_addon(api): pass", encoding="utf-8")

    # Addon 2 : Erreur
    p2 = addons_dir / "broken_plugin"
    p2.mkdir(parents=True)
    m2 = {
        "id": "broken_plugin",
        "name": "Broken Tool",
        "version": "0.1.0",
        "author": "Tester",
        "description": "Plugin en erreur de syntaxe.",
    }
    (p2 / "manifest.json").write_text(json.dumps(m2), encoding="utf-8")
    (p2 / "__init__.py").write_text("def init_addon(api):\n    raise ValueError('Config manquante')", encoding="utf-8")

    pm = PluginManager(addons_dir=addons_dir)
    pm.load_all_addons(safe_mode=False)

    yield pm

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_addon_config_form(qtbot, dummy_plugin_env):
    """Teste le formulaire dynamique généré pour config.json."""
    addon = dummy_plugin_env.get_addon("tts_plugin")
    assert addon is not None

    form = AddonConfigForm(addon, dummy_plugin_env)
    qtbot.addWidget(form)

    assert "rate" in form._fields
    assert "enabled" in form._fields
    assert "voice" in form._fields

    # Modification d'une valeur et sauvegarde
    saved_events = []
    form.config_saved.connect(lambda cfg: saved_events.append(cfg))
    form._on_save()

    assert len(saved_events) == 1
    assert saved_events[0]["rate"] == 150
    assert saved_events[0]["enabled"] is True


def test_addon_detail_widget(qtbot, dummy_plugin_env):
    """Teste le widget de détail d'un addon (actif vs erreur)."""
    detail = AddonDetailWidget(dummy_plugin_env)
    qtbot.addWidget(detail)

    # 1. État initial vide (content_box cachée)
    assert detail.content_box.isHidden() is True

    # 2. Sélectionner addon valide
    addon_valid = dummy_plugin_env.get_addon("tts_plugin")
    detail.set_addon(addon_valid)

    assert detail.content_box.isHidden() is False
    assert detail.lbl_name.text() == "TTS Vocalizer"
    assert detail.badge_status.text() == "Actif"

    # 3. Sélectionner addon en erreur
    addon_err = dummy_plugin_env.get_addon("broken_plugin")
    detail.set_addon(addon_err)

    assert detail.badge_status.text() == "Erreur"
    assert "ValueError" in detail.error_edit.toPlainText()


def test_addon_manager_widget(qtbot, dummy_plugin_env):
    """Teste la liste des addons, le filtrage et la sélection."""
    widget = AddonManagerWidget(plugin_manager=dummy_plugin_env)
    qtbot.addWidget(widget)

    assert widget.table.rowCount() == 2

    # Filtrage par recherche
    widget.search_input.setText("Vocalizer")
    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 0).text() == "TTS Vocalizer"

    # Réinitialisation filtre
    widget.search_input.setText("")
    assert widget.table.rowCount() == 2

    # Clic sur une ligne
    widget.table.selectRow(0)
    assert widget.detail_widget.current_addon is not None


def test_settings_modal_addons_tab(qtbot, dummy_plugin_env):
    """Vérifie que l'onglet Extensions est bien intégré dans SettingsModal."""
    modal = SettingsModal(ai_manager=None)
    qtbot.addWidget(modal)

    # Vérifier que le stacked widget a 6 onglets (Général, Moteurs IA, Anki, Audio & TTS, Maintenance, Extensions)
    assert modal.stacked_widget.count() == 6
    assert hasattr(modal, "addons_tab")

    # Basculer sur l'onglet Extensions (index 5)
    modal.stacked_widget.setCurrentIndex(5)
    assert modal.stacked_widget.currentIndex() == 5
