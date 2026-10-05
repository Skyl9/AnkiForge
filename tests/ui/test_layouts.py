"""
Tests unitaires pour l'Architecture UI Enfichable (Layouts) d'AnkiForge.
"""

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QStackedWidget, QWidget

from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.layouts.dashboard_layout import DashboardLayout
from ankiforge.ui.layouts.glass_layout import GlassmorphismLayout
from ankiforge.ui.layouts.ide_layout import IdeLayout
from ankiforge.ui.layouts.layout_manager import LayoutManager
from ankiforge.ui.layouts.macos_layout import MacosLayout
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.theme import DesignTokens

pytestmark = pytest.mark.ui


def test_layout_manager_available_layouts():
    """Vérifie que tous les 4 layouts sont correctement enregistrés avec icônes distinctes et miniatures."""
    layouts = LayoutManager.get_available_layouts()
    layout_ids = [item["id"] for item in layouts]
    assert "ide" in layout_ids
    assert "macos" in layout_ids
    assert "dashboard" in layout_ids
    assert "glassmorphism" in layout_ids

    # Chaque layout doit avoir une icône et une référence de miniature distinctes
    icons = [item["icon"] for item in layouts]
    assert len(icons) == len(set(icons)), "Chaque disposition doit avoir une icône distincte"
    assert all(item["icon"].startswith("ph.") for item in layouts)
    assert all(item["thumbnail"] == f"{item['id']}.png" for item in layouts)

    # get_layout_thumbnail_path doit retourner un Path valide ou None
    for item in layouts:
        p = LayoutManager.get_layout_thumbnail_path(item["id"])
        assert p is None or p.name == f"{item['id']}.png"


@pytest.mark.slow
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
        assert DesignTokens.ACTIVE_THEME_ID is not None

        # Injection du stack et navigation
        layout.set_stacked_widget(stack)
        layout.populate_navigation(MainWindow.view_registry())
        layout.set_active_view("dashboard")
        layout.update_token_tracker("0.05", "1500")


@pytest.mark.slow
def test_main_window_layout_hot_reload_and_tokens(qtbot, mock_db):
    """Vérifie le basculement dynamique à chaud des layouts et de leurs tokens visuels sur MainWindow."""
    LayoutManager.save_layout_id("test_profile", "ide")
    # Aucune Famille persistée : chaque layout impose donc sa Famille par défaut (ADR 0004).
    assert get_style_engine().get_appearance_preference("test_profile").family_id is None
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
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


@pytest.mark.slow
def test_ide_layout_sidebar_toggle(qtbot, mock_db):
    """Vérifie que le bouton de la sidebar et l'icône du logo rétractent et ré-étendent correctement la sidebar."""
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="test_profile")
        window.apply_layout("ide")
        qtbot.addWidget(window)

        sidebar = window.sidebar

        assert sidebar is not None
        assert not sidebar.is_collapsed
        assert sidebar.width() == DesignTokens.SIDEBAR_WIDTH_EXPANDED

        # 1. Clic sur le bouton hamburger/list de la sidebar pour la replier
        sidebar.toggle_btn.click()
        assert sidebar.is_collapsed
        assert sidebar.width() == DesignTokens.SIDEBAR_WIDTH_COLLAPSED

        # 2. Clic sur le logo pour la ré-étendre
        sidebar.logo_icon.clicked.emit()
        assert not sidebar.is_collapsed
        assert sidebar.width() == DesignTokens.SIDEBAR_WIDTH_EXPANDED


def test_flow_layout_wrapping_and_crud(qtbot):
    """Vérifie le bon fonctionnement du FlowLayout (ajout, calcul de taille, suppression)."""
    from PySide6.QtWidgets import QLabel, QWidget

    from ankiforge.ui.components.flow_layout import FlowLayout

    container = QWidget()
    qtbot.addWidget(container)
    layout = FlowLayout(container, margin=5, h_spacing=8, v_spacing=8)

    labels = [QLabel(f"Label {i}") for i in range(10)]
    for lbl in labels:
        layout.addWidget(lbl)

    assert layout.count() == 10
    assert layout.horizontalSpacing() == 8
    assert layout.verticalSpacing() == 8
    assert layout.hasHeightForWidth() is True
    assert layout.heightForWidth(200) > 0
    assert layout.sizeHint().isValid()
    assert layout.minimumSize().isValid()

    # Retirer des éléments
    item = layout.takeAt(0)
    assert item is not None
    assert layout.count() == 9
    assert layout.itemAt(0) is not None


def test_flow_layout_fixed_height_widgets_no_overlap(qtbot):
    """Vérifie que les widgets à hauteur fixe dans FlowLayout ne se chevauchent pas et que heightForWidth est exact."""
    from PySide6.QtWidgets import QPushButton, QWidget

    from ankiforge.ui.components.flow_layout import FlowLayout

    container = QWidget()
    qtbot.addWidget(container)
    layout = FlowLayout(container, margin=0, h_spacing=6, v_spacing=6)

    btn1 = QPushButton("Bouton 1")
    btn1.setFixedHeight(26)
    btn2 = QPushButton("Bouton 2")
    btn2.setFixedHeight(26)
    layout.addWidget(btn1)
    layout.addWidget(btn2)

    container.show()
    # À une largeur étroite forçant le wrap sur 2 lignes
    h = layout.heightForWidth(50)
    assert h == 26 + 6 + 26  # 58px exactement


@pytest.mark.slow
def test_generate_layout_thumbnails_preserves_profile_settings(tmp_path, mock_db):
    """Vérifie la génération des miniatures statiques et la préservation de la configuration du profil."""
    from ankiforge.ui.style_engine import get_style_engine
    from script.capture_view import generate_layout_thumbnails

    engine = get_style_engine()
    LayoutManager.save_layout_id("default", "ide")
    pref_before = engine.get_appearance_preference("default")

    generated = generate_layout_thumbnails(output_dir=tmp_path, thumb_width=200, thumb_height=125)

    assert len(generated) == len(LayoutManager.LAYOUTS)
    for lid in LayoutManager.LAYOUTS:
        target = tmp_path / f"{lid}.png"
        assert target.is_file()
        assert target.stat().st_size > 0

    # Vérification stricte de non-altération du profil utilisateur
    assert LayoutManager.get_saved_layout_id("default") == "ide"
    pref_after = engine.get_appearance_preference("default")
    assert pref_after.family_id == pref_before.family_id
    assert pref_after.mode_source == pref_before.mode_source
