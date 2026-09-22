"""
Tests unitaires pour l'application des diffs et patches du Consultant IA (ConsultantToolRegistry.apply_patch).
Vérifie la mutation atomique en base SQLite, le versionnage NoteVersionModel et le support des 4 types :
- card
- split
- model
- css
"""

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
from ankiforge.services.ai.consultant_engine import ConsultantToolRegistry

pytestmark = pytest.mark.integration


@pytest.fixture
def note_setup():
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_Patch_{uid}")
    nt = NoteTypeModel.create(
        name=f"NT_Patch_{uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style=".card { font-size: 14px; }",
    )
    note = NoteModel.create(guid=f"g_patch_{uid}", note_type=nt, tags="test_patch")
    v1 = NoteVersionModel.create(
        note=note,
        version_number=1,
        content='{"Front": "Question originale", "Back": "Réponse originale"}',
        source="test_init",
        is_active=True,
    )
    card = CardModel.create(note=note, deck=deck, template_index=0)
    return {"uid": uid, "deck": deck, "nt": nt, "note": note, "v1": v1, "card": card}


def test_apply_patch_card_success(note_setup):
    note = note_setup["note"]
    patch_payload = {
        "type": "card",
        "note_id": note.id,
        "modified": {"Front": "Question améliorée", "Back": "Réponse concise"},
        "explanation": "Formulation atomique selon la règle Wozniak.",
    }

    result_raw = ConsultantToolRegistry.apply_patch(patch_json=json.dumps(patch_payload))
    result = json.loads(result_raw)

    assert result["status"] == "applied"
    assert result["type"] == "card"
    assert result["note_id"] == note.id
    assert result["version_number"] == 2

    # Vérification en base SQLite
    active_version = NoteVersionModel.get(note=note, is_active=True)
    assert active_version.version_number == 2
    assert active_version.source == "consultant_apply_patch"
    parsed_content = json.loads(active_version.content)
    assert parsed_content["Front"] == "Question améliorée"

    # L'ancienne version n'est plus active
    v1 = NoteVersionModel.get_by_id(note_setup["v1"].id)
    assert not v1.is_active


def test_apply_patch_card_via_kwargs(note_setup):
    note = note_setup["note"]
    result_raw = ConsultantToolRegistry.apply_patch(
        patch_type="card",
        target_id=note.id,
        patch_data_json=json.dumps({"Front": "Via kwargs Front", "Back": "Via kwargs Back"}),
        explanation="Test kwargs",
    )
    result = json.loads(result_raw)

    assert result["status"] == "applied"
    assert result["note_id"] == note.id
    active_v = NoteVersionModel.get(note=note, is_active=True)
    assert "Via kwargs Front" in active_v.content


def test_apply_patch_split(note_setup):
    note = note_setup["note"]
    deck = note_setup["deck"]
    split_payload = {
        "type": "split",
        "note_id": note.id,
        "modified": [
            {"Front": "Atome 1", "Back": "Explication 1"},
            {"Front": "Atome 2", "Back": "Explication 2"},
            {"Front": "Atome 3", "Back": "Explication 3"},
        ],
        "explanation": "Décomposition en 3 fiches atomiques.",
    }

    result_raw = ConsultantToolRegistry.apply_patch(patch_json=json.dumps(split_payload))
    result = json.loads(result_raw)

    assert result["status"] == "applied"
    assert result["type"] == "split"
    assert len(result["new_note_ids"]) == 3

    # La note parente est archivée
    reloaded_note = NoteModel.get_by_id(note.id)
    assert reloaded_note.status == "archived"

    # Les 3 nouvelles notes existent avec cartes associées au même deck
    for nid in result["new_note_ids"]:
        new_note = NoteModel.get_by_id(nid)
        assert new_note.status == "pending"
        assert new_note.cards.count() == 1
        assert new_note.cards.first().deck == deck
        assert new_note.versions.where(NoteVersionModel.is_active == True).count() == 1  # noqa: E712


def test_apply_patch_model(note_setup):
    nt = note_setup["nt"]
    model_payload = {
        "type": "model",
        "note_type_name": nt.name,
        "modified": {
            "description": "Modèle mis à jour par l'IA",
            "css_style": ".card { font-size: 16px; color: #333; }",
        },
    }

    result_raw = ConsultantToolRegistry.apply_patch(patch_json=json.dumps(model_payload))
    result = json.loads(result_raw)

    assert result["status"] == "applied"
    assert result["type"] == "model"

    reloaded_nt = NoteTypeModel.get_by_id(nt.id)
    assert reloaded_nt.description == "Modèle mis à jour par l'IA"
    assert "16px" in reloaded_nt.css_style


def test_apply_patch_css(note_setup):
    nt = note_setup["nt"]
    css_payload = {
        "type": "css",
        "note_type_name": nt.name,
        "modified": ".cloze-highlight { background-color: yellow; }",
    }

    result_raw = ConsultantToolRegistry.apply_patch(patch_json=json.dumps(css_payload))
    result = json.loads(result_raw)

    assert result["status"] == "applied"
    assert result["type"] == "css"

    reloaded_nt = NoteTypeModel.get_by_id(nt.id)
    assert ".cloze-highlight" in reloaded_nt.css_style
    assert ".card { font-size: 14px; }" in reloaded_nt.css_style


def test_apply_patch_validation_errors(note_setup):
    # 1. Type manquant ou invalide
    res = json.loads(ConsultantToolRegistry.apply_patch(patch_json=json.dumps({"type": "invalid_type"})))
    assert res["status"] == "error"

    # 2. Type card avec note_id manquant
    res = json.loads(ConsultantToolRegistry.apply_patch(patch_json=json.dumps({"type": "card", "modified": {}})))
    assert res["status"] == "error"
    assert "ID de note invalide" in res["message"]

    # 3. Note inexistante
    res = json.loads(ConsultantToolRegistry.apply_patch(patch_json=json.dumps({"type": "card", "note_id": 9999999, "modified": {}})))
    assert res["status"] == "error"
    assert "introuvable" in res["message"]

    # 4. Modèle introuvable pour patch model
    res = json.loads(ConsultantToolRegistry.apply_patch(patch_json=json.dumps({"type": "model", "note_type_name": "Inexistant_Model", "modified": {}})))
    assert res["status"] == "error"
    assert "introuvable" in res["message"]
