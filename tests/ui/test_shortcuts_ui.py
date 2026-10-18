"""Tests d'interface headless Qt des raccourcis clavier AnkiForge (ADR 0032).

Couvre :
- Fenêtre minimale à deux vues (routage, vue cachée inactive, cleanup_qt_widgets).
- Câblage de MainWindow : ouverture palette (Ctrl+K), paramètres (Ctrl+,),
  navigation (Alt+1..9, Ctrl+Tab / Ctrl+Shift+Tab), routeurs uniques (Ctrl+S, Ctrl+Entrée).
"""

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.shortcuts import ShortcutId, ShortcutManager, ShortcutScope

pytestmark = pytest.mark.ui


class SampleView(QWidget):
    """Vue de test minimale avec action locale."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = name
        self.save_called = False
        self.primary_called = False
        self.local_called = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Vue {name}", self))

    def save(self) -> None:
        self.save_called = True

    def _on_generate_clicked(self) -> None:
        self.primary_called = True

    def trigger_local_action(self) -> None:
        self.local_called = True


def test_two_views_routing_and_inactive_hidden_view(qtbot) -> None:
    """Vérifie le routage et la stricte désactivation des raccourcis de la vue cachée."""
    window = QWidget()
    qtbot.addWidget(window)

    layout = QVBoxLayout(window)
    stacked = QStackedWidget(window)
    layout.addWidget(stacked)

    view1 = SampleView("1", stacked)
    view2 = SampleView("2", stacked)
    stacked.addWidget(view1)
    stacked.addWidget(view2)

    manager = ShortcutManager(window)

    # 1. Raccourci global de portée APPLICATION : Ctrl+S
    def router_save() -> None:
        active = stacked.currentWidget()
        if isinstance(active, SampleView):
            active.save()

    manager.bind(window, {ShortcutId.APP_SAVE: router_save}, scope=ShortcutScope.APPLICATION)

    # 2. Raccourcis locaux de portée VUE : même ShortcutId (APP_FIND / Ctrl+F) mais handlers distincts
    manager.bind(view1, {ShortcutId.APP_FIND: view1.trigger_local_action}, scope=ShortcutScope.VUE)
    manager.bind(view2, {ShortcutId.APP_FIND: view2.trigger_local_action}, scope=ShortcutScope.VUE)

    # Configuration initiale : Vue 1 active
    stacked.setCurrentWidget(view1)
    manager.set_active_view(view1)

    # Exécution du routeur d'application : doit toucher vue 1 et non vue 2
    router_sc = [rec.shortcut for rec in manager._bindings if rec.id == ShortcutId.APP_SAVE][0]
    router_sc.activated.emit()
    assert view1.save_called is True
    assert view2.save_called is False

    # Déclenchement de Ctrl+F : vue 1 doit réagir, vue 2 doit être inactive
    sc_view1 = [rec.shortcut for rec in manager._bindings if rec.target is view1][0]
    sc_view2 = [rec.shortcut for rec in manager._bindings if rec.target is view2][0]

    assert sc_view1.isEnabled() is True
    assert sc_view2.isEnabled() is False

    sc_view1.activated.emit()
    assert view1.local_called is True
    assert view2.local_called is False

    # Bascule vers Vue 2
    view1.local_called = False
    stacked.setCurrentWidget(view2)
    manager.set_active_view(view2)

    assert sc_view1.isEnabled() is False
    assert sc_view2.isEnabled() is True

    sc_view2.activated.emit()
    assert view1.local_called is False
    assert view2.local_called is True

    # Nouveau déclenchement de sauvegarde : doit maintenant toucher la vue 2
    view1.save_called = False
    router_sc.activated.emit()
    assert view1.save_called is False
    assert view2.save_called is True


def test_main_window_shortcuts_wiring(qtbot, mock_db) -> None:
    """Vérifie que MainWindow initialise le ShortcutManager avec toutes les liaisons requises."""
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)

        assert hasattr(window, "shortcut_manager")
        sm: ShortcutManager = window.shortcut_manager
        assert sm is not None

        # Vérifier que les ShortcutId clés sont bien liés
        bound_ids = {rec.id for rec in sm._bindings}
        assert ShortcutId.APP_COMMAND_PALETTE in bound_ids
        assert ShortcutId.APP_SETTINGS in bound_ids
        assert ShortcutId.APP_SAVE in bound_ids
        assert ShortcutId.APP_RUN_PRIMARY in bound_ids
        assert ShortcutId.APP_FIND in bound_ids
        assert ShortcutId.APP_IMPORT in bound_ids
        assert ShortcutId.APP_EXPORT in bound_ids
        assert ShortcutId.APP_TOUR in bound_ids
        assert ShortcutId.NAV_VIEW_1 in bound_ids
        assert ShortcutId.NAV_VIEW_2 in bound_ids
        assert ShortcutId.NAV_NEXT_VIEW in bound_ids
        assert ShortcutId.NAV_PREV_VIEW in bound_ids

        # Vérifier que l'export n'est plus en collision avec Ctrl+Shift+E
        export_rec = [rec for rec in sm._bindings if rec.id == ShortcutId.APP_EXPORT][0]
        assert export_rec.sequence == "Ctrl+Alt+E"


def test_main_window_palette_and_settings_activation(qtbot, mock_db) -> None:
    """Vérifie l'ouverture de la palette de commandes (Ctrl+K) et des paramètres (Ctrl+,)."""
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)

        # 1. Palette de commandes (Ctrl+K)
        with patch.object(window, "_open_command_palette") as mock_palette:
            palette_sc = [rec.shortcut for rec in window.shortcut_manager._bindings if rec.id == ShortcutId.APP_COMMAND_PALETTE][0]
            palette_sc.activated.emit()
            mock_palette.assert_called_once()

        # 2. Paramètres (Ctrl+,)
        with patch.object(window, "_open_settings_modal") as mock_settings:
            settings_sc = [rec.shortcut for rec in window.shortcut_manager._bindings if rec.id == ShortcutId.APP_SETTINGS][0]
            settings_sc.activated.emit()
            mock_settings.assert_called_once()


def test_main_window_view_navigation_shortcuts(qtbot, mock_db) -> None:
    """Vérifie la navigation par Alt+1..9 et Ctrl+Tab / Ctrl+Shift+Tab."""
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)

        nav_ids = window._get_navigable_view_ids()
        assert len(nav_ids) >= 2

        # Alt+2 doit basculer vers la 2ème vue (Studio de Création)
        alt_2_sc = [rec.shortcut for rec in window.shortcut_manager._bindings if rec.id == ShortcutId.NAV_VIEW_2][0]
        alt_2_sc.activated.emit()
        assert window._current_view_id == nav_ids[1]

        # Alt+1 doit basculer vers la 1ère vue (Tableau de bord)
        alt_1_sc = [rec.shortcut for rec in window.shortcut_manager._bindings if rec.id == ShortcutId.NAV_VIEW_1][0]
        alt_1_sc.activated.emit()
        assert window._current_view_id == nav_ids[0]

        # Ctrl+Tab doit aller à la vue suivante
        next_sc = [rec.shortcut for rec in window.shortcut_manager._bindings if rec.id == ShortcutId.NAV_NEXT_VIEW][0]
        next_sc.activated.emit()
        assert window._current_view_id == nav_ids[1]

        # Ctrl+Shift+Tab doit revenir à la vue précédente
        prev_sc = [rec.shortcut for rec in window.shortcut_manager._bindings if rec.id == ShortcutId.NAV_PREV_VIEW][0]
        prev_sc.activated.emit()
        assert window._current_view_id == nav_ids[0]


def test_palette_and_keyboard_tab_open_shortcuts_doc(qtbot, mock_db) -> None:
    """Vérifie que la palette et l'onglet Clavier renvoient vers la page de référence."""
    from ankiforge.ui.widgets.command_palette import CommandPalette
    from ankiforge.ui.widgets.settings_modal.tabs.keyboard_tab import (
        DOC_SHORTCUTS_URL,
        KeyboardTab,
    )

    # 1. Palette de commandes : présence et déclenchement de shortcuts_doc
    palette = CommandPalette()
    qtbot.addWidget(palette)

    doc_cmds = [cmd for cmd in palette.commands if cmd["id"] == "action.shortcuts_doc"]
    assert len(doc_cmds) == 1, "La commande action.shortcuts_doc doit être enregistrée dans la palette"

    with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open_url, patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)

        # Test de routage MainWindow sur action.shortcuts_doc
        window._on_command_selected("action.shortcuts_doc")
        assert mock_open_url.call_count == 1
        called_url = mock_open_url.call_args[0][0].toString()
        assert called_url == DOC_SHORTCUTS_URL

        # Test de _on_view_selected sur shortcuts_doc
        window._on_view_selected("shortcuts_doc")
        assert mock_open_url.call_count == 2

    # 2. Onglet Clavier : clic sur le bouton Documentation
    tab = KeyboardTab()
    qtbot.addWidget(tab)

    with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open_url:
        tab.btn_doc.click()
        assert mock_open_url.call_count == 1
        called_url = mock_open_url.call_args[0][0].toString()
        assert called_url == DOC_SHORTCUTS_URL
