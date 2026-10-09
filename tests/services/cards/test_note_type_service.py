"""Tests unitaires pour le service NoteTypeService (MCP-NT-01).

Couvre :
- Le remap automatique (insensible à la casse, puis positionnel, puis vide).
- La surcharge par mapping explicite.
- La migration par lot sans toucher aux cartes ni altérer l'état SRS.
- L'atomicité (rollback complet en cas d'erreur).
- Les avertissements non bloquants en cas de divergence du nombre de gabarits.
"""

import json

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.note_type_service import NoteTypeService

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_models_and_notes():
    deck = DeckModel.create(name="Deck::Test")
    nt_source = NoteTypeModel.create(
        name="Source Model",
        fields_schema=json.dumps(["Question", "Reponse", "Remarque"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}]),
    )

    nt_target_same_tmpl = NoteTypeModel.create(
        name="Target Model",
        fields_schema=json.dumps(["question", "Answer", "Extra"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{question}}", "afmt": "{{Answer}} <hr> {{Extra}}"}]),
    )

    nt_target_diff_tmpl = NoteTypeModel.create(
        name="Target Model Diff Tmpl",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps(
            [
                {"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"},
                {"name": "C2", "qfmt": "{{Back}}", "afmt": "{{Front}}"},
            ]
        ),
    )

    # Note 1 avec SRS sur la carte
    n1 = NoteModel.create(note_type=nt_source, tags="alpha")
    n1.add_version({"Question": "Capitale de la France ?", "Reponse": "Paris", "Remarque": "Europe"}, source="init")
    c1 = CardModel.create(
        note=n1,
        deck=deck,
        template_index=0,
        flags=3,
        is_suspended=False,
        ivl=42,
        reps=10,
        lapses=1,
        stability=18.5,
        difficulty=4.2,
        retrievability=0.91,
    )

    # Note 2
    n2 = NoteModel.create(note_type=nt_source, tags="beta")
    n2.add_version({"Question": "2 + 2 ?", "Reponse": "4", "Remarque": "Math"}, source="init")
    c2 = CardModel.create(
        note=n2,
        deck=deck,
        template_index=0,
        ivl=5,
        reps=2,
    )

    return {
        "deck": deck,
        "nt_source": nt_source,
        "nt_target": nt_target_same_tmpl,
        "nt_target_diff_tmpl": nt_target_diff_tmpl,
        "notes": [n1, n2],
        "cards": [c1, c2],
    }


def test_remap_fields_auto():
    source_data = {
        "QUESTION": "Quelle est la capitale ?",
        "Reponse": "Paris",
        "Source": "Manuel géo",
    }
    target_fields = ["Question", "Answer", "Source", "Notes"]

    # "Question" matched by case-insensitive name -> "Quelle est la capitale ?"
    # "Answer" not in source, positional 1 in source is "Reponse" -> "Paris"
    # "Source" matched by case-insensitive name -> "Manuel géo"
    # "Notes" -> empty
    mapped = NoteTypeService.remap_fields(source_data, target_fields)
    assert mapped["Question"] == "Quelle est la capitale ?"
    assert mapped["Answer"] == "Paris"
    assert mapped["Source"] == "Manuel géo"
    assert mapped["Notes"] == ""


def test_remap_fields_with_explicit_mapping_override():
    source_data = {
        "Question": "Q",
        "Reponse": "R",
        "Remarque": "Annotation importante",
    }
    target_fields = ["Front", "Back", "Comments"]
    explicit = {"Remarque": "Comments", "Reponse": "Front"}

    mapped = NoteTypeService.remap_fields(source_data, target_fields, mapping_champs=explicit)
    # Explicit overrides:
    assert mapped["Comments"] == "Annotation importante"
    assert mapped["Front"] == "R"
    # Positional or default for "Back":
    assert mapped["Back"] in ("Q", "R", "Annotation importante")


def test_change_note_type_preserves_srs_and_cards(sample_models_and_notes):
    n1, n2 = sample_models_and_notes["notes"]
    c1, c2 = sample_models_and_notes["cards"]
    target_nt = sample_models_and_notes["nt_target"]

    initial_card_count = CardModel.select().count()
    c1_id = c1.id
    c1_ivl = c1.ivl
    c1_stability = c1.stability

    result = NoteTypeService.change_note_type(
        note_ids=[n1.id, n2.id],
        target_model=target_nt,
        mapping_champs={"Reponse": "Answer"},
    )

    assert result["status"] == "applied"
    assert result["migrated_count"] == 2
    assert len(result["warnings"]) == 0

    # Cartes non recréées, compte identique
    assert CardModel.select().count() == initial_card_count

    # Vérification carte 1 et SRS préservé
    reloaded_c1 = CardModel.get_by_id(c1_id)
    assert reloaded_c1.ivl == c1_ivl
    assert reloaded_c1.stability == c1_stability
    assert reloaded_c1.flags == 3
    assert reloaded_c1.note.id == n1.id

    # Vérification type de note rechargé
    reloaded_n1 = NoteModel.get_by_id(n1.id)
    assert reloaded_n1.note_type.id == target_nt.id

    active_v = reloaded_n1.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
    assert active_v is not None
    content = json.loads(active_v.content)
    assert content["question"] == "Capitale de la France ?"
    assert content["Answer"] == "Paris"


def test_change_note_type_warning_on_templates_diff(sample_models_and_notes):
    n1, n2 = sample_models_and_notes["notes"]
    target_diff = sample_models_and_notes["nt_target_diff_tmpl"]

    result = NoteTypeService.change_note_type(
        note_ids=[n1.id],
        target_model=target_diff.name,
    )

    assert result["status"] == "applied"
    assert len(result["warnings"]) > 0
    assert any("gabarit" in w.lower() for w in result["warnings"])


def test_change_note_type_atomic_rollback(sample_models_and_notes):
    n1, _ = sample_models_and_notes["notes"]
    target_nt = sample_models_and_notes["nt_target"]

    # Passer un ID inexistant pour forcer l'échec
    with pytest.raises(ValueError, match="Note.*introuvable"):
        NoteTypeService.change_note_type(
            note_ids=[n1.id, 999999],
            target_model=target_nt,
        )

    # Vérifier que n1 n'a pas été modifié (rollback)
    reloaded_n1 = NoteModel.get_by_id(n1.id)
    assert reloaded_n1.note_type.id == sample_models_and_notes["nt_source"].id


def test_validate_structure():
    # 1. Modèle valide
    valid_data = {
        "name": "Modèle Valide",
        "fields_schema": ["Front", "Back", "Extra"],
        "templates": [{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}} {{hint:Extra}}"}],
    }
    ok, errs = NoteTypeService.validate_structure(valid_data)
    assert ok is True
    assert len(errs) == 0

    # 2. Nom vide
    ok, errs = NoteTypeService.validate_structure({"name": "", "fields_schema": ["A"], "templates": [{"name": "1", "qfmt": "{{A}}", "afmt": "{{A}}"}]})
    assert ok is False
    assert any("nom" in e.lower() for e in errs)

    # 3. Champs vides ou doublons
    ok, errs = NoteTypeService.validate_structure({"name": "X", "fields_schema": [], "templates": [{"name": "1", "qfmt": "x", "afmt": "y"}]})
    assert ok is False
    assert any("au moins un champ" in e.lower() for e in errs)

    ok, errs = NoteTypeService.validate_structure({"name": "X", "fields_schema": ["Front", "front"], "templates": [{"name": "1", "qfmt": "{{Front}}", "afmt": "{{Front}}"}]})
    assert ok is False
    assert any("double" in e.lower() for e in errs)

    # 4. Gabarit référençant un champ inconnu
    ok, errs = NoteTypeService.validate_structure(
        {
            "name": "X",
            "fields_schema": ["Front", "Back"],
            "templates": [{"name": "C1", "qfmt": "{{Inconnu}}", "afmt": "{{Back}}"}],
        }
    )
    assert ok is False
    assert any("inexistant" in e.lower() for e in errs)


def test_audit_conformity(sample_models_and_notes):
    nt_source = sample_models_and_notes["nt_source"]

    # Création d'une note avec violations
    n_violation = NoteModel.create(note_type=nt_source)
    n_violation.add_version(
        {
            "Question": "<span style='color:red;'>Question avec style</span>",  # inline_html
            "Reponse": "<span style='color:red;'>Question avec style</span>",  # field_duplicates
            "Remarque": "[sound:audio_parasite.mp3]",  # sound_outside_audio
        },
        source="test",
    )

    # Note avec champ vide
    n_empty = NoteModel.create(note_type=nt_source)
    n_empty.add_version(
        {
            "Question": "Valide",
            "Reponse": "",  # empty_fields
            "Remarque": "",
        },
        source="test",
    )

    # Audit complet
    res = NoteTypeService.audit_conformity(nt_source.name)
    assert res["total_notes"] >= 4
    summary = res["summary"]
    assert summary["total_violations"] > 0
    assert summary["by_rule"]["inline_html"] >= 1
    assert summary["by_rule"]["sound_outside_audio"] >= 1
    assert summary["by_rule"]["field_duplicates"] >= 1
    assert summary["by_rule"]["empty_fields"] >= 1

    # Audit filtré sur une seule règle
    res_filtered = NoteTypeService.audit_conformity(nt_source.name, regles="empty_fields")
    assert res_filtered["rules_evaluated"] == ["empty_fields"]
    assert res_filtered["summary"]["by_rule"]["empty_fields"] >= 1
    assert "inline_html" not in res_filtered["summary"]["by_rule"]


def test_preview_card_render(sample_models_and_notes):
    n1 = sample_models_and_notes["notes"][0]
    nt = sample_models_and_notes["nt_source"]

    # Rendu standard
    res = NoteTypeService.preview_card_render(n1.id)
    assert res["note_id"] == n1.id
    assert res["note_type"] == nt.name
    assert "Capitale de la France ?" in res["front_html"]
    assert "Paris" in res["back_html"]

    # Rendu avec surcharges
    res_override = NoteTypeService.preview_card_render(
        n1.id,
        fields_json=json.dumps({"Question": "Quelle est la capitale de l'Espagne ?", "Reponse": "Madrid"}),
    )
    assert "Espagne" in res_override["front_html"]
    assert "Madrid" in res_override["back_html"]
