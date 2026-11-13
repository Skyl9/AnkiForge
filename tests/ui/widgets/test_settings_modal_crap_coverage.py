"""Tests de couverture ciblés pour SettingsModal afin de résorber le risque CRAP."""

from __future__ import annotations

from typing import Any

import pytest

from ankidraft.ui.style_engine import JETBRAINS_DARK
from ankidraft.ui.widgets.settings_modal.modal import SettingsModal

pytestmark = pytest.mark.ui


def test_settings_modal_lazy_tabs_loading(qtbot: Any, mock_db: Any) -> None:
    """Couvre _ensure_tab_loaded (lazy loading) sur SettingsModal (CC=16, anciennement CRAP=272.0)."""
    modal = SettingsModal(parent=None)
    qtbot.addWidget(modal)

    # Vérification que seul l'onglet 0 est chargé initialement
    assert modal._tabs[0] is not None
    assert modal._tabs[1] is None

    # Chargement à la demande des onglets AI, Anki, TTS, Stockage, Support, Clavier, Aide
    ai_tab = modal._ensure_tab_loaded(1)
    assert ai_tab is not None
    assert modal._tabs[1] is ai_tab

    anki_tab = modal._ensure_tab_loaded(2)
    assert anki_tab is not None
    assert modal._tabs[2] is anki_tab

    tts_tab = modal._ensure_tab_loaded(3)
    assert tts_tab is not None
    assert modal._tabs[3] is tts_tab

    storage_tab = modal._ensure_tab_loaded(4)
    assert storage_tab is not None
    assert modal._tabs[4] is storage_tab

    support_tab = modal._ensure_tab_loaded(6)
    assert support_tab is not None
    assert modal._tabs[6] is support_tab

    keyboard_tab = modal._ensure_tab_loaded(7)
    assert keyboard_tab is not None
    assert modal._tabs[7] is keyboard_tab

    help_tab = modal._ensure_tab_loaded(8)
    assert help_tab is not None
    assert modal._tabs[8] is help_tab

    # Accès via properties
    assert modal.ai_tab is ai_tab
    assert modal.anki_tab is anki_tab
    assert modal.tts_tab is tts_tab
    assert modal.maint_tab is storage_tab
    assert modal.support_tab is support_tab
    assert modal.keyboard_tab is keyboard_tab
    assert modal.help_tab is help_tab


def test_settings_modal_save_and_theme_coverage(qtbot: Any, mock_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Couvre _save_all, _tabs_have_changes et refresh_theme (CC=24, anciennement CRAP=600.0)."""
    modal = SettingsModal(parent=None)
    qtbot.addWidget(modal)

    # 1. Aucun changement initial
    assert not modal._tabs_have_changes()
    modal._save_all()
    assert "aucun" in modal.lbl_save_status.text().lower()

    # 2. Rafraîchissement de thème
    modal.refresh_theme(JETBRAINS_DARK)

    # 3. Navigation par select_tab
    modal.select_tab(0)
    assert modal.stacked_widget.currentIndex() == 0

    modal.select_tab(1)
    assert modal.stacked_widget.currentIndex() == 1

    # 4. Sauvegarde avec changements simulés (couverture de la branche active de _save_all)
    monkeypatch.setattr(modal.general_tab, "has_pending_changes", lambda: True)
    monkeypatch.setattr(modal.general_tab, "_layout_field_changed", lambda: True)
    monkeypatch.setattr(modal.general_tab, "_theme_field_changed", lambda: False)
    monkeypatch.setattr(modal.general_tab, "_mode_field_changed", lambda: False)
    monkeypatch.setattr(modal.general_tab, "save_tab", lambda: ("default", "ide", "default"))

    from ankidraft.ui.widgets import theme_transition_overlay

    monkeypatch.setattr(
        theme_transition_overlay,
        "show_theme_transition",
        lambda *args, **kwargs: kwargs.get("on_applied", lambda: None)(),
    )

    modal._save_all()
    assert "sauvegardés" in modal.lbl_save_status.text().lower()
