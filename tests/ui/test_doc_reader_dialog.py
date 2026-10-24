"""Tests unitaires et UI pour le lecteur de documentation applicatif DocReaderDialog."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QTextDocument

from ankiforge.ui.dialogs.doc_reader_dialog import DocReaderDialog
from ankiforge.utils.paths import get_docs_path


@pytest.mark.ui
def test_doc_reader_dialog_initialization(qtbot: Any) -> None:
    dialog = DocReaderDialog()
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() != ""
    assert dialog.text_browser is not None
    assert dialog.search_input is not None
    assert dialog.btn_zoom_in is not None
    assert dialog.btn_zoom_out is not None
    assert dialog.btn_zoom_reset is not None
    assert dialog.width() >= 800
    assert dialog.height() >= 550


@pytest.mark.ui
def test_doc_reader_dialog_load_markdown(qtbot: Any) -> None:
    dialog = DocReaderDialog()
    qtbot.addWidget(dialog)

    md_content = """# Titre Test

Ceci est un paragraphe de test avec du **texte gras**.

- Puce 1
- Puce 2
"""
    dialog.load_markdown(md_content, title="Guide Test")

    html = dialog.text_browser.toHtml()
    assert "Titre Test" in html
    assert "texte gras" in html
    assert dialog.lbl_title.text() == "Guide Test"


@pytest.mark.ui
def test_doc_reader_dialog_open_lifecycle_guide_and_svg_assets(qtbot: Any) -> None:
    dialog = DocReaderDialog.open_guide("cycle_de_vie_distribue.md")
    qtbot.addWidget(dialog)

    html = dialog.text_browser.toHtml()
    assert "Cycle Global Distribué" in html
    assert "Sanctuarisation" in html
    assert "Zombies" in html

    # Vérification que la base URL est positionnée sur le dossier des guides
    docs_path = get_docs_path()
    guides_dir = docs_path / "guides"
    base_url = dialog.text_browser.document().baseUrl()
    assert base_url.toLocalFile() == str(guides_dir) + "/"

    # Vérification que l'asset SVG principal est résolu par QTextDocument
    img_resource = dialog.text_browser.document().resource(
        QTextDocument.ResourceType.ImageResource,
        QUrl("assets/cycle_de_vie/cycle_global.svg"),
    )
    assert img_resource is not None, "L'asset SVG cycle_global.svg doit être résolu dans QTextBrowser"


@pytest.mark.ui
def test_doc_reader_dialog_search_navigation(qtbot: Any) -> None:
    dialog = DocReaderDialog.open_guide("cycle_de_vie_distribue.md")
    qtbot.addWidget(dialog)

    # Effectuer une recherche
    dialog.search_input.setText("Zombies")

    # Vérifier que le texte est trouvé
    cursor = dialog.text_browser.textCursor()
    assert "zombies" in cursor.selectedText().lower() or dialog._match_count > 0

    # Clic sur Suivant
    qtbot.mouseClick(dialog.btn_find_next, Qt.MouseButton.LeftButton)
    cursor_next = dialog.text_browser.textCursor()
    assert cursor_next is not None


@pytest.mark.ui
def test_doc_reader_dialog_zoom_controls(qtbot: Any) -> None:
    dialog = DocReaderDialog()
    qtbot.addWidget(dialog)

    # Zoom In
    qtbot.mouseClick(dialog.btn_zoom_in, Qt.MouseButton.LeftButton)
    assert dialog._current_zoom_level > 0

    # Reset Zoom
    qtbot.mouseClick(dialog.btn_zoom_reset, Qt.MouseButton.LeftButton)
    assert dialog._current_zoom_level == 0

    # Zoom Out
    qtbot.mouseClick(dialog.btn_zoom_out, Qt.MouseButton.LeftButton)
    assert dialog._current_zoom_level < 0


@pytest.mark.ui
def test_help_tab_in_settings_modal(qtbot: Any) -> None:
    from ankiforge.ui.widgets.settings_modal.modal import SettingsModal
    from ankiforge.ui.widgets.settings_modal.tabs.help_tab import HelpTab

    modal = SettingsModal()
    qtbot.addWidget(modal)

    # Basculer sur l'onglet Aide & Guides (index 8)
    modal.select_tab(8)
    tab = modal.help_tab
    assert isinstance(tab, HelpTab)
    assert not tab.has_pending_changes()

    # Vérification des boutons
    assert tab.btn_open_lifecycle is not None
    assert tab.btn_open_shortcuts_tab is not None
    assert tab.btn_open_feedback is not None

    # Clic sur le bouton des raccourcis clavier doit basculer vers l'onglet 7
    qtbot.mouseClick(tab.btn_open_shortcuts_tab, Qt.MouseButton.LeftButton)
    assert modal.stacked_widget.currentIndex() == 7


@pytest.mark.ui
def test_main_window_routing_lifecycle_guide(qtbot: Any) -> None:
    from ankiforge.ui.main_window import MainWindow

    win = MagicMock(spec=MainWindow)
    # Test _on_command_selected
    MainWindow._on_command_selected(win, "action.lifecycle_guide")
    assert win._open_lifecycle_guide.call_count == 1

    # Test _on_view_selected
    MainWindow._on_view_selected(win, "lifecycle_guide")
    assert win._open_lifecycle_guide.call_count == 2
