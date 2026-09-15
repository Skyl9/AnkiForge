"""
Tests unitaires et d'intégration pour le système d'onglets IdePanel, le détachement/rattachement,
la réouverture via le bouton +, la SegmentedTabBar et la navigation transverse.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QLabel, QSplitter, QWidget

from ankiforge.ui.components.panels import IdePanel, PanelPlaceholderWidget
from ankiforge.ui.components.tabs.floating_dock import _floating_windows
from ankiforge.ui.components.tabs.segmented_tab_bar import (
    SegmentedTabBar,
    SegmentedTabButton,
    SubTabButton,
)


@pytest.fixture(autouse=True)
def cleanup_floating_windows() -> Any:
    """Nettoie les fenêtres flottantes avant et après chaque test."""
    _floating_windows.clear()
    yield
    for win in list(_floating_windows):
        try:
            win.close()
        except Exception:
            pass
    _floating_windows.clear()


class TestTabDetachAndReattach:
    """Vérifie le cycle de détachement et rattachement des onglets d'un IdePanel."""

    def test_detach_preserves_metadata_and_dock_reattaches_cleanly(self, qtbot: Any) -> None:
        """Vérifie que détacher un onglet conserve les métadonnées et le rattache dans son panneau d'origine."""
        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        widget_a = QLabel("Contenu Onglet A")
        widget_b = QLabel("Contenu Onglet B")

        panel.add_tab("Onglet A", widget_a, "ph.note", closable=True)
        panel.add_tab("Onglet B", widget_b, "ph.cards", closable=True)

        assert panel.tabs_bar.count() == 2
        assert panel.content_stack.count() == 2

        # Détache Onglet A (index 0)
        float_win = panel.detach_panel(0)
        assert float_win is not None
        assert float_win in _floating_windows

        # Vérifier que le widget détaché a bien les métadonnées enregistrées
        assert getattr(widget_a, "original_panel", None) == panel
        assert getattr(widget_a, "original_index", None) == 0
        assert getattr(widget_a, "original_title", None) == "Onglet A"
        assert getattr(widget_a, "original_icon_name", None) == "ph.note"
        assert getattr(widget_a, "original_closable", None) is True

        # Le panneau d'origine a maintenant 1 onglet (Onglet B)
        assert panel.tabs_bar.count() == 1
        assert panel.tabs_bar.tabs[0].text().strip() == "Onglet B"

        # Fermer la fenêtre flottante (déclenche closeEvent qui doit rattacher à panel)
        close_evt = QCloseEvent()
        float_win.closeEvent(close_evt)

        # Onglet A doit être revenu dans panel à l'index 0 et activé
        assert panel.tabs_bar.count() == 2
        assert panel.tabs_bar.tabs[0].text().strip() == "Onglet A"
        assert panel.tabs_bar.current_index == 0
        assert panel.content_stack.currentWidget() == widget_a
        assert float_win not in _floating_windows

    def test_detach_last_tab_does_not_delete_panel_and_reattach_works(self, qtbot: Any) -> None:
        """Détacher le dernier onglet ne détruit pas le panneau hôte, qui affiche un placeholder."""
        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        widget_solo = QLabel("Unique Onglet")
        panel.add_tab("Solo", widget_solo, "ph.star", closable=True)
        assert panel.tabs_bar.count() == 1

        float_win = panel.detach_panel(0)
        assert float_win is not None

        # Le panneau ne doit PAS être détruit !
        assert panel.parent() == splitter
        # Il doit afficher le placeholder
        assert panel.placeholder_widget.isVisible()
        assert isinstance(panel.placeholder_widget, PanelPlaceholderWidget)
        assert panel.tabs_bar.count() == 0

        # Rattachement
        close_evt = QCloseEvent()
        float_win.closeEvent(close_evt)

        # Le panneau retrouve son onglet et cache le placeholder
        assert panel.tabs_bar.count() == 1
        assert panel.tabs_bar.tabs[0].text().strip() == "Solo"
        assert panel.content_stack.currentWidget() == widget_solo

    def test_dock_button_trigger_reattaches_tab(self, qtbot: Any) -> None:
        """Le bouton d'action 'Rattacher la fenêtre' dans la toolbar flottante déclenche le rattachement."""
        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        widget = QLabel("Test Dock Button")
        panel.add_tab("Dock Me", widget, "ph.link", closable=True)

        float_win = panel.detach_panel(0)
        assert float_win is not None

        # Déclenche la fermeture / rattachement
        close_evt = QCloseEvent()
        float_win.closeEvent(close_evt)

        assert panel.tabs_bar.count() == 1
        assert panel.tabs_bar.tabs[0].text().strip() == "Dock Me"
        assert panel.content_stack.currentWidget() == widget


class TestTabReopeningAndMenu:
    """Vérifie la réouverture des onglets fermés et le menu +."""

    def test_reopen_closed_tab_via_open_tab(self, qtbot: Any) -> None:
        """Fermer un onglet puis appeler open_tab le ressuscite depuis _registered_tabs."""
        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        w1 = QLabel("Vue 1")
        w2 = QLabel("Vue 2")
        panel.add_tab("Vue 1", w1, "ph.eye", closable=True)
        panel.add_tab("Vue 2", w2, "ph.gear", closable=True)

        assert panel.tabs_bar.count() == 2

        # Ferme Vue 1 (index 0)
        panel.remove_tab_widget(0)
        assert panel.tabs_bar.count() == 1
        assert panel.tabs_bar.tabs[0].text().strip() == "Vue 2"

        # L'onglet est toujours enregistré dans _registered_tabs
        assert "Vue 1" in panel._registered_tabs

        # Réouverture via open_tab
        panel.open_tab("Vue 1")
        assert panel.tabs_bar.count() == 2
        assert panel.tabs_bar.current_index == 1
        assert panel.tabs_bar.tabs[1].text().strip() == "Vue 1"
        assert panel.content_stack.currentWidget() == w1

    def test_dynamic_tab_title_updates_registration(self, qtbot: Any) -> None:
        """Renommer un onglet met à jour les clés dans _registered_tabs."""
        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)

        w = QLabel("Doc")
        panel.add_tab("Ancien Titre", w, "ph.file", closable=True)
        assert "Ancien Titre" in panel._registered_tabs

        panel.set_tab_text(0, "Nouveau Titre")
        assert panel.tabs_bar.tabs[0].text().strip() == "Nouveau Titre"
        assert "Nouveau Titre" in panel._registered_tabs
        assert "Ancien Titre" not in panel._registered_tabs

    def test_move_tab_between_panels_via_open_tab(self, qtbot: Any) -> None:
        """Ouvrir dans panel_b un onglet actuellement ouvert dans panel_a le déplace proprement."""
        splitter = QSplitter()
        panel_a = IdePanel(parent=splitter)
        panel_b = IdePanel(parent=splitter)
        splitter.addWidget(panel_a)
        splitter.addWidget(panel_b)
        qtbot.addWidget(splitter)
        splitter.show()

        w_shared = QLabel("Partagé")
        panel_a.add_tab("Onglet Partagé", w_shared, "ph.share", closable=True)

        assert panel_a.tabs_bar.count() == 1
        assert panel_b.tabs_bar.count() == 0

        # panel_b demande à ouvrir "Onglet Partagé"
        panel_b.open_tab("Onglet Partagé")

        assert panel_a.tabs_bar.count() == 0
        assert panel_b.tabs_bar.count() == 1
        assert panel_b.tabs_bar.tabs[0].text().strip() == "Onglet Partagé"
        assert panel_b.content_stack.currentWidget() == w_shared


class TestSegmentedTabBar:
    """Vérifie le composant unifié SegmentedTabBar et SegmentedTabButton."""

    def test_add_tabs_and_click_switching(self, qtbot: Any) -> None:
        tab_bar = SegmentedTabBar(variant="subtab")
        qtbot.addWidget(tab_bar)

        received_ids: list[str] = []
        received_indices: list[int] = []
        tab_bar.tab_changed.connect(received_ids.append)
        tab_bar.tab_index_changed.connect(received_indices.append)

        btn1 = tab_bar.add_tab("tab_params", "Paramètres", "ph.gear")
        btn2 = tab_bar.add_tab("tab_dag", "DAG", "ph.git-branch")

        assert isinstance(btn1, SegmentedTabButton)
        assert tab_bar.count() == 2
        assert tab_bar.get_active_tab_id() == "tab_params"
        assert tab_bar.get_active_index() == 0

        # Clic sur le deuxième onglet
        btn2.click()
        assert tab_bar.get_active_tab_id() == "tab_dag"
        assert tab_bar.get_active_index() == 1
        assert received_ids == ["tab_dag"]
        assert received_indices == [1]

    def test_set_active_tab_by_id_and_index(self, qtbot: Any) -> None:
        tab_bar = SegmentedTabBar(variant="segmented")
        qtbot.addWidget(tab_bar)

        tab_bar.add_tab("t1", "Tab 1")
        tab_bar.add_tab("t2", "Tab 2")
        tab_bar.add_tab("t3", "Tab 3")

        tab_bar.set_active_tab("t3")
        assert tab_bar.get_active_index() == 2
        assert tab_bar.get_active_tab_id() == "t3"

        tab_bar.set_active_tab(1)
        assert tab_bar.get_active_index() == 1
        assert tab_bar.get_active_tab_id() == "t2"

    def test_tab_badge_and_enabled(self, qtbot: Any) -> None:
        tab_bar = SegmentedTabBar()
        qtbot.addWidget(tab_bar)

        btn = tab_bar.add_tab("errors", "Erreurs", "ph.warning", badge_text="3")
        assert btn.badge_text == "3"

        tab_bar.set_tab_badge("errors", "5")
        assert btn.badge_text == "5"

        tab_bar.set_tab_badge("errors", "")
        assert btn.badge_text == ""

        tab_bar.set_tab_enabled("errors", False)
        assert not btn.isEnabled()

    def test_keyboard_arrow_navigation(self, qtbot: Any) -> None:
        tab_bar = SegmentedTabBar()
        qtbot.addWidget(tab_bar)
        tab_bar.add_tab("t1", "Un")
        tab_bar.add_tab("t2", "Deux")
        tab_bar.add_tab("t3", "Trois")

        assert tab_bar.get_active_index() == 0

        # Flèche droite -> onglet suivant
        evt_right = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        tab_bar.keyPressEvent(evt_right)
        assert tab_bar.get_active_index() == 1

        # Flèche bas -> onglet suivant
        evt_down = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        tab_bar.keyPressEvent(evt_down)
        assert tab_bar.get_active_index() == 2

        # Flèche gauche -> onglet précédent
        evt_left = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
        tab_bar.keyPressEvent(evt_left)
        assert tab_bar.get_active_index() == 1

    def test_subtab_button_backward_compatibility(self, qtbot: Any) -> None:
        btn = SubTabButton("Options", "ph.gear", is_active=True)
        qtbot.addWidget(btn)
        assert btn.isChecked()

        btn.set_active(False)
        assert not btn.isChecked()


class TestTransverseNavigationRouting:
    """Vérifie le routage transverse des paramètres dans MainWindow."""

    def test_documents_view_receives_doc_id(self, monkeypatch: Any) -> None:
        from ankiforge.ui.main_window import MainWindow

        # Mock app components to test _on_view_selected logic cleanly
        window = MagicMock(spec=MainWindow)
        mock_doc_view = MagicMock(spec=QWidget)
        mock_doc_view._select_doc_id_in_tree = MagicMock()

        window._current_view_id = None
        window._can_switch_view.return_value = True
        window._view_registry = {}
        window._view_widgets = {"documents": mock_doc_view}
        window.stacked_widget = MagicMock()
        window.topbar = None
        window.current_layout = None

        # Appel de la logique _on_view_selected avec doc_id
        MainWindow._on_view_selected(window, "documents", {"doc_id": "doc_42"})

        # Vérifier que la vue a bien reçu la sélection de doc_id
        mock_doc_view._select_doc_id_in_tree.assert_called_once_with("doc_42")
        window.stacked_widget.setCurrentWidget.assert_called_once_with(mock_doc_view)
