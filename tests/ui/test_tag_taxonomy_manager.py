"""Tests UI headless pour TagSelectWindow en mode gestionnaire et ses actions contextuelles (ADR 0040)."""

from __future__ import annotations

import json

import pytest
from pytestqt.qtbot import QtBot

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel
from ankiforge.ui.components.tag_select_window import TagSelectWindow
from ankiforge.utils.tags import parse_note_tags

pytestmark = pytest.mark.ui


@pytest.fixture
def taxo_ui_setup(mock_db):
    deck = DeckModel.create(name="Deck_UI")
    nt = NoteTypeModel.create(
        name="Model_UI",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )
    n1 = NoteModel.create(note_type=nt, tags='["medecine::cardiologie", "urgent"]')
    n2 = NoteModel.create(note_type=nt, tags='["medecine::neurologie"]')
    return {"deck": deck, "nt": nt, "n1": n1, "n2": n2}


def test_tag_select_window_manager_mode(qtbot: QtBot, taxo_ui_setup) -> None:
    """Vérifie l'initialisation de TagSelectWindow en mode gestionnaire."""
    window = TagSelectWindow(mode="manage")
    qtbot.addWidget(window)
    window.show()

    assert window.mode == "manage"
    assert "medecine::cardiologie" in window._items_by_path
    assert "medecine::neurologie" in window._items_by_path


def test_tag_select_window_rename_action(qtbot: QtBot, monkeypatch, taxo_ui_setup) -> None:
    """Vérifie l'exécution du renommage d'un tag depuis la fenêtre de gestion."""
    window = TagSelectWindow(mode="manage")
    qtbot.addWidget(window)
    window.show()

    n1 = taxo_ui_setup["n1"]
    n2 = taxo_ui_setup["n2"]

    # Simuler le dialogue de renommage en mockant les interactions modales
    monkeypatch.setattr(
        window,
        "_get_rename_inputs",
        lambda old: ("sante", True),  # Nouveau nom "sante", avec propagation
    )
    monkeypatch.setattr(window, "_confirm_rename", lambda old, new, count: True)

    window._execute_rename("medecine")

    n1 = NoteModel.get_by_id(n1.id)
    n2 = NoteModel.get_by_id(n2.id)

    assert "sante::cardiologie" in parse_note_tags(n1.tags)
    assert "sante::neurologie" in parse_note_tags(n2.tags)


def test_tag_select_window_delete_action(qtbot: QtBot, monkeypatch, taxo_ui_setup) -> None:
    """Vérifie la suppression d'un tag depuis la fenêtre de gestion."""
    window = TagSelectWindow(mode="manage")
    qtbot.addWidget(window)
    window.show()

    n1 = taxo_ui_setup["n1"]

    monkeypatch.setattr(window, "_confirm_delete", lambda tag, count: True)
    window._execute_delete("urgent")

    n1 = NoteModel.get_by_id(n1.id)
    assert "urgent" not in parse_note_tags(n1.tags)


def test_tag_select_window_merge_action(qtbot: QtBot, monkeypatch, taxo_ui_setup) -> None:
    """Vérifie la fusion d'un tag vers un tag cible depuis la fenêtre de gestion."""
    from PySide6.QtWidgets import QInputDialog

    window = TagSelectWindow(mode="manage")
    qtbot.addWidget(window)
    window.show()

    n1 = taxo_ui_setup["n1"]

    monkeypatch.setattr(QInputDialog, "getItem", lambda *args, **kwargs: ("urgent", True))
    monkeypatch.setattr(window, "_confirm_merge", lambda src, tgt, count: True)

    window._execute_merge("medecine::cardiologie")

    n1 = NoteModel.get_by_id(n1.id)
    assert "urgent" in parse_note_tags(n1.tags)
    assert "medecine::cardiologie" not in parse_note_tags(n1.tags)
