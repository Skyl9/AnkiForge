"""
Tests d'interface graphique (PySide6 / pytest-qt) pour la personnalisation des drapeaux Anki dans AnkiSyncTab :
- Affichage des 7 drapeaux avec pastilles de couleur
- Détection des modifications en attente via has_pending_changes()
- Sauvegarde et persistance via save_tab()
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ankiforge.services.cards.flag_service import FlagService
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.tabs.anki_sync_tab import AnkiSyncTab

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def clean_flags():
    """Réinitialise les drapeaux avant et après chaque test."""
    FlagService.reset_to_defaults()
    yield
    FlagService.reset_to_defaults()


def test_anki_sync_tab_flags_ui_initialization(qtbot) -> None:
    """AnkiSyncTab initialise les 7 champs de saisie de drapeaux avec leurs pastilles et placeholders."""

    tab = AnkiSyncTab()
    qtbot.addWidget(tab)
    QApplication.processEvents()

    assert hasattr(tab, "flag_inputs")
    assert len(tab.flag_inputs) == 7
    for f_idx in range(1, 8):
        assert f_idx in tab.flag_inputs
        edit = tab.flag_inputs[f_idx]
        default_name = DesignTokens.FLAG_NAMES[f_idx]
        assert edit.placeholderText() == default_name
        # Comme aucune personnalisation n'est sauvée, le texte est vide (placeholder visible)
        assert edit.text() == ""


def test_anki_sync_tab_flags_pending_changes_and_save(qtbot) -> None:
    """La modification d'un libellé déclenche has_pending_changes et save_tab() persiste le choix."""
    FlagService.reset_to_defaults()

    tab = AnkiSyncTab()
    qtbot.addWidget(tab)
    QApplication.processEvents()

    assert not tab.has_pending_changes()

    # Modification du drapeau 1 (Rouge)
    tab.flag_inputs[1].setText("Priorité Haute")
    assert tab.has_pending_changes()

    # Revenir à la valeur initiale vide annule les modifications en attente
    tab.flag_inputs[1].setText("")
    assert not tab.has_pending_changes()

    # Définir deux drapeaux et sauvegarder
    tab.flag_inputs[1].setText("À revoir")
    tab.flag_inputs[7].setText("Culture G")
    assert tab.has_pending_changes()

    tab.save_tab()

    assert FlagService.get_flag_name(1) == "À revoir"
    assert FlagService.get_flag_name(7) == "Culture G"
    assert FlagService.get_flag_name(2) == "Orange"
