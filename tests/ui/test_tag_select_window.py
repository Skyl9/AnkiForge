"""Tests UI headless pour TagSelectWindow.

Vérifie le masquage par défaut des tags de traçabilité documentaire,
la case à cocher pour les révéler et l'arborescence hiérarchique.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ankiforge.ui.components.tag_select_window import TagSelectWindow

pytestmark = pytest.mark.ui


def test_tag_select_window_provenance_filtering(qtbot: QtBot) -> None:
    tags = [
        "vocabulaire",
        "matiere::physique",
        "doc:42_mon_doc",
        "section:chapitre_1",
        "page:12",
        "source:manuel_scolaire",
    ]

    window = TagSelectWindow(
        title="Test Tags",
        allowed_tags=tags,
        show_provenance_toggle=True,
    )
    qtbot.addWidget(window)
    window.show()

    # Par défaut, la case est décochée
    assert not window.cb_show_provenance.isChecked()

    # Seuls les tags non-provenance doivent être présents dans _items_by_path
    assert "vocabulaire" in window._items_by_path
    assert "matiere::physique" in window._items_by_path
    assert "doc:42_mon_doc" not in window._items_by_path
    assert "section:chapitre_1" not in window._items_by_path
    assert "page:12" not in window._items_by_path
    assert "source:manuel_scolaire" not in window._items_by_path

    # Quand on coche "Afficher les tags de traçabilité"
    window.cb_show_provenance.setChecked(True)

    assert "vocabulaire" in window._items_by_path
    assert "doc:42_mon_doc" in window._items_by_path
    assert "section:chapitre_1" in window._items_by_path
    assert "page:12" in window._items_by_path
    assert "source:manuel_scolaire" in window._items_by_path


def test_tag_select_window_selection_signal(qtbot: QtBot) -> None:
    tags = ["biologie::cellulaire", "chimie"]
    window = TagSelectWindow(title="Test Selection", allowed_tags=tags)
    qtbot.addWidget(window)

    selected_tags: list[str] = []
    window.tag_selected.connect(selected_tags.append)

    # Sélection dans le tree
    item = window._items_by_path["biologie::cellulaire"]
    window.tree.setCurrentItem(item)

    # Vérification que le texte de recherche est rempli
    assert window.search_input.text() == "biologie::cellulaire"
    assert window.btn_confirm.isEnabled()

    # Clic sur valider
    qtbot.mouseClick(window.btn_confirm, Qt.MouseButton.LeftButton)
    assert selected_tags == ["biologie::cellulaire"]
