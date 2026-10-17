"""Tests unitaires et d'intégration pour le système d'onglets IdePanel, le détachement/rattachement, la réouverture via le bouton +, la SegmentedTabBar et la navigation transverse."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDragMoveEvent, QDropEvent, QKeyEvent
from PySide6.QtWidgets import QLabel, QSplitter, QWidget

from ankiforge.ui.components.panels import IdePanel, PanelPlaceholderWidget
from ankiforge.ui.components.tabs.floating_dock import _floating_windows
from ankiforge.ui.components.tabs.segmented_tab_bar import (
    SegmentedTabBar,
    SegmentedTabButton,
    SubTabButton,
)

pytestmark = pytest.mark.ui


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
        hint_with_badge_3 = btn.sizeHint().width()

        tab_bar.set_tab_badge("errors", "58")
        assert btn.badge_text == "58"
        hint_with_badge_58 = btn.sizeHint().width()
        assert hint_with_badge_58 >= hint_with_badge_3

        tab_bar.set_tab_badge("errors", "")
        assert btn.badge_text == ""
        hint_without_badge = btn.sizeHint().width()
        # La taille avec badge réserve au moins 20px supplémentaires pour éviter tout rognage
        assert hint_with_badge_58 > hint_without_badge + 15

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


class TestTabIconColors:
    """Vérifie la gestion et la persistance des couleurs sémantiques des icônes d'onglets."""

    def test_tab_icon_color_persistence_and_detach(self, qtbot: Any) -> None:
        """Vérifie qu'un onglet conserve sa couleur d'icône personnalisée après détachement et rattachement."""
        from ankiforge.ui.theme import DesignTokens

        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        widget = QLabel("Test Content")
        panel.add_tab("Onglet Coloré", widget, icon_name="sparkle", icon_color=DesignTokens.COLOR_YELLOW, closable=True)

        assert panel.tabs_bar.count() == 1
        btn = panel.tabs_bar.tabs[0]
        assert btn.property("icon_color") == DesignTokens.COLOR_YELLOW

        # Modification dynamique via set_tab_icon_color
        panel.set_tab_icon_color(0, DesignTokens.COLOR_BLUE)
        assert btn.property("icon_color") == DesignTokens.COLOR_BLUE

        # Détachement
        float_win = panel.detach_panel(0)
        assert float_win is not None
        qtbot.addWidget(float_win)

        float_btn = float_win.tabs_bar.tabs[0]
        assert float_btn.property("icon_color") == DesignTokens.COLOR_BLUE

        # Fermeture de la fenêtre flottante -> rattachement au panneau d'origine
        close_evt = QCloseEvent()
        float_win.closeEvent(close_evt)

        assert panel.tabs_bar.count() == 1
        restored_btn = panel.tabs_bar.tabs[0]
        assert restored_btn.property("icon_color") == DesignTokens.COLOR_BLUE

    def test_analysis_view_tab_icon_colors(self, qtbot: Any) -> None:
        """Vérifie que la vue Analyse initialise ses 4 sous-onglets avec les accents sémantiques Or, Bleu, Vert, Violet."""
        from ankiforge.ui.theme import DesignTokens
        from ankiforge.ui.views.analysis_view.view import AnalysisView

        view = AnalysisView()
        qtbot.addWidget(view)

        tabs = view.main_panel.tabs_bar.tabs
        assert len(tabs) == 4

        # 0: Audit & Linter Wozniak -> Yellow / Gold
        assert tabs[0].property("icon_color") == DesignTokens.COLOR_YELLOW
        # 1: Documents -> Blue
        assert tabs[1].property("icon_color") == DesignTokens.COLOR_BLUE
        # 2: Jetons & SRS -> Green
        assert tabs[2].property("icon_color") == DesignTokens.COLOR_GREEN
        # 3: Fusions & Doublons -> Purple
        assert tabs[3].property("icon_color") == DesignTokens.COLOR_PURPLE

        # Test refresh_theme
        mock_profile = MagicMock()
        mock_profile.color_yellow = "#ffbb00"
        mock_profile.color_blue = "#0088ff"
        mock_profile.color_green = "#00ee88"
        mock_profile.color_purple = "#8800ff"

        view.refresh_theme(mock_profile)

        assert tabs[0].property("icon_color") == "#ffbb00"
        assert tabs[1].property("icon_color") == "#0088ff"
        assert tabs[2].property("icon_color") == "#00ee88"
        assert tabs[3].property("icon_color") == "#8800ff"


class TestTabMaskingAndReopening:
    """Vérifie le masquage et la réouverture d'onglets au sein d'un IdePanel."""

    def test_close_and_reopen_tab_preserves_state(self, qtbot: Any) -> None:
        panel = IdePanel(detachable=True, permanent=True)
        qtbot.addWidget(panel)
        panel.show()

        w1 = QLabel("Contenu 1")
        w2 = QLabel("Contenu 2")
        panel.add_tab("Tab 1", w1, "ph.star", closable=True)
        panel.add_tab("Tab 2", w2, "ph.heart", closable=True)

        assert panel.tabs_bar.count() == 2
        assert panel.content_stack.count() == 2

        # Fermer Tab 1
        panel.close_tab("Tab 1")
        assert panel.tabs_bar.count() == 1
        assert panel.tabs_bar.tabs[0].text().strip() == "Tab 2"
        assert panel._registered_tabs["Tab 1"]["active"] is False
        assert panel._registered_tabs["Tab 2"]["active"] is True

        # Réouvrir Tab 1
        panel.open_tab("Tab 1")
        assert panel.tabs_bar.count() == 2
        assert panel._registered_tabs["Tab 1"]["active"] is True
        assert panel.content_stack.currentWidget() == w1

    def test_close_all_tabs_shows_placeholder_without_deleting_permanent_panel(self, qtbot: Any) -> None:
        splitter = QSplitter()
        panel = IdePanel(detachable=True, permanent=True, parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        w1 = QLabel("Contenu")
        panel.add_tab("Tab", w1, "ph.star", closable=True)
        assert panel.placeholder_widget.isHidden()

        # Fermer le dernier onglet
        panel.close_tab("Tab")
        assert panel.tabs_bar.count() == 0
        assert panel.placeholder_widget.isVisible()
        assert panel.header.isHidden()

        # Clic sur le bouton fermer du placeholder d'un panneau permanent -> doit cacher et non détruire
        if hasattr(panel.placeholder_widget, "close_btn"):
            panel.placeholder_widget.close_btn.click()
            assert panel.isHidden()
            # L'objet panel est toujours vivant et valide (pas de RuntimeError Shiboken)
            panel.show()
            assert panel.isVisible()

        # Restaurer tous les onglets
        panel.restore_all_registered_tabs()
        assert panel.tabs_bar.count() == 1
        assert panel.placeholder_widget.isHidden()
        assert panel.header.isVisible()


class TestTabDragAndDropPanels:
    """Vérifie la robustesse du glisser-déposer d'onglets au sein et entre panneaux IdePanel."""

    def test_tabs_package_exports_drag_accessors(self) -> None:
        """Vérifie que get_dragged_tab_info et set_dragged_tab_info sont bien ré-exportés par tabs."""
        from ankiforge.ui.components.tabs import get_dragged_tab_info, set_dragged_tab_info

        dummy_payload = {"title": "Test Tab", "index": 0}
        set_dragged_tab_info(dummy_payload)
        assert get_dragged_tab_info() == dummy_payload

        set_dragged_tab_info(None)
        assert get_dragged_tab_info() is None

    def test_ide_panel_drag_events_without_attribute_error(self, qtbot: Any) -> None:
        """Vérifie que dragEnter, dragMove et drop sur IdePanel ne lèvent pas AttributeError."""
        from ankiforge.ui.components.tabs.tab_button import set_dragged_tab_info

        panel1 = IdePanel(detachable=True)
        panel2 = IdePanel(detachable=True)
        qtbot.addWidget(panel1)
        qtbot.addWidget(panel2)
        panel1.resize(400, 300)
        panel2.resize(400, 300)
        panel1.show()
        panel2.show()

        w1 = QLabel("Tab 1 Content")
        w2 = QLabel("Tab 2 Content")
        panel1.add_tab("Tab 1", w1, "ph.star", closable=True)
        panel1.add_tab("Tab 2", w2, "ph.heart", closable=True)

        w3 = QLabel("Tab 3 Content")
        panel2.add_tab("Tab 3", w3, "ph.note", closable=True)

        mime = QMimeData()
        mime.setData("application/x-ankiforge-tab", b"")

        # 1. dragEnterEvent avec info de drag nulle
        set_dragged_tab_info(None)
        enter_event_empty = QDragEnterEvent(
            QPoint(50, 50),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        panel1.dragEnterEvent(enter_event_empty)

        # 2. dragEnterEvent & dragMoveEvent avec info de drag active
        set_dragged_tab_info(
            {
                "source_panel": panel1,
                "index": 0,
                "widget": w1,
                "title": "Tab 1",
                "icon_name": "ph.star",
            }
        )
        enter_event = QDragEnterEvent(
            QPoint(50, 50),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        panel2.dragEnterEvent(enter_event)

        move_event = QDragMoveEvent(
            QPoint(200, 150),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        panel2.dragMoveEvent(move_event)

        # 3. dropEvent sur panel2 (centre)
        drop_event = QDropEvent(
            QPointF(200.0, 150.0),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        panel2.dropEvent(drop_event)

        # L'onglet a été transféré de panel1 à panel2 et l'info de drag est nettoyée
        from ankiforge.ui.components.tabs.tab_button import get_dragged_tab_info

        assert get_dragged_tab_info() is None
        assert panel1.tabs_bar.count() == 1
        assert panel2.tabs_bar.count() == 2

    def test_placeholder_drop_event_without_attribute_error(self, qtbot: Any) -> None:
        """Vérifie que dropEvent sur PanelPlaceholderWidget ne lève pas AttributeError."""
        from ankiforge.ui.components.tabs.tab_button import get_dragged_tab_info, set_dragged_tab_info

        src_panel = IdePanel(detachable=True)
        target_panel = IdePanel(detachable=True, permanent=True)
        qtbot.addWidget(src_panel)
        qtbot.addWidget(target_panel)

        w1 = QLabel("Tab Source")
        src_panel.add_tab("Tab Source", w1, "ph.star", closable=True)

        placeholder = target_panel.placeholder_widget

        mime = QMimeData()
        mime.setData("application/x-ankiforge-tab", b"")

        set_dragged_tab_info(
            {
                "source_panel": src_panel,
                "index": 0,
                "widget": w1,
                "title": "Tab Source",
                "icon_name": "ph.star",
            }
        )

        drop_event = QDropEvent(
            QPointF(50.0, 50.0),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        placeholder.dropEvent(drop_event)

        assert get_dragged_tab_info() is None
        assert src_panel.tabs_bar.count() == 0
        assert target_panel.tabs_bar.count() == 1

    def test_no_direct_dragged_tab_info_usage_in_panels(self) -> None:
        """Garantit qu'aucune référence directe à _dragged_tab_info ou tabs_mod n'existe dans panels.py."""
        import ast
        from pathlib import Path

        panels_path = Path(__file__).resolve().parent.parent.parent / "src" / "ankiforge" / "ui" / "components" / "panels.py"
        tree = ast.parse(panels_path.read_text(encoding="utf-8"))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}

        assert "_dragged_tab_info" not in attrs
        assert "_dragged_tab_info" not in names
        assert "tabs_mod" not in names
