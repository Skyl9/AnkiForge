"""
Tests UI headless pour LeechWozniakSplitDialog (dialogue modal d'inspection et de scission atomique).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from PySide6.QtCore import Qt

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.audit.leech_service import LeechService
from ankiforge.ui.dialogs.leech_wozniak_split_dialog import LeechWozniakSplitDialog

pytestmark = pytest.mark.ui


def test_leech_wozniak_split_dialog_flow(qtbot: Any) -> None:
    deck = DeckModel.create(name="Biologie")
    nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Recto", "Verso"]))
    note = NoteModel.create(note_type=nt, tags=json.dumps(["leech"]))
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps(
            {
                "Recto": "Qu'est-ce que la mitose, la méiose et leurs 4 phases ?",
                "Verso": "Mitose = division conforme. Méiose = réductionnelle. Phases = prophase, métaphase, anaphase, télophase.",
            }
        ),
        is_active=True,
    )
    CardModel.create(note=note, deck=deck, lapses=7, stability=1.1, difficulty=8.0)

    leech_cards = LeechService.get_leech_cards()
    assert len(leech_cards) == 1
    leech_data = leech_cards[0]

    dialog = LeechWozniakSplitDialog(leech_data=leech_data)
    qtbot.addWidget(dialog)

    # 1. Vérifications à l'ouverture
    assert "Sangsue" in dialog.windowTitle()
    assert dialog.btn_generate is not None
    assert dialog.btn_apply.isHidden()  # Caché tant qu'aucune scission n'est générée

    # 2. Déclenchement de la génération IA
    signals_emitted = []
    dialog.split_applied.connect(lambda nid: signals_emitted.append(nid))

    qtbot.mouseClick(dialog.btn_generate, Qt.MouseButton.LeftButton)

    # La proposition doit être affichée et le bouton d'application visible
    assert not dialog.btn_apply.isHidden()
    assert dialog.current_patch_id is not None
    assert len(dialog.current_subcards) >= 2

    # 3. Application du patch (Two-Phase Commit)
    qtbot.mouseClick(dialog.btn_apply, Qt.MouseButton.LeftButton)

    assert len(signals_emitted) == 1
    assert signals_emitted[0] == note.id

    # La note parente est archivée
    reloaded_parent = NoteModel.get_by_id(note.id)
    assert reloaded_parent.status == "archived"
