"""Tests de non-régression pour les dialogues et l'absence totale d'annonces orphelines (T6).

Conforme à l'ADR 0032 et au ticket T6 :
- Zéro QShortcut hors du module src/ankiforge/ui/shortcuts/
- Enregistrement au catalogue du jeu minimal des dialogues (Échap, Entrée, Ctrl+N, Ctrl+Entrée, ↑/↓)
- Câblage de l'éditeur de code (Ctrl+Alt+L) et libération de Ctrl+Shift+I
- Tests headless : navigation, validation, fermeture et création de paquet au clavier
"""

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog

from ankiforge.database.models import DeckModel
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.dialogs.selection_dialog import MultiSelectionDialog, SelectionDialog
from ankiforge.ui.shortcuts import (
    ShortcutId,
    ShortcutScope,
    get_shortcut_catalog,
)
from ankiforge.ui.views.creation_view.dialogs.card_edit_dialog import CardEditDialog
from ankiforge.ui.widgets.settings_modal.modal import SettingsModal

pytestmark = [pytest.mark.ui]


def test_zero_orphan_qshortcuts_in_src() -> None:
    """Garde-fou statique : aucun QShortcut ne doit être importé ou instancié hors de src/ankiforge/ui/shortcuts/."""
    src_dir = Path("src/ankiforge")
    shortcuts_dir = src_dir / "ui" / "shortcuts"

    violating_files: list[str] = []

    for py_file in src_dir.rglob("*.py"):
        if shortcuts_dir in py_file.parents or py_file.parent == shortcuts_dir:
            continue

        content = py_file.read_text(encoding="utf-8")
        if "QShortcut" in content:
            # Vérifier si c'est une vraie utilisation via AST
            try:
                tree = ast.parse(content, filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            if alias.name == "QShortcut":
                                violating_files.append(f"{py_file}:{node.lineno} (import QShortcut)")
                    elif isinstance(node, ast.Name) and node.id == "QShortcut":
                        violating_files.append(f"{py_file}:{node.lineno} (usage QShortcut)")
            except SyntaxError:
                violating_files.append(f"{py_file} (erreur syntaxe)")

    assert not violating_files, "Des instances ou imports de QShortcut hors du module shortcuts ont été détectés :\n" + "\n".join(violating_files)


def test_dialog_shortcuts_registered_in_catalog() -> None:
    """Vérifie l'inscription au registre déclaratif du jeu minimal des dialogues."""
    catalog = get_shortcut_catalog()

    # Contrôle de présence des ShortcutId
    assert ShortcutId.DIALOG_CLOSE in catalog
    assert ShortcutId.DIALOG_CONFIRM in catalog
    assert ShortcutId.DIALOG_APPLY in catalog
    assert ShortcutId.DIALOG_NEW_DECK in catalog
    assert ShortcutId.DIALOG_PREV_ITEM in catalog
    assert ShortcutId.DIALOG_NEXT_ITEM in catalog
    assert ShortcutId.EDITION_FORMAT_CODE in catalog
    assert ShortcutId.CODE_FORMAT in catalog

    # Vérification des portées et séquences
    assert catalog[ShortcutId.DIALOG_CLOSE].scope == ShortcutScope.DIALOGUE
    assert catalog[ShortcutId.DIALOG_CLOSE].default_sequence == "Escape"

    assert catalog[ShortcutId.DIALOG_CONFIRM].scope == ShortcutScope.DIALOGUE
    assert catalog[ShortcutId.DIALOG_CONFIRM].default_sequence == "Return"

    assert catalog[ShortcutId.DIALOG_APPLY].scope == ShortcutScope.DIALOGUE
    assert catalog[ShortcutId.DIALOG_APPLY].default_sequence == "Ctrl+Return"

    assert catalog[ShortcutId.DIALOG_NEW_DECK].scope == ShortcutScope.DIALOGUE
    assert catalog[ShortcutId.DIALOG_NEW_DECK].default_sequence == "Ctrl+N"

    assert catalog[ShortcutId.DIALOG_PREV_ITEM].scope == ShortcutScope.WIDGET
    assert catalog[ShortcutId.DIALOG_PREV_ITEM].default_sequence == "Up"
    assert catalog[ShortcutId.DIALOG_PREV_ITEM].allow_bare_key is True

    assert catalog[ShortcutId.DIALOG_NEXT_ITEM].scope == ShortcutScope.WIDGET
    assert catalog[ShortcutId.DIALOG_NEXT_ITEM].default_sequence == "Down"
    assert catalog[ShortcutId.DIALOG_NEXT_ITEM].allow_bare_key is True

    assert catalog[ShortcutId.EDITION_FORMAT_CODE].default_sequence == "Ctrl+K"
    assert catalog[ShortcutId.CODE_FORMAT].default_sequence == "Ctrl+Alt+L"


def test_selection_dialog_navigation_and_validation(qtbot) -> None:
    """Vérifie la navigation (↑/↓) depuis le champ de recherche et la validation/fermeture au clavier."""
    items = ["Alpha", "Beta", "Gamma"]
    dlg = SelectionDialog(
        title="Test Sélecteur",
        items=items,
        display_func=lambda x: str(x),
    )
    qtbot.addWidget(dlg)
    dlg.show()

    # Au départ, aucun élément n'est sélectionné
    assert dlg.get_selected_item() is None

    # Simuler Flèche Bas depuis le champ de recherche -> sélectionne le 1er élément
    qtbot.keyPress(dlg.search_input, Qt.Key.Key_Down)
    assert dlg.list_widget.currentRow() == 0
    assert dlg.get_selected_item() == "Alpha"

    # Simuler Flèche Bas -> passe au 2e
    qtbot.keyPress(dlg.search_input, Qt.Key.Key_Down)
    assert dlg.list_widget.currentRow() == 1
    assert dlg.get_selected_item() == "Beta"

    # Simuler Flèche Haut -> revient au 1er
    qtbot.keyPress(dlg.search_input, Qt.Key.Key_Up)
    assert dlg.list_widget.currentRow() == 0
    assert dlg.get_selected_item() == "Alpha"

    # Validation avec Entrée depuis le champ de recherche
    with qtbot.waitSignal(dlg.accepted, timeout=1000):
        qtbot.keyPress(dlg.search_input, Qt.Key.Key_Return)

    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.get_selected_item() == "Alpha"


def test_selection_dialog_escape_closes(qtbot) -> None:
    """Vérifie que la touche Échap ferme le dialogue sans valider."""
    dlg = SelectionDialog(
        title="Test Échap",
        items=["Item 1", "Item 2"],
        display_func=str,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    with qtbot.waitSignal(dlg.rejected, timeout=1000):
        qtbot.keyPress(dlg, Qt.Key.Key_Escape)

    assert dlg.result() == QDialog.DialogCode.Rejected
    assert dlg.get_selected_item() is None


def test_multi_selection_dialog_navigation_and_toggle(qtbot) -> None:
    """Vérifie la navigation et la sélection par case à cocher dans MultiSelectionDialog."""
    items = ["Modèle 1", "Modèle 2", "Modèle 3"]
    dlg = MultiSelectionDialog(
        title="Test Multi-Sélecteur",
        items=items,
        display_func=str,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    # Flèche Bas depuis la barre de recherche sélectionne la première ligne
    qtbot.keyPress(dlg.search_input, Qt.Key.Key_Down)
    assert dlg.list_widget.currentRow() == 0

    # Barre d'espace bascule l'état coché
    qtbot.keyPress(dlg.search_input, Qt.Key.Key_Space)
    assert "Modèle 1" in dlg.get_selected_items()

    # Validation avec Entrée
    with qtbot.waitSignal(dlg.accepted, timeout=1000):
        qtbot.keyPress(dlg.search_input, Qt.Key.Key_Return)

    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.get_selected_items() == ["Modèle 1"]


def test_deck_select_window_ctrl_n_creates_deck(qtbot, mock_db) -> None:
    """Vérifie que Ctrl+N dans DeckSelectWindow ouvre CreateDeckDialog."""
    DeckModel.create(name="Default", external_id=1)

    win = DeckSelectWindow(title="Sélection de paquet", allow_all=False)
    qtbot.addWidget(win)
    win.show()

    with patch.object(win, "_open_create_deck_dialog") as mock_create:
        qtbot.keyPress(win, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        assert mock_create.called, "Ctrl+N doit appeler _open_create_deck_dialog dans DeckSelectWindow"

    # Vérification que Échap ferme la fenêtre
    qtbot.keyPress(win, Qt.Key.Key_Escape)
    assert not win.isVisible()


def test_card_edit_dialog_shortcuts_via_manager(qtbot) -> None:
    """Vérifie que CardEditDialog utilise ShortcutManager et lie les actions sans QShortcut orphelin."""
    dlg = CardEditDialog(
        front="Question test",
        back="Réponse test",
    )
    qtbot.addWidget(dlg)
    dlg.show()

    # Vérification : ShortcutManager présent et aucun QShortcut enfant orphelin
    assert hasattr(dlg, "_shortcut_manager")
    from PySide6.QtGui import QShortcut

    children_shortcuts = dlg.findChildren(QShortcut)
    manager_shortcuts = [rec.shortcut for rec in dlg._shortcut_manager._bindings]
    for sc in children_shortcuts:
        assert sc in manager_shortcuts, f"QShortcut orphelin détecté dans CardEditDialog: {sc}"

    # Vérification du déclenchement de la sauvegarde Ctrl+Return
    save_rec = next(r for r in dlg._shortcut_manager._bindings if r.id == ShortcutId.DIALOG_APPLY)
    assert save_rec.sequence == "Ctrl+Return"
    with qtbot.waitSignal(dlg.accepted, timeout=1000):
        save_rec.shortcut.activated.emit()


def test_settings_modal_shortcuts_via_manager(qtbot) -> None:
    """Vérifie que SettingsModal ne possède aucun QShortcut orphelin et traite Ctrl+S / Échap."""
    from unittest.mock import patch

    from PySide6.QtGui import QKeyEvent, QShortcut

    modal = SettingsModal()
    qtbot.addWidget(modal)
    modal.show()

    # Zéro QShortcut orphelin dans SettingsModal
    children_shortcuts = modal.findChildren(QShortcut)
    assert len(children_shortcuts) == 0, f"QShortcut orphelin détecté dans SettingsModal: {children_shortcuts}"

    # Vérification que Ctrl+S déclenche _save_all
    with patch.object(modal, "_save_all") as mock_save:
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
        modal.keyPressEvent(event)
        mock_save.assert_called_once()

    # Vérification que Échap ferme le dialogue
    with patch.object(modal, "close") as mock_close:
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        modal.keyPressEvent(event)
        mock_close.assert_called_once()


def test_model_select_window_keyboard_navigation(qtbot, mock_db) -> None:
    """Vérifie la navigation et fermeture au clavier dans ModelSelectWindow."""
    from ankiforge.database.models import NoteTypeModel
    from ankiforge.ui.components.model_select_window import ModelSelectWindow

    NoteTypeModel.create(name="Modèle Test", fields_schema='["Front", "Back"]')

    win = ModelSelectWindow(title="Sélection de modèle", allow_all=False)
    qtbot.addWidget(win)
    win.show()

    # Flèche Bas dans search_input sélectionne un modèle
    qtbot.keyPress(win.search_input, Qt.Key.Key_Down)
    assert win.tree.currentItem() is not None

    # Échap ferme la fenêtre
    qtbot.keyPress(win, Qt.Key.Key_Escape)
    assert not win.isVisible()
