from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from ankiforge.services.cards.note_type_roles import (
    generate_markdown_table,
    get_standard_role_archetypes,
    is_markdown_table,
)
from ankiforge.ui.dialogs.note_type_role_guide_dialog import NoteTypeRoleGuideDialog


@pytest.mark.ui
def test_role_guide_dialog_initialization(qtbot: Any) -> None:
    dialog = NoteTypeRoleGuideDialog(model_fields=["Recto", "Verso"])
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() != ""
    assert not hasattr(dialog, "tab_widget") or dialog.findChild(type(dialog), "tab_widget") is None
    assert dialog.grid_table is not None
    assert dialog.grid_table.columnCount() == 3
    assert dialog.selected_directive is None
    assert dialog.preview_browser is not None
    assert dialog.width() <= 850
    assert dialog.height() <= 550


@pytest.mark.ui
def test_role_guide_dialog_archetype_chip_click_populates_grid_with_mapped_fields(qtbot: Any) -> None:
    dialog = NoteTypeRoleGuideDialog(model_fields=["Question", "Réponse"])
    qtbot.addWidget(dialog)

    # Vérifier que les chips des archétypes existent
    archetypes = get_standard_role_archetypes()
    assert len(dialog.archetype_chips) == len(archetypes)

    # Clic sur le chip Basique
    basic_chip = dialog.archetype_chips[0]
    qtbot.mouseClick(basic_chip, Qt.MouseButton.LeftButton)

    assert dialog.grid_table.rowCount() == 1
    assert dialog.grid_table.item(0, 0).text() == archetypes[0].name
    # Les champs doivent être mappés sur les champs du modèle (Question, Réponse)
    assert dialog.grid_table.item(0, 2).text() == "Question, Réponse"
    # L'aperçu Markdown est automatiquement actualisé
    preview_html = dialog.preview_browser.toHtml()
    assert archetypes[0].name in preview_html


@pytest.mark.ui
def test_role_guide_dialog_loads_existing_markdown_table(qtbot: Any) -> None:
    sample_table = generate_markdown_table(
        [
            {
                "concept": "Définition Grammaticale",
                "directive": "Identifier le participe passé.",
                "fields": "Texte, Regle",
            }
        ]
    )

    dialog = NoteTypeRoleGuideDialog(current_text=sample_table, model_fields=["Texte", "Regle"])
    qtbot.addWidget(dialog)

    assert dialog.grid_table.rowCount() == 1
    assert dialog.grid_table.item(0, 0).text() == "Définition Grammaticale"
    assert dialog.grid_table.item(0, 1).text() == "Identifier le participe passé."
    assert dialog.grid_table.item(0, 2).text() == "Texte, Regle"


@pytest.mark.ui
def test_role_guide_dialog_plain_text_banner_and_convert(qtbot: Any) -> None:
    plain_text = "Directives d'apprentissage pour la biologie cellulaire"
    dialog = NoteTypeRoleGuideDialog(current_text=plain_text, model_fields=["Cellule", "Fonction"])
    qtbot.addWidget(dialog)

    # Le bandeau de texte libre doit être visible
    assert dialog.plain_text_banner is not None
    assert dialog.plain_text_banner.isHidden() is False

    # Clic sur le bouton de conversion en règle
    assert dialog.btn_convert_plain_text is not None
    qtbot.mouseClick(dialog.btn_convert_plain_text, Qt.MouseButton.LeftButton)

    assert dialog.grid_table.rowCount() == 1
    assert dialog.grid_table.item(0, 1).text() == plain_text


@pytest.mark.ui
def test_role_guide_dialog_apply(qtbot: Any) -> None:
    dialog = NoteTypeRoleGuideDialog(model_fields=["Front", "Back"])
    qtbot.addWidget(dialog)

    # Clic sur le premier archétype
    qtbot.mouseClick(dialog.archetype_chips[0], Qt.MouseButton.LeftButton)

    with qtbot.waitSignal(dialog.accepted, timeout=1000):
        qtbot.mouseClick(dialog.btn_apply, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_directive is not None
    assert is_markdown_table(dialog.selected_directive) is True


@pytest.mark.ui
def test_role_guide_dialog_plain_text_replace_and_delegate(qtbot: Any) -> None:
    plain_text = "Directives d'apprentissage"
    fields = ["Front", "Back", "Extra"]
    dialog = NoteTypeRoleGuideDialog(current_text=plain_text, model_fields=fields)
    qtbot.addWidget(dialog)

    assert dialog.plain_text_banner.isHidden() is False
    # Clic sur remplacer
    qtbot.mouseClick(dialog.btn_replace_plain_text, Qt.MouseButton.LeftButton)
    assert dialog.plain_text_banner.isHidden() is True
    assert dialog.grid_table.rowCount() == 1

    # Vérifier la présence du délégué avec autocomplétion
    delegate = dialog.grid_table.itemDelegateForColumn(2)
    assert delegate is not None
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QStyleOptionViewItem

    editor = delegate.createEditor(dialog, QStyleOptionViewItem(), QModelIndex())
    assert editor.completer() is not None
    assert editor.completer().model().stringList() == fields
