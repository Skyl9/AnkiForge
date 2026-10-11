from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
from ankiforge.services.cards.bulk_hygiene_service import BulkHygieneService
from ankiforge.utils.tags import parse_note_tags


@pytest.fixture
def hygiene_setup(mock_db):
    uid = uuid.uuid4().hex[:6]
    deck_main = DeckModel.create(name=f"Deck_{uid}")
    nt_main = NoteTypeModel.create(
        name=f"Model_{uid}",
        fields_schema=json.dumps(["Front", "Back", "Extra"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]),
    )
    nt_second = NoteTypeModel.create(
        name=f"Model_Second_{uid}",
        fields_schema=json.dumps(["Question", "Answer"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Question}}", "afmt": "{{Answer}}"}]),
    )
    return {
        "deck_main": deck_main,
        "nt_main": nt_main,
        "nt_second": nt_second,
        "uid": uid,
    }


def test_sanitize_notes_html_direct(hygiene_setup):
    """Vérifie le nettoyage direct de HTML inline sur des notes (styles, font, scripts, tags vides)."""
    nt = hygiene_setup["nt_main"]
    n1 = NoteModel.create(note_type=nt, tags='["grammaire"]')
    n1.add_version(
        {
            "Front": '<span style="font-size: 14px; color: #ff0000;">Mot <b>important</b></span>',
            "Back": '<font color="blue">Définition</font><script>alert(1);</script><p></p>',
            "Extra": "<div><span>Simple note</span></div>",
        },
        source="init",
    )

    n2 = NoteModel.create(note_type=nt, tags='["vocab"]')
    n2.add_version(
        {
            "Front": '<p style="margin: 0;">Phrase <span style="background: yellow;">surlignée</span></p>',
            "Back": "Explication claire",
            "Extra": "",
        },
        source="init",
    )

    res = BulkHygieneService.sanitize_notes_html([n1.id, n2.id], force_apply=True)
    assert res["status"] == "applied"
    assert res["modified_count"] == 2

    # Vérification du contenu nettoyé de n1
    v1 = NoteVersionModel.get(note=n1, is_active=True)
    c1 = json.loads(v1.content)
    assert 'style="' not in c1["Front"]
    assert "Mot <b>important</b>" in c1["Front"]
    assert "<script" not in c1["Back"]
    assert "<font" not in c1["Back"]
    assert "Définition" in c1["Back"]
    assert v1.source == "mcp_sanitize_html"

    # Vérification de n2
    v2 = NoteVersionModel.get(note=n2, is_active=True)
    c2 = json.loads(v2.content)
    assert "style=" not in c2["Front"]
    assert "Phrase" in c2["Front"]
    assert "surlignée" in c2["Front"]


def test_sanitize_notes_html_preserves_cloze_math_and_sound(hygiene_setup):
    """Vérifie la préservation absolue des clozes {{c1::...}}, KaTeX et balises [sound:...]."""
    nt = hygiene_setup["nt_main"]
    n = NoteModel.create(note_type=nt)
    n.add_version(
        {
            "Front": '<span style="color: red;">Le {{c1::cœur::organe}} pompe le sang</span> \\[ \\sum_{i=1}^n x_i \\]',
            "Back": 'Prononciation : [sound:coeur.mp3] <div style="font-size:12px;">\\( a^2 + b^2 = c^2 \\)</div>',
            "Extra": "",
        },
        source="init",
    )

    res = BulkHygieneService.sanitize_notes_html([n.id], force_apply=True)
    assert res["status"] == "applied"

    v = NoteVersionModel.get(note=n, is_active=True)
    c = json.loads(v.content)
    assert "{{c1::cœur::organe}}" in c["Front"]
    assert "\\[ \\sum_{i=1}^n x_i \\]" in c["Front"]
    assert "[sound:coeur.mp3]" in c["Back"]
    assert "\\( a^2 + b^2 = c^2 \\)" in c["Back"]
    assert "style=" not in c["Front"]
    assert "style=" not in c["Back"]


def test_sanitize_notes_html_two_phase_commit_on_large_mutation(hygiene_setup):
    """Vérifie la mise en attente (StagedPatch) lorsque le volume dépasse le seuil (Two-Phase Commit)."""
    nt = hygiene_setup["nt_main"]
    notes = []
    for i in range(6):
        n = NoteModel.create(note_type=nt)
        n.add_version({"Front": f'<span style="color:blue;">Q{i}</span>', "Back": "R"}, source="init")
        notes.append(n)

    note_ids = [n.id for n in notes]
    # Par défaut stage_threshold=5, donc 6 notes déclenchent le staging
    res = BulkHygieneService.sanitize_notes_html(note_ids, stage_threshold=5, force_apply=False)
    assert res["status"] == "staged_diff"
    patch_id = res["patch_id"]
    assert patch_id.startswith("patch_")
    assert res["modified_count"] == 6

    # Les notes ne doivent PAS encore avoir été modifiées en BDD
    v_before = NoteVersionModel.get(note=notes[0], is_active=True)
    c_before = json.loads(v_before.content)
    assert 'style="color:blue;"' in c_before["Front"]

    # Application du patch via StagedPatchRegistry
    app_res = StagedPatchRegistry.apply_staged_patch(patch_id)
    assert app_res["status"] == "applied"

    # Vérification après application
    v_after = NoteVersionModel.get(note=notes[0], is_active=True)
    assert "style=" not in v_after.content
    assert "Q0" in v_after.content


def test_sanitize_notes_html_strip_all(hygiene_setup):
    """Vérifie le mode strip_all_html retirant l'ensemble des balises HTML en conservant le texte brut."""
    nt = hygiene_setup["nt_main"]
    n = NoteModel.create(note_type=nt)
    n.add_version(
        {
            "Front": "<p>Paragraphe avec <b>gras</b> et <i>italique</i></p>",
            "Back": "<ul><li>Élément 1</li><li>Élément 2</li></ul>",
            "Extra": "",
        },
        source="init",
    )

    res = BulkHygieneService.sanitize_notes_html([n.id], strip_all_html=True, force_apply=True)
    assert res["status"] == "applied"

    v = NoteVersionModel.get(note=n, is_active=True)
    c = json.loads(v.content)
    assert "<p>" not in c["Front"]
    assert "<b>" not in c["Front"]
    assert "Paragraphe avec gras et italique" in c["Front"]
    assert "<ul" not in c["Back"]
    assert "<li" not in c["Back"]
    assert "Élément 1" in c["Back"]


def test_set_tags_bulk_add_remove_replace(hygiene_setup):
    """Vérifie la manipulation en masse des tags avec l'écrivain canonique et la protection des tags de provenance."""
    nt = hygiene_setup["nt_main"]
    n1 = NoteModel.create(note_type=nt, tags='["cours1", "doc:guide_42", "section:intro"]')
    n2 = NoteModel.create(note_type=nt, tags='["cours1", "cours2"]')

    # 1. Mode 'add'
    res_add = BulkHygieneService.set_tags_bulk([n1.id, n2.id], tags=["nouveau_tag", "cours1"], mode="add")
    assert res_add["status"] == "success"
    assert res_add["modified_count"] == 2

    n1_reloaded = NoteModel.get_by_id(n1.id)
    tags1 = parse_note_tags(n1_reloaded.tags)
    assert "nouveau_tag" in tags1
    assert "doc:guide_42" in tags1
    assert "section:intro" in tags1

    # 2. Mode 'remove' protégeant les tags de provenance
    res_rem = BulkHygieneService.set_tags_bulk([n1.id], tags=["cours1", "doc:guide_42"], mode="remove", allow_remove_provenance_tags=False)
    assert res_rem["status"] == "success"
    tags1_after_rem = parse_note_tags(NoteModel.get_by_id(n1.id).tags)
    assert "cours1" not in tags1_after_rem
    assert "doc:guide_42" in tags1_after_rem  # tag de traçabilité préservé

    # 3. Mode 'replace'
    res_rep = BulkHygieneService.set_tags_bulk([n1.id], tags=["seul_tag"], mode="replace", allow_remove_provenance_tags=False)
    assert res_rep["status"] == "success"
    tags1_rep = parse_note_tags(NoteModel.get_by_id(n1.id).tags)
    assert "seul_tag" in tags1_rep
    assert "doc:guide_42" in tags1_rep  # tag de provenance conservé
    assert "nouveau_tag" not in tags1_rep


def test_delete_unused_note_type(hygiene_setup):
    """Vérifie la suppression sécurisée d'un type de note inutilisé avec garde-fous."""
    nt_main = hygiene_setup["nt_main"]
    nt_second = hygiene_setup["nt_second"]

    # Création d'une note utilisant nt_main
    NoteModel.create(note_type=nt_main)

    # 1. Échec si des notes y sont rattachées
    res_busy = BulkHygieneService.delete_unused_note_type(nt_main.name, confirm=True)
    assert res_busy["status"] == "error"
    assert "note(s) y sont rattachées" in res_busy["message"]

    # 2. Confirmation requise pour nt_second (0 note)
    res_conf = BulkHygieneService.delete_unused_note_type(nt_second.name, confirm=False)
    assert res_conf["status"] == "confirmation_required"

    # 3. Suppression réussie avec confirm=True
    res_del = BulkHygieneService.delete_unused_note_type(nt_second.name, confirm=True)
    assert res_del["status"] == "deleted"
    assert NoteTypeModel.get_or_none(NoteTypeModel.id == nt_second.id) is None

    # 4. Échec de suppression si c'est le seul modèle restant (après suppression de la note)
    NoteModel.delete().where(NoteModel.note_type == nt_main).execute()
    res_last = BulkHygieneService.delete_unused_note_type(nt_main.name, confirm=True)
    assert res_last["status"] == "error"
    assert "seul modèle restant" in res_last["message"]


def test_delete_unused_note_type_all_unused(hygiene_setup):
    """Vérifie la suppression groupée de tous les modèles à 0 note via 'all_unused'."""
    uid = hygiene_setup["uid"]
    # Attacher une note à nt_main pour que la collection ait au moins 1 modèle actif conservé
    NoteModel.create(note_type=hygiene_setup["nt_main"])

    nt_extra1 = NoteTypeModel.create(name=f"Extra1_{uid}")
    nt_extra2 = NoteTypeModel.create(name=f"Extra2_{uid}")

    # Confirmation demandée
    res_req = BulkHygieneService.delete_unused_note_type("all_unused", confirm=False)
    assert res_req["status"] == "confirmation_required"
    assert res_req["count"] >= 2

    # Validation
    res_del = BulkHygieneService.delete_unused_note_type("all_unused", confirm=True)
    assert res_del["status"] == "deleted"
    assert nt_extra1.name in res_del["deleted_models"]
    assert nt_extra2.name in res_del["deleted_models"]


def test_move_cards_to_deck(hygiene_setup):
    """Vérifie le déplacement de cartes vers un paquet ou sous-paquet hiérarchique."""
    nt = hygiene_setup["nt_main"]
    d_main = hygiene_setup["deck_main"]

    n1 = NoteModel.create(note_type=nt)
    n1.add_version({"Front": "Q1", "Back": "R1"})
    c1 = CardModel.create(note=n1, deck=d_main)

    n2 = NoteModel.create(note_type=nt)
    n2.add_version({"Front": "Q2", "Back": "R2"})
    c2 = CardModel.create(note=n2, deck=d_main)

    target_subdeck = f"{d_main.name}::SousPaquet"
    res = BulkHygieneService.move_cards_to_deck([c1.id, c2.id], deck=target_subdeck)
    assert res["status"] == "success"
    assert res["moved_count"] == 2

    c1_reloaded = CardModel.get_by_id(c1.id)
    c2_reloaded = CardModel.get_by_id(c2.id)
    assert c1_reloaded.deck.name == target_subdeck
    assert c2_reloaded.deck.name == target_subdeck
    # Le sous-deck a son parent lié
    assert c1_reloaded.deck.parent_deck.id == d_main.id


def test_list_and_delete_empty_cards(hygiene_setup):
    """Vérifie la détection et suppression des cartes à front vide."""
    nt = hygiene_setup["nt_main"]
    d_main = hygiene_setup["deck_main"]

    # Note 1 : carte vide (Front ne contient que des espaces et balises vides)
    n_empty = NoteModel.create(note_type=nt)
    n_empty.add_version({"Front": "  <div></div><p>&nbsp;</p>  ", "Back": "Contenu Verso"})
    c_empty = CardModel.create(note=n_empty, deck=d_main)

    # Note 2 : carte valide
    n_valid = NoteModel.create(note_type=nt)
    n_valid.add_version({"Front": "Question valide", "Back": "Réponse"})
    c_valid = CardModel.create(note=n_valid, deck=d_main)

    # Détection
    res_list = BulkHygieneService.list_empty_cards()
    assert res_list["status"] == "success"
    assert res_list["total_empty_cards"] == 1
    found_ids = [item["card_id"] for item in res_list["empty_cards"]]
    assert c_empty.id in found_ids
    assert c_valid.id not in found_ids

    # Suppression sans confirmation -> requise
    res_no_conf = BulkHygieneService.delete_empty_cards(confirm=False)
    assert res_no_conf["status"] == "confirmation_required"
    assert res_no_conf["empty_cards_count"] == 1

    # Suppression avec confirmation
    res_del = BulkHygieneService.delete_empty_cards(confirm=True)
    assert res_del["status"] == "deleted"
    assert res_del["deleted_count"] == 1
    assert CardModel.get_or_none(CardModel.id == c_empty.id) is None
    assert CardModel.get_or_none(CardModel.id == c_valid.id) is not None
