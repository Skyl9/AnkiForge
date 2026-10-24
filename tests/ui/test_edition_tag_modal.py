"""Tests UI headless pour le modal de filtrage par tag dans EditionView."""

from __future__ import annotations

import uuid

import pytest
from pytestqt.qtbot import QtBot

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.views.edition_view import EditionView

pytestmark = pytest.mark.ui


def test_edition_view_show_tag_modal_uses_deck_scope(qtbot: QtBot) -> None:
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"ModelTagModal_{uid}", fields_schema='["Front", "Back"]')

    deck_math = DeckModel.create(name=f"Math_{uid}")
    deck_geo = DeckModel.create(name=f"Math_{uid}::Geometrie")
    deck_bio = DeckModel.create(name=f"Bio_{uid}")

    n1 = NoteModel.create(note_type=nt, tags='["algebre"]')
    CardModel.create(note=n1, deck=deck_math, template_index=0)

    n2 = NoteModel.create(note_type=nt, tags='["triangle"]')
    CardModel.create(note=n2, deck=deck_geo, template_index=0)

    n3 = NoteModel.create(note_type=nt, tags='["cellule"]')
    CardModel.create(note=n3, deck=deck_bio, template_index=0)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)

    # 1. Test sans deck sélectionné (portée globale)
    view._active_folder_id = None
    view.btn_open_tag.click()
    assert view._tag_modal is not None
    assert view._tag_modal.raw_allowed_tags is not None
    assert set(view._tag_modal.raw_allowed_tags) == {"algebre", "triangle", "cellule"}
    view._tag_modal.close()

    # 2. Test avec deck Math sélectionné (incluant son sous-deck Geometrie)
    view._active_folder_id = deck_math.id
    view.btn_open_tag.click()
    assert view._tag_modal is not None
    assert view._tag_modal.raw_allowed_tags is not None
    assert set(view._tag_modal.raw_allowed_tags) == {"algebre", "triangle"}
    assert "cellule" not in view._tag_modal.raw_allowed_tags
    view._tag_modal.close()
