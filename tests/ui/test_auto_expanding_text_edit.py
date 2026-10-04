"""Tests unitaires et UI pour AutoExpandingTextEdit."""

from typing import Any

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QWheelEvent

from ankiforge.ui.components.inputs import AutoExpandingTextEdit
from ankiforge.ui.style_engine.theme_profile import ThemeProfile
from ankiforge.ui.theme import DesignTokens

pytestmark = pytest.mark.ui


def test_auto_expanding_text_edit_init_and_defaults(qtbot: Any) -> None:
    """Vérifie l'initialisation et l'application des tokens de design par défaut."""
    edit = AutoExpandingTextEdit(placeholder="Description test...")
    qtbot.addWidget(edit)

    assert edit.placeholderText() == "Description test..."
    assert edit.min_height == DesignTokens.INPUT_AUTO_EXPAND_MIN_HEIGHT
    assert edit.max_height == DesignTokens.INPUT_AUTO_EXPAND_MAX_HEIGHT
    assert edit.height() == DesignTokens.INPUT_AUTO_EXPAND_MIN_HEIGHT
    assert edit.tabChangesFocus() is True
    assert edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert edit.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_auto_expanding_text_edit_growth_on_content(qtbot: Any) -> None:
    """Vérifie que le champ grandit avec son contenu à l'édition."""
    edit = AutoExpandingTextEdit(min_height=54, max_height=160)
    qtbot.addWidget(edit)
    edit.resize(300, 54)
    edit.show()

    initial_height = edit.height()
    assert initial_height == 54

    # Ajout de texte multiligne
    edit.setPlainText("Ligne 1\nLigne 2\nLigne 3\nLigne 4\nLigne 5")
    qtbot.wait(20)

    expanded_height = edit.height()
    assert expanded_height > initial_height
    assert expanded_height < 160
    assert edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_auto_expanding_text_edit_clamping_to_max_height_and_scroll(qtbot: Any) -> None:
    """Vérifie que la hauteur est plafonnée à max_height et que l'ascenseur s'active."""
    edit = AutoExpandingTextEdit(min_height=54, max_height=160)
    qtbot.addWidget(edit)
    edit.resize(300, 54)
    edit.show()

    # Ajout d'un texte très long qui dépasse 160px
    long_text = "\n".join(f"Ligne de description numéro {i}" for i in range(25))
    edit.setPlainText(long_text)
    qtbot.wait(20)

    assert edit.height() == 160
    assert edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_auto_expanding_text_edit_shrink_on_deletion(qtbot: Any) -> None:
    """Vérifie que la hauteur rétrécit lorsque des lignes sont supprimées."""
    edit = AutoExpandingTextEdit(min_height=54, max_height=160)
    qtbot.addWidget(edit)
    edit.resize(300, 54)
    edit.show()

    # Remplissage puis réduction
    edit.setPlainText("\n".join(f"Ligne {i}" for i in range(15)))
    qtbot.wait(20)
    assert edit.height() == 160

    # Retour à une seule ligne
    edit.setPlainText("Une seule ligne restante.")
    qtbot.wait(20)
    assert edit.height() == 54
    assert edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_auto_expanding_text_edit_qlineedit_compatibility_api(qtbot: Any) -> None:
    """Vérifie la compatibilité d'interface avec QLineEdit (text, setText, setCursorPosition, cursorPosition)."""
    edit = AutoExpandingTextEdit(placeholder="Test")
    qtbot.addWidget(edit)

    edit.setText("Contenu de test")
    assert edit.text() == "Contenu de test"
    assert edit.toPlainText() == "Contenu de test"

    edit.setCursorPosition(4)
    assert edit.cursorPosition() == 4

    # Dépassement borné
    edit.setCursorPosition(999)
    assert edit.cursorPosition() == len("Contenu de test")


def test_auto_expanding_text_edit_dynamic_bounds_and_theme_refresh(qtbot: Any) -> None:
    """Vérifie le changement dynamique des bornes et l'actualisation de thème."""
    edit = AutoExpandingTextEdit()
    qtbot.addWidget(edit)

    edit.set_min_height(60)
    assert edit.min_height == 60
    assert edit.height() >= 60

    edit.set_max_height(200)
    assert edit.max_height == 200

    # Profil personnalisé
    mock_profile = ThemeProfile(
        id="custom_test",
        name="Test",
        description="Theme de test",
        bg_main="#000",
        bg_sidebar="#000",
        bg_panel="#000",
        bg_input="#000",
        bg_hover="#000",
        bg_active="#000",
        accent_primary="#6366f1",
        accent_hover="#4f46e5",
        accent_glow="",
        text_primary="#fff",
        text_secondary="#aaa",
        text_muted="#666",
        border_color="#333",
        border_light="#222",
        border_focus="#6366f1",
        color_blue="#00f",
        color_green="#0f0",
        color_yellow="#ff0",
        color_red="#f00",
        color_purple="#80f",
        radius_sm=6,
        radius_md=10,
        radius_lg=16,
        input_auto_expand_min_height=48,
        input_auto_expand_max_height=180,
    )

    # Edit sans surcharge personnalisée
    default_edit = AutoExpandingTextEdit()
    qtbot.addWidget(default_edit)
    default_edit.refresh_theme(mock_profile)
    assert default_edit.min_height == 48
    assert default_edit.max_height == 180


def test_auto_expanding_text_edit_wheel_event_delegation(qtbot: Any) -> None:
    """Vérifie que l'événement molette est ignoré quand le scrollbar est inactif (anti-piège)."""
    edit = AutoExpandingTextEdit(min_height=54, max_height=160)
    qtbot.addWidget(edit)
    edit.resize(300, 54)
    edit.show()

    # Texte court : scrollbar désactivée
    edit.setPlainText("Court texte")
    qtbot.wait(20)
    assert edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    event = QWheelEvent(
        QPoint(10, 10),
        QPoint(10, 10),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    edit.wheelEvent(event)
    assert not event.isAccepted()
