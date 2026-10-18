"""Tests headless Qt pour le dialogue de capture de raccourci (ShortcutCaptureDialog).

Vérifie :
- capture par appui réel au clavier (y compris touches mortes),
- affichage et validation en temps réel,
- refus des séquences réservées de la liste noire (bouton Valider désactivé),
- refus des conflits intra-portée (bouton Valider désactivé),
- annulation via Échap,
- réinitialisation au défaut.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from ankiforge.ui.shortcuts import ShortcutId
from ankiforge.ui.widgets.settings_modal.dialogs.shortcut_capture_dialog import (
    ShortcutCaptureDialog,
    key_event_to_sequence_str,
)


def test_key_event_to_sequence_str_various_keys() -> None:
    """Traduction exacte des événements clavier en représentations textuelles AnkiForge."""
    # Modificateurs + Lettre
    ev1 = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier, "k")
    assert key_event_to_sequence_str(ev1) == "Ctrl+K"

    # Multiples modificateurs
    ev2 = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_S,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        "s",
    )
    assert key_event_to_sequence_str(ev2) == "Ctrl+Alt+S"

    # Touche morte accent circonflexe
    ev3 = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Dead_Circumflex, Qt.KeyboardModifier.NoModifier, "^")
    assert key_event_to_sequence_str(ev3) == "^"

    # Touche seule Return
    ev4 = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier, "\r")
    assert key_event_to_sequence_str(ev4) == "Ctrl+Return"


def test_shortcut_capture_dialog_valid_sequence(qtbot) -> None:
    """Capture d'une séquence valide active le bouton Valider et définit captured_sequence."""
    dialog = ShortcutCaptureDialog(ShortcutId.APP_COMMAND_PALETTE, "Ctrl+K")
    qtbot.addWidget(dialog)

    assert dialog.btn_validate.isEnabled() is True
    assert dialog.captured_sequence == "Ctrl+K"

    # Simuler appui sur Ctrl+Alt+P
    qtbot.keyClick(
        dialog,
        Qt.Key.Key_P,
        modifier=Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    QApplication.processEvents()

    assert dialog.captured_sequence == "Ctrl+Alt+P"
    assert dialog.btn_validate.isEnabled() is True
    assert "valide" in dialog.lbl_status.text().lower()


def test_shortcut_capture_dialog_rejects_reserved(qtbot) -> None:
    """Saisie d'une séquence réservée affiche l'erreur et désactive Valider."""
    dialog = ShortcutCaptureDialog(ShortcutId.APP_SAVE, "Ctrl+S")
    qtbot.addWidget(dialog)

    # Simuler Ctrl+C (réservé édition de texte)
    qtbot.keyClick(dialog, Qt.Key.Key_C, modifier=Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    assert dialog.captured_sequence == ""
    assert dialog.btn_validate.isEnabled() is False
    assert "réservée" in dialog.lbl_status.text().lower()


def test_shortcut_capture_dialog_rejects_intra_scope_conflict(qtbot) -> None:
    """Saisie d'un conflit intra-portée affiche l'erreur et désactive Valider."""
    dialog = ShortcutCaptureDialog(ShortcutId.APP_SAVE, "Ctrl+S")
    qtbot.addWidget(dialog)

    # Tenter d'attribuer Ctrl+, (déjà pris par APP_SETTINGS dans la même portée APPLICATION)
    qtbot.keyClick(dialog, Qt.Key.Key_Comma, modifier=Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    assert dialog.captured_sequence == ""
    assert dialog.btn_validate.isEnabled() is False
    assert "conflit" in dialog.lbl_status.text().lower()


def test_shortcut_capture_dialog_reset_to_default(qtbot) -> None:
    """Le bouton 'Défaut' restaure la valeur d'usine du catalogue."""
    dialog = ShortcutCaptureDialog(ShortcutId.APP_COMMAND_PALETTE, "Ctrl+Alt+K")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.btn_reset_default, Qt.MouseButton.LeftButton)
    QApplication.processEvents()

    assert dialog.captured_sequence == "Ctrl+K"
    assert dialog.btn_validate.isEnabled() is True


def test_shortcut_capture_dialog_escape_cancels(qtbot) -> None:
    """L'appui sur Échap annule et rejette le dialogue."""
    dialog = ShortcutCaptureDialog(ShortcutId.APP_COMMAND_PALETTE, "Ctrl+K")
    qtbot.addWidget(dialog)

    with qtbot.waitSignal(dialog.rejected, timeout=1000):
        qtbot.keyClick(dialog, Qt.Key.Key_Escape)
