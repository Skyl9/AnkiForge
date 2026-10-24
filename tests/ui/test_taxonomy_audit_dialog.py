"""Tests UI headless pour TaxonomyAuditDialog (ADR 0040)."""

from __future__ import annotations

import json

import pytest
from pytestqt.qtbot import QtBot

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel
from ankiforge.ui.dialogs.taxonomy_audit_dialog import TaxonomyAuditDialog
from ankiforge.utils.tags import parse_note_tags

pytestmark = pytest.mark.ui


@pytest.fixture
def audit_dlg_setup(mock_db):
    deck = DeckModel.create(name="Deck_Audit_UI")
    nt = NoteTypeModel.create(
        name="Model_Audit_UI",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )
    n1 = NoteModel.create(note_type=nt, tags='["medecine generale"]')
    n2 = NoteModel.create(note_type=nt, tags='["::physique::"]')
    return {"deck": deck, "nt": nt, "n1": n1, "n2": n2}


def test_taxonomy_audit_dialog_detection_and_apply(qtbot: QtBot, monkeypatch, audit_dlg_setup) -> None:
    """Vérifie l'affichage des anomalies et l'application des réparations depuis le dialogue."""
    dialog = TaxonomyAuditDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    # Mocker la notification modale pour éviter le blocage de boucle Qt
    notifications: list[tuple[str, str]] = []
    monkeypatch.setattr(dialog, "_notify_info", lambda title, text: notifications.append((title, text)))

    assert dialog.table.rowCount() == 2
    assert dialog.btn_apply.isEnabled()

    # Déclencher les réparations
    dialog._apply_repairs()

    assert len(notifications) == 1

    # Recharger les notes
    n1 = NoteModel.get_by_id(audit_dlg_setup["n1"].id)
    n2 = NoteModel.get_by_id(audit_dlg_setup["n2"].id)

    assert "medecine_generale" in parse_note_tags(n1.tags)
    assert "physique" in parse_note_tags(n2.tags)

    # La table doit maintenant être vide
    assert dialog.table.rowCount() == 0
