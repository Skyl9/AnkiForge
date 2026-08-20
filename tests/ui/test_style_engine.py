"""
Tests unitaires pour le Moteur de Style Centralisé (StyleEngine) d'AnkiForge.
"""

from PySide6.QtWidgets import QApplication

from ankiforge.ui.components.buttons import DangerButton, PrimaryButton, SecondaryButton
from ankiforge.ui.style_engine import (
    CYBER_GLASS,
    EMERALD_DASHBOARD,
    JETBRAINS_DARK,
    MACOS_SLATE,
    ThemeProfile,
    get_style_engine,
)
from ankiforge.ui.theme import DesignTokens


def test_style_engine_singleton_and_builtin_themes():
    """Vérifie l'accès au singleton et la présence des 4 thèmes officiels."""
    engine = get_style_engine()
    themes = engine.get_available_themes()
    theme_ids = [t.id for t in themes]

    assert "ide" in theme_ids
    assert "macos" in theme_ids
    assert "dashboard" in theme_ids
    assert "glassmorphism" in theme_ids


def test_style_engine_generate_stylesheet():
    """Vérifie que la compilation QSS génère les sélecteurs sémantiques indispensables."""
    engine = get_style_engine()
    qss = engine.generate_stylesheet(JETBRAINS_DARK)

    # Vérification des rôles sémantiques
    assert 'QPushButton[role="primary"]' in qss
    assert 'QPushButton[role="secondary"]' in qss
    assert 'QPushButton[role="danger"]' in qss
    assert 'QPushButton[role="icon"]' in qss
    assert 'QFrame[card-style="elevated"]' in qss
    assert JETBRAINS_DARK.accent_primary in qss


def test_style_engine_apply_theme(qtbot):
    """Vérifie que l'application d'un thème met à jour les DesignTokens et la palette Qt."""
    engine = get_style_engine()
    app = QApplication.instance()

    # 1. Appliquer macOS
    engine.apply_theme("macos", app)
    assert engine.current_theme.id == "macos"
    assert DesignTokens.ACCENT_PRIMARY == MACOS_SLATE.accent_primary
    assert DesignTokens.RADIUS_SM == MACOS_SLATE.radius_sm

    # 2. Appliquer Dashboard (Emerald)
    engine.apply_theme("dashboard", app)
    assert engine.current_theme.id == "dashboard"
    assert DesignTokens.ACCENT_PRIMARY == EMERALD_DASHBOARD.accent_primary

    # 3. Appliquer Glassmorphism (Cyber Amethyst)
    engine.apply_theme("glassmorphism", app)
    assert engine.current_theme.id == "glassmorphism"
    assert DesignTokens.ACCENT_PRIMARY == CYBER_GLASS.accent_primary

    # 4. Revenir à JetBrains Dark
    engine.apply_theme("ide", app)
    assert engine.current_theme.id == "ide"
    assert DesignTokens.ACCENT_PRIMARY == JETBRAINS_DARK.accent_primary


def test_semantic_buttons_properties(qtbot):
    """Vérifie que les composants de boutons appliquent correctement leurs propriétés sémantiques."""
    btn_p = PrimaryButton("Valider")
    btn_s = SecondaryButton("Annuler")
    btn_d = DangerButton("Supprimer")

    qtbot.addWidget(btn_p)
    qtbot.addWidget(btn_s)
    qtbot.addWidget(btn_d)

    assert btn_p.property("role") == "primary"
    assert btn_s.property("role") == "secondary"
    assert btn_d.property("role") == "danger"


def test_custom_theme_registration():
    """Vérifie l'enregistrement d'un thème tiers personnalisé."""
    engine = get_style_engine()
    custom = ThemeProfile(
        id="custom_nord",
        name="Nord Frost",
        description="Thème arctique bleuté.",
        bg_main="#2e3440",
        bg_sidebar="#2e3440",
        bg_panel="#3b4252",
        bg_input="#434c5e",
        bg_hover="#4c566a",
        bg_active="rgba(136, 192, 208, 0.2)",
        accent_primary="#88c0d0",
        accent_hover="#81a1c1",
        accent_glow="rgba(136, 192, 208, 0.4)",
        text_primary="#eceff4",
        text_secondary="#d8dee9",
        text_muted="#e5e9f0",
        border_color="#4c566a",
        border_light="rgba(255, 255, 255, 0.05)",
        border_focus="#88c0d0",
        color_blue="#88c0d0",
        color_green="#a3be8c",
        color_yellow="#ebcb8b",
        color_red="#bf616a",
        color_purple="#b48ead",
        radius_sm=4,
        radius_md=8,
        radius_lg=12,
    )

    engine.register_theme(custom)
    assert engine.get_theme("custom_nord").name == "Nord Frost"


def test_dark_and_light_modes(qtbot):
    """Vérifie le filtrage et l'application des thèmes clairs et sombres."""
    engine = get_style_engine()
    app = QApplication.instance()

    dark_themes = engine.get_available_themes(mode="dark")
    light_themes = engine.get_available_themes(mode="light")

    assert len(dark_themes) >= 12
    assert len(light_themes) >= 12
    assert all(t.is_dark for t in dark_themes)
    assert all(not t.is_dark for t in light_themes)

    # Appliquer un thème clair
    engine.apply_theme("jetbrains_light", app)
    assert not engine.current_theme.is_dark
    assert not DesignTokens.is_dark_mode()
    assert DesignTokens.TEXT_PRIMARY == "#1f2328"
    assert DesignTokens.BG_MAIN == "#f5f6f8"

    # Revenir à JetBrains Dark
    engine.apply_theme("ide", app)
    assert engine.current_theme.is_dark
    assert DesignTokens.is_dark_mode()


def test_theme_families(qtbot):
    """Vérifie les 12 familles de thèmes bivalentes et le basculement direct de mode."""
    engine = get_style_engine()
    app = QApplication.instance()

    families = engine.get_theme_families()
    assert len(families) == 12

    # Vérifier que chaque famille possède son pendant sombre et son pendant clair
    for fam in families:
        assert fam.dark_theme.is_dark
        assert not fam.light_theme.is_dark
        resolved = engine.get_family_for_theme(fam.dark_theme.id)
        assert resolved is not None
        assert resolved.id == fam.id

    # Test set_color_mode("light") et set_color_mode("dark")
    engine.apply_theme("macos", app)
    light_macos = engine.set_color_mode("light", app)
    assert light_macos.id == "macos_light"
    assert not DesignTokens.is_dark_mode()

    dark_macos = engine.set_color_mode("dark", app)
    assert dark_macos.id == "macos"
    assert DesignTokens.is_dark_mode()


def test_toggle_color_mode(qtbot):
    """Vérifie la bascule intelligente entre mode sombre et mode clair."""
    engine = get_style_engine()
    app = QApplication.instance()

    engine.apply_theme("ide", app)
    assert DesignTokens.is_dark_mode()

    # Basculer vers Clair
    light_theme = engine.toggle_color_mode(app)
    assert not light_theme.is_dark
    assert not DesignTokens.is_dark_mode()
    assert light_theme.id == "jetbrains_light"

    # Basculer vers Sombre
    dark_theme = engine.toggle_color_mode(app)
    assert dark_theme.is_dark
    assert DesignTokens.is_dark_mode()
    assert dark_theme.id == "ide"


def test_force_global_repolish_and_live_signal(qtbot):
    """Vérifie que force_global_repolish et theme_changed s'exécutent sans erreur sur des widgets actifs."""
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
    from ankiforge.ui.components.buttons import IconButton, PrimaryButton

    engine = get_style_engine()
    app = QApplication.instance()

    widget = QWidget()
    layout = QVBoxLayout(widget)
    lbl = QLabel("Test")
    btn_icon = IconButton("bell")
    btn_primary = PrimaryButton("Action")
    layout.addWidget(lbl)
    layout.addWidget(btn_icon)
    layout.addWidget(btn_primary)
    qtbot.addWidget(widget)

    received_profiles = []
    engine.theme_changed.connect(lambda p: received_profiles.append(p.id))

    engine.apply_theme("dracula_official", app)
    assert "dracula_official" in received_profiles
    assert DesignTokens.ACTIVE_THEME_ID == "dracula_official"

    engine.set_color_mode("light", app)
    assert "dracula_light" in received_profiles
    assert DesignTokens.ACTIVE_THEME_ID == "dracula_light"
