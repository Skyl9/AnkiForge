from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from ankiforge.ui.dialogs.markdown_table_viewer_dialog import MarkdownTableViewerDialog


@pytest.mark.ui
def test_markdown_table_viewer_dialog_initialization(qtbot: Any) -> None:
    sample_md = """| Concept | Directive | Champs |
|---|---|---|
| Test | Directive de test | Front, Back |"""

    dialog = MarkdownTableViewerDialog(markdown_text=sample_md)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() != ""
    assert hasattr(dialog, "text_browser")
    assert hasattr(dialog, "raw_editor")
    assert "Test" in dialog.raw_editor.toPlainText()
    assert "Directive de test" in dialog.text_browser.toHtml()


@pytest.mark.ui
def test_markdown_table_viewer_dialog_edit_and_apply(qtbot: Any) -> None:
    initial_md = "| A | B |\n|---|---|\n| 1 | 2 |"
    dialog = MarkdownTableViewerDialog(markdown_text=initial_md)
    qtbot.addWidget(dialog)

    edited_md = "| A | B |\n|---|---|\n| Modif | Valeur |"
    dialog.raw_editor.setPlainText(edited_md)

    with qtbot.waitSignal(dialog.accepted, timeout=1000):
        qtbot.mouseClick(dialog.btn_apply, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_markdown == edited_md
