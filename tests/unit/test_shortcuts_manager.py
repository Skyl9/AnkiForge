"""Tests unitaires du ShortcutManager (liaison, portées, activation par vue, texte prioritaire)."""

import pytest
from PySide6.QtWidgets import QLineEdit, QWidget

from ankiforge.ui.shortcuts.manager import ShortcutManager, is_text_input_focused
from ankiforge.ui.shortcuts.models import (
    ShortcutCategory,
    ShortcutDefinition,
    ShortcutId,
    ShortcutScope,
)

pytestmark = pytest.mark.ui


def test_manager_binding_and_execution(qtbot) -> None:
    """Vérifie la liaison basique d'un raccourci et son exécution via activation."""
    parent = QWidget()
    qtbot.addWidget(parent)
    manager = ShortcutManager(parent)

    called = False

    def on_save() -> None:
        nonlocal called
        called = True

    shortcuts = manager.bind(parent, {ShortcutId.APP_SAVE: on_save})
    assert len(shortcuts) == 1
    sc = shortcuts[0]
    assert sc.key().toString() == "Ctrl+S"

    # Déclenchement direct du QShortcut
    sc.activated.emit()
    assert called is True


def test_manager_scope_most_specific_wins(qtbot) -> None:
    """À séquence égale, le raccourci de portée la plus spécifique gagne (VUE > APPLICATION)."""
    window = QWidget()
    qtbot.addWidget(window)
    manager = ShortcutManager(window)

    app_called = False
    view_called = False

    def app_handler() -> None:
        nonlocal app_called
        app_called = True

    def view_handler() -> None:
        nonlocal view_called
        view_called = True

    view = QWidget(window)

    # Binding Application
    app_sc = manager.bind(window, {ShortcutId.APP_SAVE: app_handler})[0]

    # Binding Vue (même séquence Ctrl+S, mais portée VUE)
    view_sc = manager.bind(
        view,
        {ShortcutId.APP_SAVE: view_handler},
        scope=ShortcutScope.VUE,
    )[0]

    # Avant activation de la vue : vue_sc doit être inactif, app_sc actif
    assert app_sc.isEnabled() is True
    assert view_sc.isEnabled() is False

    # Activation de la vue : view_sc devient actif, app_sc est désactivé au profit de la portée plus spécifique
    manager.set_active_view(view)
    assert view_sc.isEnabled() is True
    assert app_sc.isEnabled() is False

    # Désactivation de la vue (changement de vue) : app_sc redevient actif
    other_view = QWidget(window)
    manager.set_active_view(other_view)
    assert view_sc.isEnabled() is False
    assert app_sc.isEnabled() is True


def test_manager_hides_inactive_view_shortcuts(qtbot) -> None:
    """Les raccourcis d'une vue cachée dans un QStackedWidget sont désactivés."""
    container = QWidget()
    qtbot.addWidget(container)
    manager = ShortcutManager(container)

    view_a = QWidget()
    view_b = QWidget()

    sc_a = manager.bind(
        view_a,
        {ShortcutId.APP_FIND: lambda: None},
        scope=ShortcutScope.VUE,
    )[0]
    sc_b = manager.bind(
        view_b,
        {ShortcutId.APP_FIND: lambda: None},
        scope=ShortcutScope.VUE,
    )[0]

    manager.set_active_view(view_a)
    assert sc_a.isEnabled() is True
    assert sc_b.isEnabled() is False

    manager.set_active_view(view_b)
    assert sc_a.isEnabled() is False
    assert sc_b.isEnabled() is True


def test_text_input_focused_guard(qtbot) -> None:
    """La règle du texte prioritaire absorbe les touches nues lorsqu'un champ de saisie a le focus."""
    widget = QWidget()
    qtbot.addWidget(widget)
    input_field = QLineEdit(widget)
    with qtbot.waitExposed(widget):
        widget.show()
    widget.activateWindow()
    input_field.setFocus()
    qtbot.waitUntil(lambda: input_field.hasFocus() or is_text_input_focused(), timeout=1000)
    assert is_text_input_focused() is True

    manager = ShortcutManager(widget)
    bare_called = False

    def bare_handler() -> None:
        nonlocal bare_called
        bare_called = True

    # Touche nue autorisée en portée Widget
    bare_definition = ShortcutDefinition(
        id=ShortcutId.VIEW_DELETE,
        category=ShortcutCategory.EDITION,
        scope=ShortcutScope.WIDGET,
        default_sequence="Suppr",
        title_getter=lambda: "Supprimer",
        allow_bare_key=True,
    )

    sc = manager.bind(
        widget,
        {ShortcutId.VIEW_DELETE: bare_handler},
        scope=ShortcutScope.WIDGET,
        custom_definitions={ShortcutId.VIEW_DELETE: bare_definition},
    )[0]

    # Quand le focus est sur le champ texte, le handler ne s'exécute pas
    sc.activated.emit()
    assert bare_called is False

    # Quand le focus n'est plus sur un champ texte, le handler s'exécute
    input_field.clearFocus()
    sc.activated.emit()
    assert bare_called is True
