"""
Tests unitaires et d'intégration pour le rendu des cartes, la préservation des médias
et l'éradication des faux positifs 'CARTE INVALIDE'.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.models.note_table_model import NoteVirtualTableModel
from ankiforge.utils.anki_renderer import _is_empty, render_card_text


def test_is_empty_recognizes_media() -> None:
    """Vérifie que _is_empty ne considère pas les balises images, SVG ou audio comme vides."""
    assert not _is_empty('<img src="schema.png">')
    assert not _is_empty("<svg><rect width='100' height='50'/></svg>")
    assert not _is_empty("[sound:audio.mp3]")
    assert not _is_empty("<audio src='test.wav'></audio>")
    assert _is_empty("")
    assert _is_empty("   ")
    assert _is_empty("<div>&nbsp;</div>")
    assert _is_empty("<b></b>")


def test_render_card_text_preserves_images_and_svg() -> None:
    """Vérifie que render_card_text préserve les étiquettes de médias et n'efface pas les sections conditionnelles."""
    qfmt = "{{#Header}}<h3>{{Header}}</h3>{{/Header}}\n<div id='image-wrapper'>\n    {{Image}}\n    {{Question Mask}}\n</div>"
    fields = {
        "Header": "",
        "Image": '<img src="anatomy_heart.png">',
        "Question Mask": "<svg><rect/></svg>",
    }

    result = render_card_text(qfmt, fields, template_index=0, is_recto=True)

    assert "🖼️ [anatomy_heart.png]" in result
    assert "🔲 [Masque d'occlusion]" in result
    assert len(result.strip()) > 0


def test_render_card_text_cloze_multiple_cards() -> None:
    """Vérifie le rendu propre et distinct des cartes cloze c1 et c2."""
    qfmt = "{{cloze:Texte}}"
    fields = {"Texte": "Le {{c1::cœur}} comporte {{c2::quatre}} cavités."}

    # Carte 1 (c1)
    q1 = render_card_text(qfmt, fields, template_index=0, is_recto=True)
    assert "[...]" in q1
    assert "quatre" in q1

    # Carte 2 (c2)
    q2 = render_card_text(qfmt, fields, template_index=1, is_recto=True)
    assert "cœur" in q2
    assert "[...]" in q2


def test_render_card_text_field_name_fallback() -> None:
    """Vérifie que si les champs d'origine ne s'appellent pas Front/Back, un repli automatique s'applique."""
    qfmt = "<b>Question:</b> {{Front}}"
    afmt = "{{FrontSide}}<hr><b>Réponse:</b> {{Back}}"
    fields = {"Question": "Capitale de l'Islande ?", "Reponse": "Reykjavik"}

    r_front = render_card_text(qfmt, fields, template_index=0, is_recto=True)
    assert "Capitale de l'Islande ?" in r_front

    r_back = render_card_text(afmt, fields, template_index=0, is_recto=False, front_raw_html=qfmt)
    assert "Reykjavik" in r_back


def test_table_model_cards_mode_image_occlusion_not_invalid(mock_db: Any) -> None:
    """Vérifie qu'une carte Image Occlusion dans le tableau virtuel n'est pas marquée 'CARTE INVALIDE'."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck IO {uid}")

    qfmt = "{{#Header}}<h3>{{Header}}</h3>{{/Header}}\n<div id='image-wrapper'>\n    {{Image}}\n    {{Question Mask}}\n</div>"
    nt = NoteTypeModel.create(
        name=f"IO Model {uid}",
        fields_schema=json.dumps(["Header", "Image", "Question Mask", "Answer Mask"]),
        templates=json.dumps([{"name": "Image Occlusion", "qfmt": qfmt, "afmt": "{{Image}}{{Answer Mask}}"}]),
        css_style="",
    )

    note = NoteModel.create(guid=f"io_note_{uid}", note_type=nt, deck=deck)
    NoteVersionModel.create(
        note=note,
        content=json.dumps(
            {
                "Header": "",
                "Image": '<img src="brain_lobes.png">',
                "Question Mask": "<svg><rect/></svg>",
                "Answer Mask": "<svg><rect/></svg>",
            }
        ),
        is_active=True,
    )
    card = CardModel.create(note=note, deck=deck, template_index=0)

    cards_query = CardModel.select().where(CardModel.id == card.id)
    model = NoteVirtualTableModel(query=cards_query, display_mode="cards")

    assert model.rowCount() == 1
    card_data = model.get_card_data_at(0)
    assert card_data is not None
    assert not card_data.is_invalid
    assert "⚠️ CARTE INVALIDE" not in card_data.question
    assert "🖼️ [brain_lobes.png]" in card_data.question


def test_table_model_cards_mode_cloze_c2_not_invalid(mock_db: Any) -> None:
    """Vérifie que la carte c2 d'une note cloze n'est pas marquée 'CARTE INVALIDE' et a le bon libellé."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Cloze {uid}")

    nt = NoteTypeModel.create(
        name=f"Cloze Model {uid}",
        fields_schema=json.dumps(["Texte", "Extra"]),
        templates=json.dumps([{"name": "Cloze", "qfmt": "{{cloze:Texte}}", "afmt": "{{cloze:Texte}}<br>{{Extra}}"}]),
        css_style="",
    )

    note = NoteModel.create(guid=f"cloze_note_{uid}", note_type=nt, deck=deck)
    NoteVersionModel.create(
        note=note,
        content=json.dumps({"Texte": "Canberra est la capitale de l'{{c1::Australie}} et non {{c2::Sydney}}.", "Extra": "Géo"}),
        is_active=True,
    )
    c1 = CardModel.create(note=note, deck=deck, template_index=0)
    c2 = CardModel.create(note=note, deck=deck, template_index=1)

    cards_query = CardModel.select().where(CardModel.id.in_([c1.id, c2.id])).order_by(CardModel.template_index.asc())
    model = NoteVirtualTableModel(query=cards_query, display_mode="cards")

    assert model.rowCount() == 2

    # Carte c1
    row0 = model.get_card_data_at(0)
    assert row0 is not None
    assert not row0.is_invalid
    assert row0.template_name == "Trou 1 (c1)"
    assert "[...]" in row0.question
    assert "Sydney" in row0.question

    # Carte c2
    row1 = model.get_card_data_at(1)
    assert row1 is not None
    assert not row1.is_invalid
    assert row1.template_name == "Trou 2 (c2)"
    assert "Australie" in row1.question
    assert "[...]" in row1.question


def test_table_model_notes_mode_empty_first_field_not_invalid(mock_db: Any) -> None:
    """Vérifie qu'une note dont le premier champ est vide mais dont les champs suivants sont remplis n'est pas invalide."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Note {uid}")

    nt = NoteTypeModel.create(
        name=f"Model First Empty {uid}",
        fields_schema=json.dumps(["Header", "Question", "Answer"]),
        templates="[]",
        css_style="",
    )

    note = NoteModel.create(guid=f"note_fe_{uid}", note_type=nt, deck=deck)
    NoteVersionModel.create(
        note=note,
        content=json.dumps(
            {
                "Header": "",
                "Question": "Qui a peint la Joconde ?",
                "Answer": "Léonard de Vinci",
            }
        ),
        is_active=True,
    )

    notes_query = NoteModel.select().where(NoteModel.id == note.id)
    model = NoteVirtualTableModel(query=notes_query, display_mode="notes")

    assert model.rowCount() == 1
    note_data = model.get_note_data_at(0)
    assert note_data is not None
    assert not note_data.is_invalid
    assert note_data.recto == "Qui a peint la Joconde ?"
    assert "⚠️ CARTE INVALIDE" not in note_data.recto
