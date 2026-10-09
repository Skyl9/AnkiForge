from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPushButton

from ankiforge.services.cards.note_type_roles import get_standard_role_archetypes
from ankiforge.ui.dialogs.note_type_role_guide_dialog import NoteTypeRoleGuideDialog


@pytest.mark.ui
def test_role_guide_dialog_initialization(qtbot: Any) -> None:
    dialog = NoteTypeRoleGuideDialog()
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() != ""
    assert dialog.table is not None

    archetypes = get_standard_role_archetypes()
    assert dialog.table.rowCount() == len(archetypes)
    assert dialog.table.columnCount() == 5
    assert dialog.selected_directive is None
    assert dialog.selected_archetype is None


@pytest.mark.ui
def test_role_guide_dialog_apply_button(qtbot: Any) -> None:
    dialog = NoteTypeRoleGuideDialog()
    qtbot.addWidget(dialog)

    # Le bouton Appliquer de la 1ère ligne (Basic)
    apply_btn = dialog.get_apply_button_at_row(0)
    assert isinstance(apply_btn, QPushButton)

    with qtbot.waitSignal(dialog.accepted, timeout=1000):
        qtbot.mouseClick(apply_btn, Qt.MouseButton.LeftButton)

    archetypes = get_standard_role_archetypes()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_archetype is not None
    assert dialog.selected_archetype.archetype_id == archetypes[0].archetype_id
    assert dialog.selected_directive == archetypes[0].ai_heuristic_directive


@pytest.mark.ui
def test_role_guide_dialog_filter(qtbot: Any) -> None:
    dialog = NoteTypeRoleGuideDialog()
    qtbot.addWidget(dialog)

    # Saisie d'une recherche dans le champ filtre
    assert hasattr(dialog, "search_input")
    qtbot.keyClicks(dialog.search_input, "KaTeX")

    visible_rows = [r for r in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(r)]
    assert len(visible_rows) == 1

    math_archetype = dialog.get_archetype_at_row(visible_rows[0])
    assert math_archetype is not None
    assert math_archetype.archetype_id == "math_katex"


@pytest.mark.ui
def test_role_guide_dialog_customize_archetype_loads_builder(qtbot: Any) -> None:
    dialog = NoteTypeRoleGuideDialog()
    qtbot.addWidget(dialog)

    archetype = get_standard_role_archetypes()[0]
    dialog.load_archetype_into_builder(archetype)

    assert dialog.tab_widget.currentIndex() == 1
    assert dialog.builder_table.rowCount() == 1
    assert dialog.builder_table.item(0, 0).text() == archetype.name


@pytest.mark.ui
def test_role_guide_dialog_builder_apply(qtbot: Any) -> None:
    from ankiforge.services.cards.note_type_roles import is_markdown_table

    dialog = NoteTypeRoleGuideDialog()
    qtbot.addWidget(dialog)

    # Bascule sur l'onglet créateur
    dialog.tab_widget.setCurrentIndex(1)
    dialog._add_blank_builder_row()

    with qtbot.waitSignal(dialog.accepted, timeout=1000):
        qtbot.mouseClick(dialog.btn_apply_builder, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_directive is not None
    assert is_markdown_table(dialog.selected_directive) is True
