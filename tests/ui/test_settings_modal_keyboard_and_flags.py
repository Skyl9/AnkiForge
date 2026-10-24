"""Tests unitaires et d'interface graphique (PySide6 / pytest-qt) pour la sécurisation du clavier dans SettingsModal.

Conforme à l'ADR 0032 §9 (neutralisation des dialogues et persistance explicite) :
- Neutralisation de la fermeture accidentelle sur Entrée
- Validation par Entrée dans les QLineEdit (dont les champs de drapeaux) avec persistance _save_all() et maintien ouvert
- Raccourci standard Ctrl+S / Cmd+S
- Ordre de tabulation séquentielle entre les drapeaux.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    LLMConfigModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
)
from ankiforge.services.cards.flag_service import FlagService
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.widgets.settings_modal import SettingsModal

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def setup_settings_test_db():
    """Initialise une base propre pour chaque test."""
    LLMConfigModel.delete().execute()
    CardModel.delete().execute()
    NoteVersionMediaModel.delete().execute()
    NoteVersionModel.delete().execute()
    NoteModel.delete().execute()
    NoteTypeModel.delete().execute()
    DeckModel.delete().execute()
    MediaModel.delete().execute()
    FlagService.reset_to_defaults()
    yield
    FlagService.reset_to_defaults()


def test_settings_modal_buttons_autodefault_disabled(qtbot) -> None:
    """Tous les boutons de SettingsModal (fermeture, annuler, navigation) ont autoDefault à False."""
    modal = SettingsModal()
    qtbot.addWidget(modal)
    modal.show()
    QApplication.processEvents()

    assert not modal.btn_cancel.autoDefault()
    assert not modal.btn_close.autoDefault()
    for btn in modal.nav_btns:
        assert not btn.autoDefault()


def test_settings_modal_ctrl_s_shortcut(qtbot) -> None:
    """Le raccourci Ctrl+S / Cmd+S déclenche l'enregistrement général sans fermer la modale."""
    modal = SettingsModal()
    qtbot.addWidget(modal)
    modal.show()
    QApplication.processEvents()

    modal.select_tab(2)
    QApplication.processEvents()

    modal.anki_tab.flag_inputs[1].setText("Drapeau Test CtrlS")
    assert modal.anki_tab.has_pending_changes()

    # Déclencher le raccourci Save (Ctrl+S / Cmd+S)
    qtbot.keyClick(modal, Qt.Key.Key_S, modifier=Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    assert modal.isVisible()
    assert FlagService.get_flag_name(1) == "Drapeau Test CtrlS"


def test_enter_in_flag_input_triggers_save_and_keeps_modal_open(qtbot) -> None:
    """Taper Entrée dans un champ de drapeau sauvegarde immédiatement et garde la modale ouverte."""
    modal = SettingsModal()
    qtbot.addWidget(modal)
    modal.show()
    QApplication.processEvents()

    modal.select_tab(2)
    QApplication.processEvents()

    flag_1_edit = modal.anki_tab.flag_inputs[1]
    flag_1_edit.setFocus()
    flag_1_edit.setText("Urgentissime")
    assert modal.anki_tab.has_pending_changes()

    # Appui sur Entrée dans le champ de drapeau
    qtbot.keyClick(flag_1_edit, Qt.Key.Key_Return)
    QApplication.processEvents()

    # La modale DOIT rester visible et le drapeau DOIT être sauvegardé
    assert modal.isVisible()
    assert FlagService.get_flag_name(1) == "Urgentissime"
    assert not modal.anki_tab.has_pending_changes()


def test_enter_in_generic_lineedit_triggers_save_and_keeps_modal_open(qtbot) -> None:
    """Taper Entrée dans un champ QLineEdit standard sauvegarde et garde la modale ouverte."""
    modal = SettingsModal()
    qtbot.addWidget(modal)
    modal.show()
    QApplication.processEvents()

    modal.select_tab(2)
    QApplication.processEvents()

    dir_edit = modal.anki_tab.le_anki_dir
    dir_edit.setFocus()
    test_dir = "/tmp/test_anki_dir_saved"
    dir_edit.setText(test_dir)
    assert modal.anki_tab.has_pending_changes()

    qtbot.keyClick(dir_edit, Qt.Key.Key_Return)
    QApplication.processEvents()

    assert modal.isVisible()
    assert SettingsService.get("anki/collection_dir") == test_dir


def test_flags_tab_navigation(qtbot) -> None:
    """L'appui sur Tab dans les drapeaux navigue séquentiellement de 1 à 7."""
    modal = SettingsModal()
    qtbot.addWidget(modal)
    modal.show()
    QApplication.processEvents()

    modal.select_tab(2)
    QApplication.processEvents()

    tab = modal.anki_tab
    tab.flag_inputs[1].setFocus()
    assert tab.flag_inputs[1].hasFocus()

    for idx in range(1, 7):
        qtbot.keyClick(tab.flag_inputs[idx], Qt.Key.Key_Tab)
        QApplication.processEvents()
        assert tab.flag_inputs[idx + 1].hasFocus()
