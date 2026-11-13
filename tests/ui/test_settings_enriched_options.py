"""Tests unitaires et headless Qt pour les options métier enrichies du modal de paramètres.

Couvre :
- GeneralTab : section ÉDITEUR & AFFICHAGE DE TEXTE (font_size, line_numbers, word_wrap) + comportement système (QSettings).
- AIEnginesTab : section PARAMÈTRES DE GÉNÉRATION PAR DÉFAUT (default_temperature, max_tokens_budget, request_timeout_sec).
- TTSSettingsTab : persistance de la vitesse par défaut et des voix par langue (tts/default_speed, tts/voice_fr, tts/voice_en).
- Détection des modifications (has_pending_changes) et restauration au rechargement de l'onglet.
"""

import pytest
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox

from ankidraft.services.settings_service import SettingsService
from ankidraft.ui.widgets.settings_modal.tabs.ai_engines_tab import AIEnginesTab
from ankidraft.ui.widgets.settings_modal.tabs.general_tab import GeneralTab
from ankidraft.ui.widgets.settings_modal.tabs.tts_tab import TTSSettingsTab
from ankidraft.utils.environment import get_app_qsettings

pytestmark = pytest.mark.ui


def _set_combo_data(combo, value):
    """Sélectionne l'item d'une QComboBox dont les données (userData) valent `value`."""
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return True
    return False


# ── GeneralTab ──────────────────────────────────────────────────────────────


def test_general_tab_editor_options_persistence(qtbot):
    """Les options de l'éditeur (police, numéros de ligne, retour à la ligne) sont persistées et restaurées."""
    tab1 = GeneralTab()
    qtbot.addWidget(tab1)

    assert tab1.spn_editor_font_size.value() == 13
    assert tab1.chk_editor_line_numbers.isChecked() is True
    assert tab1.chk_editor_word_wrap.isChecked() is True
    assert tab1.has_pending_changes() is False

    tab1.spn_editor_font_size.setValue(16)
    tab1.chk_editor_line_numbers.setChecked(False)
    tab1.chk_editor_word_wrap.setChecked(False)
    assert tab1.has_pending_changes() is True

    tab1.save_tab()

    assert SettingsService.get("editor/font_size") == 16
    assert SettingsService.get("editor/line_numbers") is False
    assert SettingsService.get("editor/word_wrap") is False
    assert tab1.has_pending_changes() is False

    # Restauration dans un nouvel onglet
    tab2 = GeneralTab()
    qtbot.addWidget(tab2)
    assert tab2.spn_editor_font_size.value() == 16
    assert tab2.chk_editor_line_numbers.isChecked() is False
    assert tab2.chk_editor_word_wrap.isChecked() is False


def test_general_tab_behavior_options_qsettings_persistence(qtbot):
    """Les options comportement/confirmation/auto-sauvegarde sont persistées dans QSettings et restaurées."""
    tab1 = GeneralTab()
    qtbot.addWidget(tab1)

    q_settings = get_app_qsettings()
    assert q_settings.value("app/confirm_on_exit", True, type=bool) is True
    assert q_settings.value("app/autosave_interval_sec", 30, type=int) == 30
    assert q_settings.value("app/restore_last_project", True, type=bool) is True
    assert tab1.has_pending_changes() is False

    tab1.chk_confirm_on_exit.setChecked(False)
    tab1.spn_autosave_interval.setValue(120)
    tab1.chk_restore_last_project.setChecked(False)
    assert tab1.has_pending_changes() is True

    tab1.save_tab()

    assert q_settings.value("app/confirm_on_exit", True, type=bool) is False
    assert q_settings.value("app/autosave_interval_sec", 30, type=int) == 120
    assert q_settings.value("app/restore_last_project", True, type=bool) is False
    assert tab1.has_pending_changes() is False

    # Restauration dans un nouvel onglet
    tab2 = GeneralTab()
    qtbot.addWidget(tab2)
    assert tab2.chk_confirm_on_exit.isChecked() is False
    assert tab2.spn_autosave_interval.value() == 120
    assert tab2.chk_restore_last_project.isChecked() is False


# ── AIEnginesTab ────────────────────────────────────────────────────────────


def test_ai_engines_tab_generation_defaults_persistence(qtbot):
    """Les paramètres de génération par défaut (température, tokens, timeout) sont persistés et restaurés."""
    tab1 = AIEnginesTab()
    qtbot.addWidget(tab1)
    tab1.refresh_data()

    assert isinstance(tab1.spn_ai_temperature, QDoubleSpinBox)
    assert isinstance(tab1.spn_ai_max_tokens, QSpinBox)
    assert isinstance(tab1.spn_ai_timeout, QSpinBox)

    assert tab1.spn_ai_temperature.value() == 0.30
    assert tab1.spn_ai_max_tokens.value() == 4000
    assert tab1.spn_ai_timeout.value() == 60
    assert tab1.has_pending_changes() is False

    tab1.spn_ai_temperature.setValue(0.55)
    tab1.spn_ai_max_tokens.setValue(8000)
    tab1.spn_ai_timeout.setValue(150)
    assert tab1.has_pending_changes() is True

    tab1.save_tab()

    assert SettingsService.get("ai/default_temperature") == 0.55
    assert SettingsService.get("ai/max_tokens_budget") == 8000
    assert SettingsService.get("ai/request_timeout_sec") == 150
    assert tab1.has_pending_changes() is False

    # Restauration dans un nouvel onglet
    tab2 = AIEnginesTab()
    qtbot.addWidget(tab2)
    tab2.refresh_data()
    assert tab2.spn_ai_temperature.value() == 0.55
    assert tab2.spn_ai_max_tokens.value() == 8000
    assert tab2.spn_ai_timeout.value() == 150


# ── TTSSettingsTab ──────────────────────────────────────────────────────────


def test_tts_tab_defaults_persistence(qtbot):
    """La vitesse par défaut et les voix par langue sont persistées et restaurées."""
    tab = TTSSettingsTab()
    qtbot.addWidget(tab)
    # Attendre la fin du worker de détection asynchrone (évite les verrous SQLite au teardown).
    if tab._discovery_worker is not None:
        qtbot.waitUntil(tab._discovery_worker.isFinished, timeout=5000)

    assert tab.spn_tts_default_speed.value() == 1.0
    assert _set_combo_data(tab.cb_tts_default_voice_fr, "fr-FR-Standard") or tab.cb_tts_default_voice_fr.currentData() == "fr-FR-Standard"
    assert _set_combo_data(tab.cb_tts_default_voice_en, "en-US-Standard") or tab.cb_tts_default_voice_en.currentData() == "en-US-Standard"
    assert tab.has_pending_changes() is False

    tab.spn_tts_default_speed.setValue(1.35)
    _set_combo_data(tab.cb_tts_default_voice_fr, "fr-CA-Standard")
    _set_combo_data(tab.cb_tts_default_voice_en, "en-GB-Standard")
    assert tab.has_pending_changes() is True

    tab.save_tab()

    assert SettingsService.get("tts/default_speed") == 1.35
    assert SettingsService.get("tts/voice_fr") == "fr-CA-Standard"
    assert SettingsService.get("tts/voice_en") == "en-GB-Standard"
    assert tab.has_pending_changes() is False

    # Restauration dans un nouvel onglet
    tab2 = TTSSettingsTab()
    qtbot.addWidget(tab2)
    if tab2._discovery_worker is not None:
        qtbot.waitUntil(tab2._discovery_worker.isFinished, timeout=5000)
    assert tab2.spn_tts_default_speed.value() == 1.35
    assert tab2.cb_tts_default_voice_fr.currentData() == "fr-CA-Standard"
    assert tab2.cb_tts_default_voice_en.currentData() == "en-GB-Standard"


# ── Spinbox bornes ──────────────────────────────────────────────────────────


def test_general_tab_editor_font_size_bounds(qtbot):
    """La taille de police de l'éditeur est bornée entre 9 et 28 pt."""
    tab = GeneralTab()
    qtbot.addWidget(tab)
    spin: QSpinBox = tab.spn_editor_font_size
    assert spin.minimum() == 9
    assert spin.maximum() == 28


def test_ai_engines_tab_generation_defaults_bounds(qtbot):
    """Les paramètres de génération par défaut respectent leurs bornes."""
    tab = AIEnginesTab()
    qtbot.addWidget(tab)
    tab.refresh_data()

    assert tab.spn_ai_temperature.minimum() == 0.0
    assert tab.spn_ai_temperature.maximum() == 1.0
    assert tab.spn_ai_temperature.singleStep() == 0.05

    assert tab.spn_ai_max_tokens.minimum() == 500
    assert tab.spn_ai_max_tokens.maximum() == 32000
    assert tab.spn_ai_max_tokens.singleStep() == 500

    assert tab.spn_ai_timeout.minimum() == 10
    assert tab.spn_ai_timeout.maximum() == 300


def test_tts_tab_speed_bounds(qtbot):
    """La vitesse par défaut TTS est bornée entre 0.5x et 2.0x avec un pas de 0.05."""
    tab = TTSSettingsTab()
    qtbot.addWidget(tab)
    if tab._discovery_worker is not None:
        qtbot.waitUntil(tab._discovery_worker.isFinished, timeout=5000)

    spin: QDoubleSpinBox = tab.spn_tts_default_speed
    assert spin.minimum() == 0.5
    assert spin.maximum() == 2.0
    assert spin.singleStep() == 0.05
