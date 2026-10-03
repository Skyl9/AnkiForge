"""Tests de régression pour les animations de flou (blurRadius) sur les boutons et inputs.

Vérifie l'absence de warning Qt 'without target' lors des changements d'état,
des restylages dynamiques en BatchView et du cycle de vie des widgets.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

from ankiforge.ui.components import ActionButton, DangerButton, IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.style_engine import JETBRAINS_DARK, JETBRAINS_LIGHT, get_style_engine
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.views.batch_view.view import BatchView

pytestmark = pytest.mark.ui


@pytest.fixture
def qt_warning_interceptor() -> list[str]:
    """Capture les messages de warning Qt émis durant le test."""
    captured: list[str] = []

    def _handler(_msg_type: Any, _context: Any, message: str) -> None:
        if "without target" in message and "blurRadius" in message:
            captured.append(message)

    qInstallMessageHandler(_handler)
    yield captured
    qInstallMessageHandler(None)


def test_button_animation_parenting(qtbot: Any) -> None:
    """Vérifie que QPropertyAnimation a bien le bouton comme parent Qt pour éviter les orphelins."""
    for btn_cls in (PrimaryButton, SecondaryButton, DangerButton, IconButton):
        btn = btn_cls("ph.x") if btn_cls is IconButton else btn_cls("Test")
        qtbot.addWidget(btn)
        assert hasattr(btn, "anim"), f"{btn_cls.__name__} doit avoir un attribut anim"
        assert btn.anim.parent() is btn, f"{btn_cls.__name__}.anim doit avoir le bouton comme parent Qt"

    glow_input = GlowLineEdit()
    qtbot.addWidget(glow_input)
    assert hasattr(glow_input, "anim")
    assert glow_input.anim.parent() is glow_input, "GlowLineEdit.anim doit avoir glow_input comme parent Qt"


def test_apply_shadow_maintains_animation_target_on_new_effect(qtbot: Any, qt_warning_interceptor: list[str]) -> None:
    """Vérifie que apply_shadow reconnecte anim.targetObject même si un nouvel effet est créé."""
    btn = PrimaryButton("Lancer")
    qtbot.addWidget(btn)

    # Réinitialisation forcée de l'effet pour forcer la branche shadow = QGraphicsDropShadowEffect
    btn.setGraphicsEffect(None)
    apply_shadow(btn, blur=16, offset_y=0)

    # anim.targetObject() doit pointer immédiatement sur le nouvel effet
    effect = btn.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert btn.anim.targetObject() is effect, "anim.targetObject() doit être synchronisé avec le nouvel effet"

    # Déclencher le survol et vérifier l'absence d'avertissement
    btn._start_blur_anim(btn.hover_blur)
    btn._start_blur_anim(btn.default_blur)

    assert not qt_warning_interceptor, f"Avertissements interceptés : {qt_warning_interceptor}"


def test_start_blur_anim_safe_when_effect_cleared(qtbot: Any, qt_warning_interceptor: list[str]) -> None:
    """Vérifie que _start_blur_anim ne déclenche pas start() si la cible est nulle."""
    btn = SecondaryButton("Option")
    qtbot.addWidget(btn)

    btn.setGraphicsEffect(None)
    # Tenter de démarrer l'animation avec un effet absent
    btn._start_blur_anim(12)

    assert not qt_warning_interceptor, f"Avertissements interceptés : {qt_warning_interceptor}"


def test_batch_view_start_button_hover_and_state_toggle_no_warnings(qtbot: Any, qt_warning_interceptor: list[str], mock_db: Any) -> None:
    """Vérifie que le basculement d'état en cours (rouge) et le survol de btn_start_pipeline ne lèvent aucun warning."""
    view = BatchView(ai_manager=None)
    qtbot.addWidget(view)
    view.show()

    # Survol initial (état vert)
    view.btn_start_pipeline._start_blur_anim(view.btn_start_pipeline.hover_blur)
    view.btn_start_pipeline._start_blur_anim(view.btn_start_pipeline.default_blur)

    # Basculement en état "En cours" (restylage rouge dans _set_running_ui_state)
    view._set_running_ui_state(True)
    view.btn_start_pipeline._start_blur_anim(view.btn_start_pipeline.hover_blur)
    view.btn_start_pipeline._start_blur_anim(view.btn_start_pipeline.default_blur)

    # Retour à l'état initial
    view._set_running_ui_state(False)
    view.btn_start_pipeline._start_blur_anim(view.btn_start_pipeline.hover_blur)
    view.btn_start_pipeline._start_blur_anim(view.btn_start_pipeline.default_blur)

    assert not qt_warning_interceptor, f"Avertissements interceptés pendant le cycle de BatchView : {qt_warning_interceptor}"


def shadow_color() -> QColor:
    """Le token d'ombre du thème actif, lu dans `DesignTokens` et converti en `QColor`.

    `DesignTokens.SHADOW_COLOR` est une chaîne CSS `rgba(...)` que `QColor` ne sait pas lire
    (d'où le dissecteur de `apply_shadow`) : le test relit le token plutôt que de recopier 0.45.
    """
    match = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", DesignTokens.SHADOW_COLOR)
    assert match is not None, f"Token d'ombre illisible : {DesignTokens.SHADOW_COLOR!r}"
    red, green, blue, alpha = match.groups()
    return QColor(int(red), int(green), int(blue), int(float(alpha) * 255))


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: SecondaryButton("Parcourir"), id="secondary"),
        pytest.param(lambda: ActionButton("ph.folder-open", "Parcourir"), id="action"),
    ],
)
def test_secondary_button_relief_shadow_follows_the_active_theme(qtbot: Any, build: Callable[[], SecondaryButton]) -> None:
    """Le halo de relief est re-teinté au changement de thème, sans perdre sa cible d'animation.

    Le halo est posé une fois à la construction depuis `DesignTokens.SHADOW_COLOR` : sans
    `refresh_theme`, un bouton construit en sombre conserve un halo opaque après un passage en
    thème clair, où le token vaut 12 % d'opacité — un halo gris sombre sur fond clair.
    """
    engine = get_style_engine()
    previous = engine.current_theme
    btn = build()
    qtbot.addWidget(btn)

    try:
        DesignTokens.apply_theme_profile(JETBRAINS_DARK)
        btn.refresh_theme(JETBRAINS_DARK)
        dark_color = btn.graphicsEffect().color()
        expected_dark = shadow_color()

        DesignTokens.apply_theme_profile(JETBRAINS_LIGHT)
        btn.refresh_theme(JETBRAINS_LIGHT)
        light_color = btn.graphicsEffect().color()
        expected_light = shadow_color()
    finally:
        DesignTokens.apply_theme_profile(previous)

    assert dark_color == expected_dark, "Le halo doit prendre la couleur d'ombre du thème actif"
    assert light_color == expected_light, "Le halo doit prendre la couleur d'ombre du thème actif"
    assert dark_color.alpha() > light_color.alpha(), "Le halo clair doit être plus discret que le halo sombre"
    assert btn.anim.targetObject() is btn.graphicsEffect(), "La cible de l'animation doit survivre au re-tintage"
