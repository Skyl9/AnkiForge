"""
Tests unitaires et UI pour EditorToolbarWidget et ToolbarCustomizeDialog.
"""

from typing import Any

import pytest

from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.dialogs.toolbar_customize_dialog import ToolbarCustomizeDialog
from ankiforge.ui.widgets.editor_toolbar_widget import EditorToolbarWidget


@pytest.fixture(autouse=True)
def reset_toolbar_settings() -> Any:
    """Réinitialise les préférences de la barre d'outils pour chaque test."""
    SettingsService.set("editor/toolbar_hidden_actions", [])
    yield
    SettingsService.set("editor/toolbar_hidden_actions", [])


@pytest.mark.ui
def test_editor_toolbar_init_and_default_actions(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'initialisation de la toolbar et la présence du bouton trois points."""
    toolbar = EditorToolbarWidget()
    qtbot.addWidget(toolbar)

    assert toolbar.btn_customize is not None
    assert toolbar.btn_customize.toolTip() == "Personnaliser la barre d'outils..."

    # Vérifier que les actions par défaut sont présentes
    actions = toolbar.get_registered_actions()
    action_ids = [a.action_id for a in actions]
    assert "bold" in action_ids
    assert "italic" in action_ids
    assert "math" in action_ids
    assert "cloze" in action_ids
    assert "link" in action_ids
    assert "bullet_list" in action_ids


@pytest.mark.ui
def test_editor_toolbar_hide_and_show_action(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le masquage et l'affichage individuel d'un bouton d'action."""
    toolbar = EditorToolbarWidget()
    qtbot.addWidget(toolbar)
    toolbar.show()

    # Initialement visible
    assert toolbar.is_action_visible("bold") is True
    assert not toolbar._action_buttons["bold"].isHidden()

    # Masquer l'action
    toolbar.set_action_visible("bold", False)
    assert toolbar.is_action_visible("bold") is False
    assert toolbar._action_buttons["bold"].isHidden()
    assert "bold" in toolbar.get_hidden_action_ids()

    # Réafficher l'action
    toolbar.set_action_visible("bold", True)
    assert toolbar.is_action_visible("bold") is True
    assert not toolbar._action_buttons["bold"].isHidden()
    assert "bold" not in toolbar.get_hidden_action_ids()


@pytest.mark.ui
def test_editor_toolbar_batch_hide_and_reset(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le masquage par lot, tout afficher et réinitialiser."""
    toolbar = EditorToolbarWidget()
    qtbot.addWidget(toolbar)
    toolbar.show()

    toolbar.set_hidden_action_ids(["bold", "italic", "math"])
    assert set(toolbar.get_hidden_action_ids()) == {"bold", "italic", "math"}
    assert toolbar._action_buttons["bold"].isHidden()
    assert toolbar._action_buttons["italic"].isHidden()
    assert toolbar._action_buttons["math"].isHidden()
    assert not toolbar._action_buttons["cloze"].isHidden()

    # Tout afficher
    toolbar.show_all_actions()
    assert len(toolbar.get_hidden_action_ids()) == 0
    assert not toolbar._action_buttons["bold"].isHidden()
    assert not toolbar._action_buttons["italic"].isHidden()

    # Reset
    toolbar.set_hidden_action_ids(["cloze"])
    toolbar.reset_customization()
    assert len(toolbar.get_hidden_action_ids()) == 0


@pytest.mark.ui
def test_editor_toolbar_persistence(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la persistance des préférences de visibilité via SettingsService."""
    toolbar = EditorToolbarWidget()
    qtbot.addWidget(toolbar)

    toolbar.set_hidden_action_ids(["strikethrough", "code_block"])
    toolbar.save_customization_preferences()

    saved = SettingsService.get("editor/toolbar_hidden_actions", default=[])
    assert set(saved) == {"strikethrough", "code_block"}

    # Nouvelle instance chargeant les préférences sauvegardées
    toolbar2 = EditorToolbarWidget()
    qtbot.addWidget(toolbar2)
    assert toolbar2.is_action_visible("strikethrough") is False
    assert toolbar2.is_action_visible("code_block") is False
    assert toolbar2.is_action_visible("bold") is True


@pytest.mark.ui
def test_toolbar_customize_dialog(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le fonctionnement de ToolbarCustomizeDialog (cases à cocher, application)."""
    toolbar = EditorToolbarWidget()
    qtbot.addWidget(toolbar)

    dlg = ToolbarCustomizeDialog(
        actions=toolbar._actions,
        hidden_action_ids={"bold"},
        parent=None,
    )
    qtbot.addWidget(dlg)

    # Vérifier que "bold" est décoché et "italic" est coché
    assert not dlg._checkboxes["bold"].isChecked()
    assert dlg._checkboxes["italic"].isChecked()

    # Tout cocher
    dlg._select_all()
    assert dlg._checkboxes["bold"].isChecked()

    # Tout décocher
    dlg._unselect_all()
    assert not dlg._checkboxes["bold"].isChecked()
    assert not dlg._checkboxes["italic"].isChecked()

    # Rétablir par défaut
    dlg._reset_defaults()
    assert dlg._checkboxes["bold"].isChecked()
    assert dlg._checkboxes["italic"].isChecked()

    # Décocher "italic" et appliquer
    dlg._checkboxes["italic"].setChecked(False)

    applied_result: list[set[str]] = []
    dlg.customization_applied.connect(lambda hids: applied_result.append(hids))

    dlg.btn_apply.click()
    assert len(applied_result) == 1
    assert "italic" in applied_result[0]


@pytest.mark.ui
def test_editor_toolbar_adaptive_separators_and_menu(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Vérifie l'adaptation des séparateurs et l'ouverture du menu trois points."""
    from PySide6.QtWidgets import QFrame

    toolbar = EditorToolbarWidget()
    qtbot.addWidget(toolbar)
    toolbar.show()

    # Masquer tout le groupe texte ("bold", "italic", "underline", "strikethrough")
    toolbar.set_hidden_action_ids(["bold", "italic", "underline", "strikethrough"])

    # Le premier séparateur doit être masqué car aucun bouton visible ne le précède
    separators = [toolbar.tools_layout.itemAt(i).widget() for i in range(toolbar.tools_layout.count()) if isinstance(toolbar.tools_layout.itemAt(i).widget(), QFrame)]
    assert len(separators) >= 1
    first_sep = separators[0]
    assert first_sep.isHidden()

    # Tester la construction et le contenu du menu trois points
    menu = toolbar._open_customize_menu(exec_menu=False)
    assert menu is not None
    action_texts = [a.text() for a in menu.actions()]
    assert any("Actions masquées" in t for t in action_texts)
    assert any("Boutons visibles" in t for t in action_texts)
    assert any("Personnaliser la barre" in t for t in action_texts)
    assert any("Tout afficher" in t for t in action_texts)
    assert any("Rétablir par défaut" in t for t in action_texts)
