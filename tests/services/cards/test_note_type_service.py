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


def test_suggest_field_mapping_heuristics() -> None:
    # 1. Exact et insensible à la casse/accents
    src = ["Question", "Réponse", "Remarque"]
    tgt = ["question", "reponse", "remarque"]
    sugg = NoteTypeService.suggest_field_mapping(src, tgt)
    assert sugg["Question"] == "question"
    assert sugg["Réponse"] == "reponse"
    assert sugg["Remarque"] == "remarque"

    # 2. Synonymes canoniques
    src2 = ["Question", "Réponse", "Notes"]
    tgt2 = ["Front", "Back", "Extra"]
    sugg2 = NoteTypeService.suggest_field_mapping(src2, tgt2)
    assert sugg2["Question"] == "Front"
    assert sugg2["Réponse"] == "Back"
    assert sugg2["Notes"] == "Extra"

    # 3. Positionnel de repli
    src3 = ["ChampA", "ChampB"]
    tgt3 = ["Target1", "Target2"]
    sugg3 = NoteTypeService.suggest_field_mapping(src3, tgt3)
    assert sugg3["ChampA"] == "Target1"
    assert sugg3["ChampB"] == "Target2"


def test_validate_field_mapping(sample_models_and_notes) -> None:
    src_fields = ["Question", "Reponse", "Remarque"]
    tgt_fields = ["Front", "Back"]

    # 1. Champ cible inexistant
    valid, err, sugg = NoteTypeService.validate_field_mapping(src_fields, tgt_fields, mapping_champs={"Question": "Inexistant"})
    assert valid is False
    assert "introuvable" in err.lower() or "inexistant" in err.lower()

    # 2. Perte de données non vide sans mapping explicite
    n1 = sample_models_and_notes["notes"][0]
    valid_loss, err_loss, _ = NoteTypeService.validate_field_mapping(src_fields, tgt_fields, mapping_champs=None, sample_notes=[n1])
    # n1 a "Remarque": "Europe" (non vide) et tgt_fields n'a que Front et Back -> Remarque est perdue
    assert valid_loss is False
    assert "remarque" in err_loss.lower()

    # 2b. Mapping partiel n'assignant pas Remarque (contenant du texte)
    valid_partial, err_partial, _ = NoteTypeService.validate_field_mapping(src_fields, tgt_fields, mapping_champs={"Question": "Front"}, sample_notes=[n1])
    assert valid_partial is False
    assert "remarque" in err_partial.lower()

    # 3. Mapping explicite autorisant l'omission ou associant le champ
    valid_ok, err_ok, _ = NoteTypeService.validate_field_mapping(src_fields, tgt_fields, mapping_champs={"Question": "Front", "Reponse": "Back", "Remarque": ""}, sample_notes=[n1])
    assert valid_ok is True
    assert err_ok == ""


def test_clean_cloze_markers() -> None:
    raw = "La capitale de la {{c1::France::pays}} est {{c2::Paris}}."
    cleaned = NoteTypeService.clean_cloze_markers(raw)
    assert cleaned == "La capitale de la France est Paris."


def test_change_note_type_creates_additional_card(sample_models_and_notes) -> None:
    n1 = sample_models_and_notes["notes"][0]
    c1 = sample_models_and_notes["cards"][0]
    c1_id = c1.id
    target_diff = sample_models_and_notes["nt_target_diff_tmpl"]  # a 2 templates C1 et C2

    initial_cards = CardModel.select().where(CardModel.note == n1).count()
    assert initial_cards == 1

    result = NoteTypeService.change_note_type(
        note_ids=[n1.id],
        target_model=target_diff,
        mapping_champs={"Question": "Front", "Reponse": "Back"},
    )

    assert result["status"] == "applied"
    assert result["cards_preserved"] == 1
    assert result["cards_created"] == 1
    assert result["cards_deleted"] == 0

    # 2 cartes pour n1 maintenant
    cards = list(CardModel.select().where(CardModel.note == n1).order_by(CardModel.template_index.asc()))
    assert len(cards) == 2
    assert cards[0].id == c1_id  # 1ère carte préservée
    assert cards[0].template_index == 0
    assert cards[0].ivl == 42  # SRS conservé
    assert cards[1].template_index == 1  # 2ème carte créée


def test_change_note_type_deletes_surnumerary_cards(sample_models_and_notes) -> None:
    deck = DeckModel.create(name="Deck::TwoTemplates")
    nt_2tmpl = sample_models_and_notes["nt_target_diff_tmpl"]
    nt_1tmpl = sample_models_and_notes["nt_source"]

    # Créer une note avec 2 cartes
    note_2c = NoteModel.create(note_type=nt_2tmpl, tags="two")
    note_2c.add_version({"Front": "F", "Back": "B"}, source="init")
    c1 = CardModel.create(note=note_2c, deck=deck, template_index=0, ivl=50)
    c2 = CardModel.create(note=note_2c, deck=deck, template_index=1, ivl=20)

    assert CardModel.select().where(CardModel.note == note_2c).count() == 2

    result = NoteTypeService.change_note_type(
        note_ids=[note_2c.id],
        target_model=nt_1tmpl,
        mapping_champs={"Front": "Question", "Back": "Reponse"},
    )

    assert result["status"] == "applied"
    assert result["cards_preserved"] == 1
    assert result["cards_deleted"] == 1

    remaining_cards = list(CardModel.select().where(CardModel.note == note_2c))
    assert len(remaining_cards) == 1
    assert remaining_cards[0].id == c1.id
    assert remaining_cards[0].ivl == 50
    # c2 a été supprimée
    assert CardModel.get_or_none(CardModel.id == c2.id) is None


def test_change_note_type_explicit_template_mapping(sample_models_and_notes) -> None:
    deck = DeckModel.create(name="Deck::TmplRemap")
    nt_source = sample_models_and_notes["nt_source"]  # 1 template C1
    nt_target = sample_models_and_notes["nt_target_diff_tmpl"]  # 2 templates C1, C2

    n = NoteModel.create(note_type=nt_source)
    n.add_version({"Question": "Q", "Reponse": "R"}, source="init")
    c = CardModel.create(note=n, deck=deck, template_index=0, ivl=99)

    # Mapper explicitement la carte 0 vers le gabarit 1 avec tolérance clé chaîne
    result = NoteTypeService.change_note_type(
        note_ids=[n.id],
        target_model=nt_target,
        mapping_champs={"Question": "Front", "Reponse": "Back"},
        template_mapping={"0": 1},
    )

    assert result["status"] == "applied"
    c_reloaded = CardModel.get_by_id(c.id)
    assert c_reloaded.template_index == 1
    assert c_reloaded.ivl == 99


def test_change_note_type_cloze_to_standard() -> None:
    deck = DeckModel.create(name="Deck::ClozeTest")
    nt_cloze = NoteTypeModel.create(
        name="Model Cloze Test",
        fields_schema=json.dumps(["Text", "Extra"]),
        templates=json.dumps([{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"}]),
    )
    nt_standard = NoteTypeModel.create(
        name="Model Standard Test",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Standard", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )

    note = NoteModel.create(note_type=nt_cloze)
    note.add_version({"Text": "L'oxygène a le symbole {{c1::O}} et le numéro {{c2::8}}.", "Extra": "Chimie"}, source="init")
    CardModel.create(note=note, deck=deck, template_index=0, ivl=10)
    CardModel.create(note=note, deck=deck, template_index=1, ivl=20)

    result = NoteTypeService.change_note_type(
        note_ids=[note.id],
        target_model=nt_standard,
        mapping_champs={"Text": "Front", "Extra": "Back"},
        clean_cloze=True,
    )

    assert result["status"] == "applied"
    note_reloaded = NoteModel.get_by_id(note.id)
    active_v = note_reloaded.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
    assert active_v is not None
    content = json.loads(active_v.content)
    # Marqueurs de trous nettoyés
    assert content["Front"] == "L'oxygène a le symbole O et le numéro 8."
    assert content["Back"] == "Chimie"
    # 1 seule carte conservée
    cards = list(CardModel.select().where(CardModel.note == note))
    assert len(cards) == 1


def test_change_note_type_standard_to_cloze() -> None:
    deck = DeckModel.create(name="Deck::StdToCloze")
    nt_standard = NoteTypeModel.create(
        name="Model Std Test 2",
        fields_schema=json.dumps(["Question", "Reponse"]),
        templates=json.dumps([{"name": "Standard", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}]),
    )
    nt_cloze = NoteTypeModel.create(
        name="Model Cloze Test 2",
        fields_schema=json.dumps(["Text", "Extra"]),
        templates=json.dumps([{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"}]),
    )

    note = NoteModel.create(note_type=nt_standard)
    note.add_version({"Question": "{{c1::Paris}} et {{c2::Lyon}} sont en {{c3::France}}.", "Reponse": "Géographie"}, source="init")
    c0 = CardModel.create(note=note, deck=deck, template_index=0, ivl=35)

    result = NoteTypeService.change_note_type(
        note_ids=[note.id],
        target_model=nt_cloze,
        mapping_champs={"Question": "Text", "Reponse": "Extra"},
    )

    assert result["status"] == "applied"
    assert result["cards_preserved"] == 1
    assert result["cards_created"] == 2  # pour couvrir c1, c2, c3

    cards = list(CardModel.select().where(CardModel.note == note).order_by(CardModel.template_index.asc()))
    assert len(cards) == 3
    assert cards[0].id == c0.id
    assert cards[0].template_index == 0
    assert cards[0].ivl == 35  # SRS préservé
    assert cards[1].template_index == 1
    assert cards[2].template_index == 2


def test_change_note_type_cloze_without_occlusion_warning() -> None:
    deck = DeckModel.create(name="Deck::ClozeNoOcclusion")
    nt_std = NoteTypeModel.create(
        name="Std No Occ",
        fields_schema=json.dumps(["Question", "Reponse"]),
        templates=json.dumps([{"name": "S", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}]),
    )
    nt_cloze = NoteTypeModel.create(
        name="Cloze No Occ",
        fields_schema=json.dumps(["Text", "Extra"]),
        templates=json.dumps([{"name": "C", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}"}]),
    )

    note = NoteModel.create(note_type=nt_std)
    note.add_version({"Question": "Texte sans occlusion.", "Reponse": "Rien"}, source="init")
    CardModel.create(note=note, deck=deck, template_index=0)

    result = NoteTypeService.change_note_type(
        note_ids=[note.id],
        target_model=nt_cloze,
        mapping_champs={"Question": "Text", "Reponse": "Extra"},
    )

    assert result["status"] == "applied"
    # Doit contenir un avertissement explicite
    assert any("occlusion" in w.lower() for w in result["warnings"])
