"""
Tests unitaires pour l'Architecture UI Enfichable (Layouts) d'AnkiForge.
"""

from unittest.mock import patch
from PySide6.QtWidgets import QStackedWidget, QWidget

from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.layouts.dashboard_layout import DashboardLayout
from ankiforge.ui.layouts.glass_layout import GlassmorphismLayout
from ankiforge.ui.layouts.ide_layout import IdeLayout
from ankiforge.ui.layouts.layout_manager import LayoutManager
from ankiforge.ui.layouts.macos_layout import MacosLayout
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.theme import DesignTokens


def test_layout_manager_available_layouts():
    """Vérifie que tous les 4 layouts sont correctement enregistrés."""
    layouts = LayoutManager.get_available_layouts()
    layout_ids = [item["id"] for item in layouts]
    assert "ide" in layout_ids
    assert "macos" in layout_ids
    assert "dashboard" in layout_ids
    assert "glassmorphism" in layout_ids


def test_layout_instantiation_and_theme_sync(qtbot):
    """Vérifie l'instanciation de chaque classe de layout, l'injection du stacked widget et la synchro du thème."""
    stack = QStackedWidget()
    dummy = QWidget()
    stack.addWidget(dummy)

    for layout_id in ["ide", "macos", "dashboard", "glassmorphism"]:
        layout = LayoutManager.create_layout(layout_id, profile_name="test_user")
        LayoutManager.apply_theme_for_layout(layout_id)
        qtbot.addWidget(layout)
        assert isinstance(layout, BaseLayout)
        assert layout.get_layout_id() == layout_id
        assert DesignTokens.ACTIVE_THEME_ID == layout_id

        # Injection du stack et navigation
        layout.set_stacked_widget(stack)
        layout.populate_navigation(MainWindow.VIEW_REGISTRY)
        layout.set_active_view("dashboard")
        layout.update_daemon_status("idle", "Daemon Prêt")
        layout.update_token_tracker("0.05", "1500")


def test_main_window_layout_hot_reload_and_tokens(qtbot, mock_db):
    """Vérifie le basculement dynamique à chaud des layouts et de leurs tokens visuels sur MainWindow."""
    LayoutManager.save_layout_id("test_profile", "ide")
    with patch("ankiforge.services.background_daemon.BackgroundDaemon"), patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="test_profile")
        qtbot.addWidget(window)

        # 1. Test layout par défaut (IDE)
        assert window.current_layout is not None
        assert window.current_layout.get_layout_id() == "ide"
        assert DesignTokens.ACCENT_PRIMARY == "#6366f1"

        # 2. Bascule vers macOS (Apple Blue + Radius 8px)
        window.apply_layout("macos")
        assert window.current_layout is not None
        assert window.current_layout.get_layout_id() == "macos"
        assert isinstance(window.current_layout, MacosLayout)
        assert DesignTokens.ACCENT_PRIMARY == "#0a84ff"
        assert DesignTokens.RADIUS_SM == 8

        # 3. Bascule vers Dashboard (Emerald Green)
        window.apply_layout("dashboard")
        assert window.current_layout is not None
        assert window.current_layout.get_layout_id() == "dashboard"
        assert isinstance(window.current_layout, DashboardLayout)
        assert DesignTokens.ACCENT_PRIMARY == "#10b981"
        assert DesignTokens.BG_MAIN == "#0b0f19"

        # 4. Bascule vers Glassmorphism (Neon Amethyst + Radius 10px)
        window.apply_layout("glassmorphism")
        assert window.current_layout is not None
        assert window.current_layout.get_layout_id() == "glassmorphism"
        assert isinstance(window.current_layout, GlassmorphismLayout)
        assert DesignTokens.ACCENT_PRIMARY == "#c084fc"
        assert DesignTokens.RADIUS_SM == 10

        # 5. Retour vers IDE
        window.apply_layout("ide")
        assert window.current_layout is not None
        assert window.current_layout.get_layout_id() == "ide"
        assert isinstance(window.current_layout, IdeLayout)
        assert DesignTokens.ACCENT_PRIMARY == "#6366f1"


def test_layout_persistence(tmp_path):
    """Vérifie la sauvegarde et la récupération du layout par profil."""
    profile = "student_profile"
    LayoutManager.save_layout_id(profile, "macos")
    assert LayoutManager.get_saved_layout_id(profile) == "macos"

    LayoutManager.save_layout_id(profile, "glassmorphism")
    assert LayoutManager.get_saved_layout_id(profile) == "glassmorphism"
