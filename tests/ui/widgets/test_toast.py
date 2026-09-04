"""
Unit tests for Toast and ToastManager floating notification system.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from ankiforge.ui.widgets.toast import Toast, ToastLevel, ToastManager, show_import_toast, show_toast


@pytest.fixture
def parent_widget(qtbot) -> QWidget:
    """Fixture qui crée un widget parent factice."""
    widget = QWidget()
    widget.resize(800, 600)
    qtbot.addWidget(widget)
    return widget


def test_toast_levels_initialization(parent_widget: QWidget, qtbot) -> None:
    message = "Opération réussie avec succès"
    toast = Toast(message=message, level=ToastLevel.SUCCESS, parent=parent_widget)
    qtbot.addWidget(toast)

    labels = toast.findChildren(QLabel)
    texts = [label.text() for label in labels]
    assert message in texts
    assert toast.level == ToastLevel.SUCCESS
    assert toast.progress_bar.value() == 100


def test_toast_levels_styling(parent_widget: QWidget, qtbot) -> None:
    for level, expected_color in [
        (ToastLevel.SUCCESS, "#10B981"),
        (ToastLevel.INFO, "#3B82F6"),
        (ToastLevel.WARNING, "#F59E0B"),
        (ToastLevel.ERROR, "#EF4444"),
    ]:
        toast = Toast(message=f"Test {level.value}", level=level, parent=parent_widget)
        qtbot.addWidget(toast)
        assert expected_color in toast.card.styleSheet()


def test_toast_manager_stacking_and_reposition(parent_widget: QWidget, qtbot) -> None:
    manager = ToastManager.get_instance()
    manager.clear()

    t1 = manager.show(parent_widget, "Message 1", level=ToastLevel.INFO)
    t2 = manager.show(parent_widget, "Message 2", level=ToastLevel.SUCCESS)
    t3 = manager.show(parent_widget, "Message 3", level=ToastLevel.ERROR)

    qtbot.addWidget(t1)
    qtbot.addWidget(t2)
    qtbot.addWidget(t3)

    assert len(manager._active_toasts) == 3
    # Top toast (t1) should be higher than t2 and t3 (lower y coordinate)
    assert t1.y() < t2.y() < t3.y()

    manager.clear()
    assert len(manager._active_toasts) == 0


def test_helper_show_toast_backward_compatibility(parent_widget: QWidget, qtbot) -> None:
    manager = ToastManager.get_instance()
    manager.clear()

    # Success (default or is_error=False)
    t_success = show_toast(parent_widget, "Sauvegardé !", is_error=False)
    assert t_success is not None
    qtbot.addWidget(t_success)
    assert t_success.level == ToastLevel.SUCCESS

    # Error (is_error=True)
    t_error = show_toast(parent_widget, "Échec !", is_error=True)
    assert t_error is not None
    qtbot.addWidget(t_error)
    assert t_error.level == ToastLevel.ERROR

    # Explicit level
    t_warn = show_toast(parent_widget, "Attention aux doublons", level="warning", title="Alerte")
    assert t_warn is not None
    qtbot.addWidget(t_warn)
    assert t_warn.level == ToastLevel.WARNING

    manager.clear()


def test_show_import_toast_feedback_rich(parent_widget: QWidget, qtbot) -> None:
    """Vérifie le formatage enrichi du feedback d'importation (cartes créées, mises à jour, médias)."""
    manager = ToastManager.get_instance()
    manager.clear()

    summary = {"created": 238, "updated": 4, "merged": 1, "media": 2}
    toast = show_import_toast(parent_widget, summary)
    assert toast is not None
    qtbot.addWidget(toast)

    labels = toast.findChildren(QLabel)
    texts = " ".join([label.text() for label in labels])

    assert "Importation Réussie" in texts
    assert "238 cartes créées" in texts
    assert "4 mises à jour silencieuses" in texts
    assert "1 fusion arbitrée" in texts
    assert "2 médias indexés" in texts
    assert toast.level == ToastLevel.SUCCESS

    manager.clear()


def test_show_import_toast_empty(parent_widget: QWidget, qtbot) -> None:
    """Vérifie le message quand aucun élément n'a été importé."""
    manager = ToastManager.get_instance()
    manager.clear()

    summary = {"created": 0, "updated": 0, "merged": 0, "media": 0}
    toast = show_import_toast(parent_widget, summary)
    assert toast is not None
    qtbot.addWidget(toast)

    labels = toast.findChildren(QLabel)
    texts = " ".join([label.text() for label in labels])

    assert "Importation Terminée" in texts
    assert "Aucune nouvelle carte ni modification détectée" in texts
    assert toast.level == ToastLevel.INFO

    manager.clear()


def test_toast_manager_resolves_dialog_host_window(qtbot) -> None:
    """Vérifie que ToastManager ancre le toast à la fenêtre hôte durable même si parent est une QDialog."""
    from PySide6.QtWidgets import QDialog, QMainWindow

    win = QMainWindow()
    win.show()
    qtbot.addWidget(win)

    dlg = QDialog(parent=win)
    dlg.show()
    qtbot.addWidget(dlg)

    manager = ToastManager.get_instance()
    manager.clear()

    toast = manager.show(dlg, "Toast depuis dialog", level=ToastLevel.SUCCESS)
    assert toast is not None
    qtbot.addWidget(toast)

    assert toast.parent() == win
    manager.clear()
