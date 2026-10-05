"""Navigation libre inter-vues : pas de garde modal sur le switch d'onglet.

Couvre le ticket « Feature : navigation libre inter-vues sans blocage modal » :
la navigation entre vues ne doit plus déclencher de dialogue `is_dirty()`, l'état de
travail de CreationView/BatchView doit survivre aux allers-retours, les gardes
`is_dirty()` doivent être réservés aux actions destructives (fermeture, changement
de profil) et un indicateur discret doit rappeler le travail en cours sur la
navigation.
"""

import inspect
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox, QWidget

from ankiforge.ui.components.nav_badge import NavBadgeButton
from ankiforge.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


class DirtyViewProbe(QWidget):
    """Vue de test exposant un `is_dirty()` contrôlable et un compte de travail."""

    def __init__(self, view_id: str, dirty: bool = True) -> None:
        super().__init__()
        self.view_id = view_id
        self._dirty = dirty
        self.refresh_count = 0

    def refresh_data(self) -> None:
        self.refresh_count += 1

    def is_dirty(self) -> bool:
        return self._dirty

    def pending_work_count(self) -> int:
        return 7 if self._dirty else 0


@pytest.fixture(autouse=True)
def no_modal_dialog() -> Iterator[Any]:
    """Enregistre toute boîte de dialogue modale et répond « Non » sans bloquer la boucle Qt.

    Répondre « Non » laisse pytest-qt fermer proprement les fenêtres : un `closeEvent`
    annulé ne lève rien. Les tests qui exigent l'absence de dialogue vérifient
    `call_count == 0` dans le corps du test.
    """
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
        yield question


@pytest.fixture(autouse=True)
def no_mcp_autostart() -> Iterator[None]:
    """Empêche le QTimer d'auto-démarrage MCP de survivre au test.

    `_init_mcp_daemon` programme `start_mcp_server` 500 ms après la construction ; ce
    timer outlive la fixture et référence un `MCPStatusWidget` déjà détruit, ce qui fait
    échouer le teardown Qt. On force donc `is_testing()` pendant toute la construction.
    """
    with patch("ankiforge.utils.environment.is_testing", return_value=True):
        yield


@pytest.fixture
def window(qtbot: Any, mock_db: Any) -> MainWindow:
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        win = MainWindow(ai_manager=None)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def install_probe(window: MainWindow) -> Iterator[Callable[..., DirtyViewProbe]]:
    """Fabrique de sondes sales restaurant la fenêtre avant le nettoyage Qt global.

    Les finaliseurs de fixtures précèdent `cleanup_qt_widgets`, qui ferme les widgets
    orphelins : sans cette restauration, `closeEvent` verrait encore une vue sale.
    """
    from ankiforge.ui.main_window import DummyView

    installed: list[str] = []

    def _install(view_id: str, dirty: bool = True) -> DirtyViewProbe:
        installed.append(view_id)
        probe = DirtyViewProbe(view_id, dirty=dirty)
        window._view_widgets[view_id] = probe
        window._current_view_id = view_id
        return probe

    yield _install

    for view_id in installed:
        window._view_widgets[view_id] = DummyView(view_id)
    window._current_view_id = None


# ---------------------------------------------------------------------------
# Critère 1 : la navigation ne déclenche plus de dialogue
# ---------------------------------------------------------------------------


class TestNavigationIsNeverBlocked:
    def test_switching_away_from_a_dirty_view_asks_nothing(self, window: MainWindow, install_probe: Any, no_modal_dialog: Any) -> None:
        """Une vue sale ne doit plus empêcher la navigation vers une autre vue."""
        install_probe("batch", dirty=True)

        window._on_view_selected("documents")

        assert window._current_view_id == "documents"
        assert no_modal_dialog.call_count == 0

    def test_does_not_call_the_destructive_guard_on_navigation(self, window: MainWindow, install_probe: Any) -> None:
        """`_confirm_discard_unsaved_work` est réservé aux actions destructives."""
        install_probe("batch", dirty=True)

        with patch.object(MainWindow, "_confirm_discard_unsaved_work", side_effect=AssertionError("garde destructif invoqué")) as guard:
            window._on_view_selected("creation")

        guard.assert_not_called()
        assert window._current_view_id == "creation"

    def test_no_dirty_prompt_when_leaving_a_clean_view(self, window: MainWindow, install_probe: Any, no_modal_dialog: Any) -> None:
        install_probe("edition", dirty=False)

        window._on_view_selected("documents")

        assert window._current_view_id == "documents"
        assert no_modal_dialog.call_count == 0

    def test_view_instances_are_reused_across_switches(self, window: MainWindow, install_probe: Any) -> None:
        """Aller-retour : la même instance de vue est réutilisée (état en mémoire)."""
        probe = install_probe("batch", dirty=True)

        window._on_view_selected("documents")
        window._on_view_selected("batch")

        assert window._view_widgets["batch"] is probe


# ---------------------------------------------------------------------------
# Critère 2 : sanctuarisation de l'état de travail au retour
# ---------------------------------------------------------------------------


class TestWorkStateSurvivesRoundTrip:
    def test_batch_queue_survives_creation_refresh_data(self, qtbot: Any, mock_db: Any) -> None:
        """`BatchView.refresh_data()` ne doit ni vider ni remplacer la file d'attente."""
        from ankiforge.ui.views.batch_view import BatchView

        view = BatchView()
        qtbot.addWidget(view)
        view.queue_tasks_data = [{"doc_id": "d1", "status": "À réviser", "cards_count": 3}]
        before = [dict(task) for task in view.queue_tasks_data]

        view.refresh_data()

        assert len(view.queue_tasks_data) == 1
        assert [t.get("doc_id") for t in view.queue_tasks_data] == ["d1"]
        assert [t.get("status") for t in view.queue_tasks_data] == ["À réviser"]
        assert [t.get("cards_count") for t in view.queue_tasks_data] == [3]
        assert [dict(t) for t in view.queue_tasks_data] == before

    def test_batch_staging_review_state_survives_creation_refresh_data(self, qtbot: Any, mock_db: Any) -> None:
        """Une revue en cours (panneau de staging) n'est pas réinitialisée par refresh_data()."""
        from ankiforge.ui.views.batch_view import BatchView

        view = BatchView()
        qtbot.addWidget(view)
        view.queue_tasks_data = [{"doc_id": "d1", "status": "À réviser"}]
        panel = view.staging_panel
        panel._prepared_notes = [{"Front": "A", "Back": "B"}]
        panel._current_task_idx = 0
        panel._current_card_idx = 0

        view.refresh_data()

        assert panel._prepared_notes == [{"Front": "A", "Back": "B"}]
        assert panel._current_task_idx == 0
        assert panel._current_card_idx == 0

    def test_creation_generated_cards_survive_refresh_data(self, qtbot: Any, mock_db: Any) -> None:
        """`CreationView.refresh_data()` ne doit ni vider ni recalculer les cartes générées."""
        from ankiforge.ui.views.creation_view import CreationView

        view = CreationView()
        qtbot.addWidget(view)
        view.generated_cards = [
            {"Front": "A1", "Back": "B1", "status": "Validée"},
            {"Front": "A2", "Back": "B2", "status": "À valider"},
        ]

        view.refresh_data()

        assert len(view.generated_cards) == 2
        assert [c["status"] for c in view.generated_cards] == ["Validée", "À valider"]
        assert view._count_validated() == 1
        assert view.is_dirty() is True

    def test_creation_view_is_not_reinstantiated_on_return(self, window: MainWindow, install_probe: Any) -> None:
        """Un aller-retour ne doit pas reconstruire la vue (donc pas perdre les cartes)."""
        window._on_view_selected("creation")
        created = window._view_widgets["creation"]

        window._on_view_selected("documents")
        window._on_view_selected("creation")

        assert window._view_widgets["creation"] is created


# ---------------------------------------------------------------------------
# Critères 1 & 4 : `is_dirty()` réservé aux actions destructives
# ---------------------------------------------------------------------------


class TestDestructiveGuards:
    def test_confirm_reports_dirty_views_by_title(self, window: MainWindow, install_probe: Any) -> None:
        install_probe("batch", dirty=True)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
            assert window._confirm_discard_unsaved_work("fermer l'application") is False

        question.assert_called_once()
        message = question.call_args.args[2]
        assert "Batch Factory" in message
        assert "fermer l'application" in message

    def test_confirm_passes_when_nothing_is_dirty(self, window: MainWindow, install_probe: Any, no_modal_dialog: Any) -> None:
        install_probe("batch", dirty=False)

        assert window._confirm_discard_unsaved_work("fermer l'application") is True
        assert no_modal_dialog.call_count == 0

    def test_confirm_ignores_uninstantiated_placeholders(self, window: MainWindow, install_probe: Any, no_modal_dialog: Any) -> None:
        """Les placeholders (DummyView) ne sont jamais sales."""
        assert window._confirm_discard_unsaved_work("fermer l'application") is True
        assert no_modal_dialog.call_count == 0

    def test_close_event_is_cancelled_when_user_declines(self, window: MainWindow, install_probe: Any) -> None:
        probe = install_probe("creation", dirty=True)
        event = QCloseEvent()

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No),
            patch("ankiforge.database.maintenance.execute_clean_shutdown") as shutdown,
        ):
            MainWindow.closeEvent(window, event)

        assert not event.isAccepted()
        shutdown.assert_not_called()
        # La vue sale est laissée intacte : rien n'est détruit en cas de renoncement.
        assert window._view_widgets["creation"] is probe

    def test_close_event_proceeds_when_user_confirms(self, window: MainWindow, install_probe: Any) -> None:
        install_probe("creation", dirty=True)
        event = QCloseEvent()

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
            patch("ankiforge.database.maintenance.execute_clean_shutdown") as shutdown,
        ):
            MainWindow.closeEvent(window, event)

        assert event.isAccepted()
        shutdown.assert_called_once()

    def test_close_event_never_asks_when_nothing_is_dirty(self, window: MainWindow, install_probe: Any, no_modal_dialog: Any) -> None:
        event = QCloseEvent()

        with patch("ankiforge.database.maintenance.execute_clean_shutdown"):
            MainWindow.closeEvent(window, event)

        assert event.isAccepted()
        assert no_modal_dialog.call_count == 0

    def test_profile_switch_is_blocked_when_user_declines(self, window: MainWindow, install_probe: Any) -> None:
        install_probe("batch", dirty=True)
        original_profile = window.profile_name

        with patch("ankiforge.services.profile_lock_service.ProfileLockService.acquire_lock", return_value=(True, None)) as acquire:
            window.switch_to_profile("other")

        acquire.assert_not_called()
        assert window.profile_name == original_profile


# ---------------------------------------------------------------------------
# Critère 3 : indicateur discret sur la navigation
# ---------------------------------------------------------------------------


class TestNavBadge:
    def test_nav_badge_button_shows_and_hides_count(self, qtbot: Any) -> None:
        btn = NavBadgeButton("batch", "factory", "Batch Factory")
        qtbot.addWidget(btn)

        assert btn.nav_badge_count() is None
        assert btn.nav_badge_label().isHidden()

        btn.set_nav_badge(4)
        assert btn.nav_badge_count() == 4
        assert btn.nav_badge_label().text() == "4"
        assert not btn.nav_badge_label().isHidden()

        btn.set_nav_badge(None)
        assert btn.nav_badge_count() is None
        assert btn.nav_badge_label().isHidden()

    def test_nav_badge_caps_long_counts(self, qtbot: Any) -> None:
        btn = NavBadgeButton("batch", "factory", "Batch Factory")
        qtbot.addWidget(btn)

        btn.set_nav_badge(1234)
        assert btn.nav_badge_label().text() == "99+"

    def test_nav_badge_zero_is_equivalent_to_no_badge(self, qtbot: Any) -> None:
        btn = NavBadgeButton("batch", "factory", "Batch Factory")
        qtbot.addWidget(btn)

        btn.set_nav_badge(0)
        assert btn.nav_badge_count() is None
        assert btn.nav_badge_label().isHidden()

    def test_nav_badge_carries_an_accessible_label(self, qtbot: Any) -> None:
        btn = NavBadgeButton("batch", "factory", "Batch Factory")
        qtbot.addWidget(btn)
        btn.set_nav_badge(3)

        assert btn.nav_badge_label().accessibleName() == "Batch Factory — 3 éléments en cours"

    def test_badge_stays_inside_the_button_bounds(self, qtbot: Any) -> None:
        btn = NavBadgeButton("batch", "factory", "Batch Factory")
        qtbot.addWidget(btn)
        btn.show()
        qtbot.waitExposed(btn)
        btn.set_nav_badge(7)

        geo = btn.nav_badge_label().geometry()
        assert geo.right() <= btn.width()
        assert geo.left() >= 0
        assert geo.top() >= 0

    @pytest.mark.parametrize("layout_id", ["ide", "macos", "dashboard", "glassmorphism"])
    def test_every_layout_actually_renders_the_badge(self, qtbot: Any, layout_id: str) -> None:
        """Chaque layout rend une pastille visible, et sait la masquer."""
        from ankiforge.ui.layouts.layout_manager import LayoutManager

        layout = LayoutManager.create_layout(layout_id, profile_name="default")
        qtbot.addWidget(layout)
        layout.populate_navigation(MainWindow.view_registry())
        layout.resize(1400, 900)
        layout.show()
        qtbot.waitExposed(layout)

        button = self._nav_buttons(layout, layout_id)["batch"]
        assert isinstance(button, NavBadgeButton)
        assert button.nav_badge_label().isHidden()

        layout.set_nav_badge("batch", 3)
        qtbot.waitExposed(button)

        label = button.nav_badge_label()
        assert not label.isHidden()
        assert label.text() == "3"

        # La pastille reste dans le bouton et ne mord pas sur l'icône.
        assert label.geometry().right() <= button.width()
        assert label.geometry().left() >= button.iconSize().width()

        layout.set_nav_badge("batch", None)
        assert button.nav_badge_label().isHidden()

    @pytest.mark.parametrize("layout_id", ["ide", "macos", "dashboard", "glassmorphism"])
    def test_set_nav_badge_ignores_unknown_views(self, qtbot: Any, layout_id: str) -> None:
        from ankiforge.ui.layouts.layout_manager import LayoutManager

        layout = LayoutManager.create_layout(layout_id, profile_name="default")
        qtbot.addWidget(layout)
        layout.populate_navigation(MainWindow.view_registry())

        layout.set_nav_badge("vue-inexistante", 5)

    def test_badge_style_is_declared_in_the_central_stylesheet(self) -> None:
        """Règle d'or DESIGN.md : le style d'un nouveau widget vit dans `StyleEngine`, pas codé en dur."""
        from ankiforge.ui.style_engine import StyleEngine

        stylesheet = StyleEngine.instance().generate_stylesheet()
        block = stylesheet.split("/* --- NavBadgeButton")[1].split("}")[0]

        assert "QLabel#NavBadge" in stylesheet
        for declaration in ("background-color:", "color:", "border:", "border-radius:", "font-size:"):
            assert declaration in block
        # La pastille ne porte aucun style en dur : le QSS global est sa seule source.
        source = inspect.getsource(NavBadgeButton)
        assert "setStyleSheet" not in source
        assert "DesignTokens" not in source

    @staticmethod
    def _nav_buttons(layout: Any, layout_id: str) -> dict[str, Any]:
        """Boutons de navigation d'un layout, quelle que soit sa famille de boutons."""
        return layout.sidebar._items if layout_id == "ide" else layout._nav_buttons

    def test_main_window_publishes_dirty_counts_to_the_layout(self, window: MainWindow, install_probe: Any) -> None:
        install_probe("batch", dirty=True)

        with patch.object(type(window.current_layout), "set_nav_badge") as set_badge:
            window._refresh_nav_badges()

        assert ("batch", 7) in [c.args for c in set_badge.call_args_list]

    def test_main_window_clears_badge_for_clean_view(self, window: MainWindow, install_probe: Any) -> None:
        install_probe("batch", dirty=False)

        with patch.object(type(window.current_layout), "set_nav_badge") as set_badge:
            window._refresh_nav_badges()

        assert ("batch", None) in [c.args for c in set_badge.call_args_list]

    def test_main_window_survives_views_without_pending_work_count(self, window: MainWindow, install_probe: Any) -> None:
        class _NoCount(QWidget):
            def refresh_data(self) -> None:
                pass

            def is_dirty(self) -> bool:
                return False

        window._view_widgets["documents"] = _NoCount()

        with patch.object(type(window.current_layout), "set_nav_badge") as set_badge:
            window._refresh_nav_badges()

        assert ("documents", None) in [c.args for c in set_badge.call_args_list]

    def test_main_window_survives_a_failing_pending_work_count(self, window: MainWindow, install_probe: Any) -> None:
        class _Exploding(QWidget):
            def pending_work_count(self) -> int:
                raise RuntimeError("boom")

        window._view_widgets["documents"] = _Exploding()

        with patch.object(type(window.current_layout), "set_nav_badge") as set_badge:
            window._refresh_nav_badges()

        assert ("documents", None) in [c.args for c in set_badge.call_args_list]

    def test_batch_view_reports_active_tasks_only(self, qtbot: Any, mock_db: Any) -> None:
        """La pastille ne compte que les tâches actives : une frappe terminée l'éteint."""
        from ankiforge.ui.views.batch_view import BatchView

        view = BatchView()
        qtbot.addWidget(view)
        assert view.pending_work_count() == 0

        view.queue_tasks_data = [
            {"doc_id": "d1", "status": "En attente"},
            {"doc_id": "d2", "status": "En cours"},
            {"doc_id": "d3", "status": "À réviser"},
            {"doc_id": "d4", "status": "Erreur"},
            {"doc_id": "d5", "status": "Succès"},
            {"doc_id": "d6", "status": "Acceptée"},
        ]
        assert view.pending_work_count() == 4

        # Toutes les tâches réglées : plus rien à signaler.
        view.queue_tasks_data = [{"doc_id": "d5", "status": "Succès"}, {"doc_id": "d6", "status": "Acceptée"}]
        assert view.pending_work_count() == 0

        view.queue_tasks_data = []
        assert view.pending_work_count() == 0

    def test_creation_view_reports_unsaved_cards(self, qtbot: Any, mock_db: Any) -> None:
        from ankiforge.ui.views.creation_view import CreationView

        view = CreationView()
        qtbot.addWidget(view)
        assert view.pending_work_count() == 0

        view.generated_cards = [
            {"Front": "A", "Back": "B", "status": "À valider"},
            {"Front": "C", "Back": "D", "status": "Enregistrée"},
            {"Front": "E", "Back": "F", "status": "Validée"},
        ]
        assert view.pending_work_count() == 2


# ---------------------------------------------------------------------------
# Régression : la sidebar suit la navigation sans retour arrière
# ---------------------------------------------------------------------------


class TestSidebarSelection:
    def test_sidebar_follows_the_navigation_without_reset(self, window: MainWindow, install_probe: Any) -> None:
        sidebar = window.sidebar
        if sidebar is None:
            pytest.skip("Le layout actif n'expose pas de Sidebar (layout non-ide).")
        install_probe("batch", dirty=True)

        window._on_view_selected("documents")

        assert sidebar._items["documents"].isChecked()
