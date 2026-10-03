"""
Tests unitaires pour le Moteur de Style Centralisé (StyleEngine) d'AnkiForge.
"""

import dataclasses
import re

import pytest
from PySide6.QtWidgets import QApplication

from ankiforge.ui.components.buttons import DangerButton, PrimaryButton, SecondaryButton
from ankiforge.ui.style_engine import (
    BUILTIN_THEMES,
    CYBER_GLASS,
    EMERALD_DASHBOARD,
    JETBRAINS_DARK,
    JETBRAINS_LIGHT,
    MACOS_SLATE,
    ThemeProfile,
    get_style_engine,
)
from ankiforge.ui.theme import DesignTokens

pytestmark = pytest.mark.ui

COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)")
SECONDARY_ROLE_TOKENS = (
    "bg_input",
    "bg_hover",
    "bg_panel",
    "bg_active",
    "text_primary",
    "text_muted",
    "border_color",
    "border_light",
    "border_focus",
    "accent_primary",
)
"""Vocabulaire de tokens du rôle `secondary` : les seules couleurs que sa règle a le droit de citer."""


def qss_rule(qss: str, selector: str) -> str:
    """Retourne le corps de la première règle QSS `selector { … }` (sélecteurs d'attributs inclus)."""
    match = re.search(re.escape(selector) + r"\s*\{(?P<body>[^{}]*)\}", qss)
    assert match is not None, f"Règle QSS absente : {selector}"
    return match.group("body")


def parse_color(color: str) -> tuple[tuple[int, int, int], float]:
    """Décompose une couleur QSS (`#rgb`, `#rrggbb`, `rgb()`, `rgba()`) en canaux et alpha."""
    value = color.strip()
    if value.startswith("#"):
        digits = value.lstrip("#")
        if len(digits) == 3:
            digits = "".join(char * 2 for char in digits)
        return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)), 1.0
    match = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", value)
    assert match is not None, f"Couleur QSS non analysable : {color!r}"
    alpha = float(match.group(4)) if match.group(4) is not None else 1.0
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))), alpha


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Luminance relative WCAG d'un triplet de canaux 0-255."""
    linear = []
    for channel in rgb:
        value = channel / 255
        linear.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def wcag_ratio(foreground: str, background: str) -> float:
    """Rapport de contraste WCAG, la couleur de premier plan étant composée sur son fond.

    Qt peint un `rgba()` translucide *sur* le fond avant rasterisation : sans cette composition,
    un `border_light` a 4 % d'opacité aurait le contraste de son alpha et semblerait
    correct, alors qu'il est invisible : l'erreur exacte que ce test doit attraper.
    """
    fg_rgb, fg_alpha = parse_color(foreground)
    bg_rgb, _ = parse_color(background)
    composited = tuple(round(channel * fg_alpha + backdrop * (1 - fg_alpha)) for channel, backdrop in zip(fg_rgb, bg_rgb, strict=True))
    first, second = relative_luminance(composited), relative_luminance(bg_rgb)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


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


@pytest.mark.parametrize("theme", [JETBRAINS_DARK, JETBRAINS_LIGHT], ids=["dark", "light"])
def test_secondary_button_rest_contour_uses_the_documented_border_token(theme):
    """Le contour au repos est le token `border_color` de DESIGN.md, jamais `border_light`.

    `border_light` est un liseré décoratif (4 % de blanc en sombre, quasi blanc en clair) :
    il mesure 1,0:1 contre le panneau sur plusieurs thèmes, donc un contour *invisible*.
    `border_color` est le contour déclaré pour les boutons secondaires et le contour de tous
    les autres contrôles interactifs (champs, cases, combos, curseurs).
    """
    qss = get_style_engine().generate_stylesheet(theme)

    rest = qss_rule(qss, 'QPushButton[role="secondary"]')

    assert f"border: 1px solid {theme.border_color}" in rest
    # `border_light` ne peut plus porter le contour : uniquement l'arête haute en relief.
    assert f"border: 1px solid {theme.border_light}" not in rest
    assert f"border-color: {theme.border_light}" not in rest

    disabled = qss_rule(qss, 'QPushButton[role="secondary"]:disabled')
    assert f"border-color: {theme.border_color}" in disabled

    primary_disabled = qss_rule(qss, 'QPushButton[role="primary"]:disabled')
    assert f"border-color: {theme.border_color}" in primary_disabled


@pytest.mark.parametrize("theme", [JETBRAINS_DARK, JETBRAINS_LIGHT], ids=["dark", "light"])
def test_secondary_button_highlights_its_contour_on_hover_and_focus(theme):
    """Survol et focus accentuent le contour avec l'accent et le token de focus dédié."""
    qss = get_style_engine().generate_stylesheet(theme)

    hover = qss_rule(qss, 'QPushButton[role="secondary"]:hover')
    assert f"border: 1.5px solid {theme.accent_primary}" in hover

    focus = qss_rule(qss, 'QPushButton[role="secondary"]:focus')
    assert f"border: 2px solid {theme.border_focus}" in focus


def test_secondary_button_focus_contour_follows_the_border_focus_token():
    """Le focus suit `border_focus` — pas `accent_primary` — pour coller aux champs de saisie.

    Les thèmes intégrés définissent `border_focus` égal à `accent_primary`, ce qui masque la
    différence dans le QSS : un profil tiers où les deux divergent prouve le bon câblage.
    """
    engine = get_style_engine()
    custom = dataclasses.replace(JETBRAINS_DARK, id="custom_focus_probe", border_focus="#ff00aa")

    qss = engine.generate_stylesheet(custom)
    focus = qss_rule(qss, 'QPushButton[role="secondary"]:focus')

    assert "border: 2px solid #ff00aa" in focus
    assert f"border: 2px solid {custom.accent_primary}" not in focus


@pytest.mark.parametrize("theme", [JETBRAINS_DARK, JETBRAINS_LIGHT], ids=["dark", "light"])
def test_secondary_button_rule_declares_no_hardcoded_color(theme):
    """Chaque couleur de la règle `secondary` est la valeur résolue d'un token qu'elle cite.

    Vérifier « est-ce une couleur du thème ? » serait trop laxiste : une substitution par un
    autre token de la palette passerait le test. Le seuil retenu est donc le vocabulaire du rôle
    (surface, texte, contour, accent) : une couleur en dur, comme un token hors sujet — un
    `color_red` de suppression ou un `syntax_tag` d'éditeur — sont tous deux refusés.
    """
    qss = get_style_engine().generate_stylesheet(theme)
    rest = qss_rule(qss, 'QPushButton[role="secondary"]')

    allowed = {getattr(theme, name) for name in SECONDARY_ROLE_TOKENS}
    literals = set(COLOR_LITERAL.findall(rest))

    assert literals, "La règle doit bien porter des couleurs"
    assert literals <= allowed, f"Couleurs hors vocabulaire du rôle : {sorted(literals - allowed)}"


def test_secondary_button_rest_contour_stays_visible_in_every_builtin_theme():
    """Le contour au repos reste détaché du fond dans *tous* les thèmes intégrés (AC1).

    C'est le critère d'acceptation qui ne se vérifie pas en lisant du QSS : il faut comparer le
    contraste une fois la couleur *composée* sur le panneau, comme Qt le fait au rendu. Le seuil
    de 1,15:1 est le plancher observé sur les thèmes intégrés (Solarized Dark) et reste
    délibérément bas : aucun thème ne fournit de token de contour atteignant 3:1 (AA sur un
    composant non textuel), et `border_color` est déjà la valeur de tous les autres contrôles
    interactifs. Le test verrouille donc surtout le non-retour à `border_light` (1,00:1 à 1,24:1,
    soit invisible sur un fond de panneau).
    """
    for theme in BUILTIN_THEMES.values():
        border = wcag_ratio(theme.border_color, theme.bg_panel)
        faint = wcag_ratio(theme.border_light, theme.bg_panel)
        assert border >= 1.15, f"{theme.id}: contour {theme.border_color} invisible sur {theme.bg_panel} ({border:.2f}:1)"
        assert border >= faint, f"{theme.id}: le contour ({border:.2f}:1) ne vaut pas mieux que border_light ({faint:.2f}:1)"


def test_style_engine_apply_theme(qtbot):
    """Vérifie que l'application d'un thème met à jour les DesignTokens et la palette Qt."""
    engine = get_style_engine()
    app = QApplication.instance()

    # 1. Appliquer macOS
    engine.apply_theme("macos", app)
    assert engine.current_theme.id == "macos"
    assert MACOS_SLATE.accent_primary == DesignTokens.ACCENT_PRIMARY
    assert MACOS_SLATE.radius_sm == DesignTokens.RADIUS_SM

    # 2. Appliquer Dashboard (Emerald)
    engine.apply_theme("dashboard", app)
    assert engine.current_theme.id == "dashboard"
    assert EMERALD_DASHBOARD.accent_primary == DesignTokens.ACCENT_PRIMARY

    # 3. Appliquer Glassmorphism (Cyber Amethyst)
    engine.apply_theme("glassmorphism", app)
    assert engine.current_theme.id == "glassmorphism"
    assert CYBER_GLASS.accent_primary == DesignTokens.ACCENT_PRIMARY

    # 4. Revenir à JetBrains Dark
    engine.apply_theme("ide", app)
    assert engine.current_theme.id == "ide"
    assert JETBRAINS_DARK.accent_primary == DesignTokens.ACCENT_PRIMARY


def test_semantic_buttons_properties(qtbot):
    """Vérifie que les composants de boutons appliquent correctement leurs propriétés sémantiques et animations."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QEnterEvent

    from ankiforge.ui.components.buttons import IconButton

    btn_p = PrimaryButton("Valider")
    btn_s = SecondaryButton("Annuler")
    btn_d = DangerButton("Supprimer")
    btn_i = IconButton("ph.trash")

    qtbot.addWidget(btn_p)
    qtbot.addWidget(btn_s)
    qtbot.addWidget(btn_d)
    qtbot.addWidget(btn_i)

    assert btn_p.property("role") == "primary"
    assert btn_s.property("role") == "secondary"
    assert btn_d.property("role") == "danger"
    assert btn_i.property("role") == "icon"

    assert btn_p.testAttribute(Qt.WidgetAttribute.WA_Hover)
    assert btn_s.testAttribute(Qt.WidgetAttribute.WA_Hover)
    assert btn_d.testAttribute(Qt.WidgetAttribute.WA_Hover)
    assert btn_i.testAttribute(Qt.WidgetAttribute.WA_Hover)

    # Vérification des animations d'ombres au survol
    enter_ev = QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
    btn_s.enterEvent(enter_ev)
    assert btn_s.anim.endValue() == btn_s.hover_blur

    leave_ev = QEvent(QEvent.Type.Leave)
    btn_s.leaveEvent(leave_ev)
    assert btn_s.anim.endValue() == btn_s.default_blur


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
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    from ankiforge.ui.components.buttons import IconButton, PrimaryButton

    engine = get_style_engine()
    app = QApplication.instance()

    widget = QWidget()
    layout = QVBoxLayout(widget)
    lbl = QLabel("Test")
    btn_icon = IconButton("ph.bell")
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


def test_button_shadow_and_blur_animation_without_target_issue(qtbot):
    """Vérifie que ré-appliquer apply_shadow met à jour l'effet existant in-place et ne casse pas l'animation."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    from ankiforge.ui.components.buttons import DangerButton, IconButton, PrimaryButton, SecondaryButton
    from ankiforge.ui.components.inputs import GlowLineEdit
    from ankiforge.ui.theme import apply_shadow

    btn = PrimaryButton("Lancer Batch")
    qtbot.addWidget(btn)
    btn.show()

    initial_effect = btn.graphicsEffect()
    assert isinstance(initial_effect, QGraphicsDropShadowEffect)
    assert btn.anim.targetObject() is initial_effect

    # Simuler le changement d'état pendant le batch (bouton rouge Arrêter)
    apply_shadow(btn, blur=16, offset_y=0, color="rgba(239, 68, 68, 0.45)")
    updated_effect = btn.graphicsEffect()
    # L'effet a été mis à jour in-place, pas remplacé par un nouvel objet détruisant la cible
    assert updated_effect is initial_effect
    assert btn.anim.targetObject() is initial_effect
    assert updated_effect.blurRadius() == 16

    # Simuler survol souris
    enter_ev = QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5))
    btn.enterEvent(enter_ev)
    assert btn.anim.state() == btn.anim.State.Running

    leave_ev = QEvent(QEvent.Type.Leave)
    btn.leaveEvent(leave_ev)

    # Vérifier également SecondaryButton, DangerButton, IconButton et GlowLineEdit
    for widget in (SecondaryButton("Sec"), DangerButton("Danger"), IconButton("ph.play"), GlowLineEdit()):
        qtbot.addWidget(widget)
        apply_shadow(widget, blur=14, offset_y=2, color="rgba(0,0,0,0.3)")
        assert widget.anim.targetObject() is widget.graphicsEffect()
        widget.enterEvent(enter_ev)
        widget.leaveEvent(leave_ev)


@pytest.mark.slow
def test_all_builtin_themes_compilation_and_application(qtbot):
    """Vérifie que la compilation QSS et l'application s'exécutent avec succès sur TOUS les thèmes intégrés."""
    from ankiforge.ui.style_engine import BUILTIN_THEMES

    engine = get_style_engine()
    app = QApplication.instance()

    for theme_id, theme in BUILTIN_THEMES.items():
        qss = engine.generate_stylesheet(theme)
        assert len(qss) > 100
        engine.apply_theme(theme_id, app)
        assert engine.current_theme.id == theme.id
