"""Tests unitaires et d'intégration pour propose_cards_batch_refactor et les Staged Bundles."""

import json
from typing import Any

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    StagedBundleModel,
    StagedPatchModel,
    db,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

pytestmark = pytest.mark.integration


@pytest.fixture
def batch_refactor_setup():
    """Initialise un deck, un modèle et plusieurs notes pour tester la refactorisation par lot."""
    with db.atomic():
        deck = DeckModel.create(name="Sciences::Physique")
        note_type = NoteTypeModel.create(
            name="Modèle Physique",
            fields_schema=json.dumps(["Recto", "Verso", "Remarque"]),
            templates=json.dumps([{"name": "Standard", "qfmt": "{{Recto}}", "afmt": "{{Verso}}<br>{{Remarque}}"}]),
            css_style=".card { font-size: 14px; }",
        )
        notes = []
        for i in range(1, 6):
            n = NoteModel.create(
                guid=f"guid_physique_{i}",
                note_type=note_type,
                tags=f"physique chapitre_{i}",
            )
            NoteVersionModel.create(
                note=n,
                version_number=1,
                content=json.dumps({"Recto": f"Question {i}", "Verso": f"Réponse {i}", "Remarque": ""}),
                is_active=True,
                source="test",
            )
            CardModel.create(note=n, deck=deck, ord=0)
            notes.append(n)

    return {"deck": deck, "note_type": note_type, "notes": notes}


def _extract_text(tool_result: Any) -> str:
    """Helper d'extraction du texte de retour FastMCP."""
    if hasattr(tool_result, "content") and tool_result.content:
        return str(tool_result.content[0].text)
    return str(tool_result)


def test_propose_cards_batch_refactor_nominal_creates_sealed_bundle(batch_refactor_setup):
    """Vérifie le cas nominal : un lot valide crée un StagedBundle scellé avec N étapes unitaires."""
    notes = batch_refactor_setup["notes"]

    refactors = [
        {
            "note_id": notes[0].id,
            "fields": {"Recto": "Question 1 Révisée", "Verso": "Réponse 1 Concise"},
            "tags": ["physique", "mecanique"],
            "explanation": "Suppression du verbiage",
        },
        {
            "note_id": notes[1].id,
            "fields": {"Recto": "Question 2 Révisée", "Verso": "Réponse 2 Concise"},
            "add_tags": ["revu_ia"],
            "explanation": "Clarification",
        },
    ]

    import asyncio

    res_raw = asyncio.run(
        mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": json.dumps(refactors),
                "title": "Campagne Physique P1",
                "reason": "Nettoyage sémantique",
            },
        )
    )
    res_text = _extract_text(res_raw)
    data = json.loads(res_text)

    assert data["status"] == "staged"
    assert data["total_staged"] == 2
    assert data["total_requested"] == 2
    assert len(data["warnings"]) == 0
    bundle_id = data["bundle_id"]

    # Vérification en BDD
    bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == bundle_id)
    assert bundle is not None
    assert bundle.status == "pending"  # Doit être automatiquement scellé
    assert bundle.total_steps == 2
    assert bundle.title == "Campagne Physique P1"

    # Vérification des patches individuels
    patches = list(StagedPatchModel.select().where(StagedPatchModel.bundle == bundle).order_by(StagedPatchModel.step_order))
    assert len(patches) == 2
    assert patches[0].patch_type == "card"
    assert patches[0].target_id == notes[0].id
    assert patches[1].target_id == notes[1].id

    # Vérification du diff_payload et des tags
    payload_0 = json.loads(patches[0].diff_payload)
    assert payload_0["modified"]["Recto"] == "Question 1 Révisée"
    assert payload_0["modified_tags"] == ["physique", "mecanique"]

    payload_1 = json.loads(patches[1].diff_payload)
    assert "revu_ia" in payload_1["modified_tags"]
    assert "physique" in payload_1["modified_tags"]  # tag conservé


def test_propose_cards_batch_refactor_inside_existing_bundle(batch_refactor_setup):
    """Vérifie que si un bundle est déjà ouvert, les étapes y sont ajoutées sans scellement prématuré."""
    notes = batch_refactor_setup["notes"]

    import asyncio

    # 1. Ouvrir manuellement une session de bundle
    b_id = StagedPatchRegistry.begin_bundle(title="Bundle Maître Ouvert")

    refactors = [
        {
            "note_id": notes[0].id,
            "fields": {"Recto": "Question A"},
        }
    ]

    res_raw = asyncio.run(
        mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": json.dumps(refactors),
            },
        )
    )
    data = json.loads(_extract_text(res_raw))

    assert data["status"] == "staged"
    assert data["bundle_id"] == b_id

    # Le bundle doit toujours être en cours de construction ("building")
    bundle = StagedBundleModel.get(StagedBundleModel.bundle_id == b_id)
    assert bundle.status == "building"

    # Nettoyage
    StagedPatchRegistry.abort_bundle(b_id)


def test_propose_cards_batch_refactor_tolerant_to_missing_ids(batch_refactor_setup):
    """Vérifie la tolérance : les cartes valides sont stagées et les IDs introuvables sont rapportés dans warnings."""
    notes = batch_refactor_setup["notes"]

    refactors = [
        {
            "note_id": notes[0].id,
            "fields": {"Recto": "Question Valide"},
        },
        {
            "note_id": 999999,  # ID inexistant
            "fields": {"Recto": "Question Fantôme"},
        },
    ]

    import asyncio

    res_raw = asyncio.run(
        mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": json.dumps(refactors),
            },
        )
    )
    data = json.loads(_extract_text(res_raw))

    assert data["status"] == "staged"
    assert data["total_staged"] == 1
    assert data["total_requested"] == 2
    assert len(data["warnings"]) == 1
    assert "999999" in data["warnings"][0]


def test_propose_cards_batch_refactor_rejects_unknown_fields(batch_refactor_setup):
    """Vérifie le rejet strict des clés de champs non déclarées dans fields_schema."""
    notes = batch_refactor_setup["notes"]

    refactors = [
        {
            "note_id": notes[0].id,
            "fields": {"Recto": "Question Valide", "ChampInconnu": "Valeur Illégale"},
        }
    ]

    import asyncio

    res_raw = asyncio.run(
        mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": json.dumps(refactors),
            },
        )
    )
    data = json.loads(_extract_text(res_raw))

    assert data["status"] == "error" or data["total_staged"] == 0
    assert any("ChampInconnu" in w for w in data.get("warnings", [data.get("message", "")]))


def test_propose_cards_batch_refactor_limit_exceeded():
    """Vérifie qu'un lot supérieur à 100 cartes est rejeté d'emblée."""
    fake_refactors = [{"note_id": i, "fields": {"Recto": f"Q{i}"}} for i in range(101)]

    import asyncio

    res_raw = asyncio.run(
        mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": json.dumps(fake_refactors),
            },
        )
    )
    data = json.loads(_extract_text(res_raw))

    assert data["status"] == "error"
    assert "100" in data["message"]


def test_apply_staged_patch_and_bundle_with_tags(batch_refactor_setup):
    """Vérifie que l'application d'un patch avec modified_tags met à jour NoteVersionModel ET note.tags."""
    notes = batch_refactor_setup["notes"]
    target_note = notes[2]

    refactors = [
        {
            "note_id": target_note.id,
            "fields": {"Recto": "Question 3 Finale", "Verso": "Réponse 3 Finale"},
            "tags": ["physique_appliquee", "energie"],
            "explanation": "Changement complet des tags",
        }
    ]

    import asyncio

    res_raw = asyncio.run(
        mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": json.dumps(refactors),
            },
        )
    )
    data = json.loads(_extract_text(res_raw))
    bundle_id = data["bundle_id"]

    # Appliquer l'ensemble du bundle via apply_bundle_all
    apply_res = StagedPatchRegistry.apply_bundle_all(bundle_id)
    assert apply_res["status"] == "applied"
    assert apply_res["applied_steps_count"] == 1

    # Recharger la note depuis la base
    refreshed_note = NoteModel.get_by_id(target_note.id)
    assert "physique_appliquee" in refreshed_note.tags
    assert "energie" in refreshed_note.tags
    assert "chapitre_3" not in refreshed_note.tags  # tags remplacés intégralement

    # Vérifier la nouvelle version active
    active_v = refreshed_note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
    assert active_v is not None
    assert active_v.version_number == 2
    content = json.loads(active_v.content)
    assert content["Recto"] == "Question 3 Finale"


def test_card_semantic_diff_widget_displays_tags(batch_refactor_setup, qtbot):
    """Vérifie que CardSemanticDiffWidget instancie une rangée pour les tags modifiés."""
    from ankiforge.ui.widgets.card_semantic_diff_widget import CardSemanticDiffWidget

    notes = batch_refactor_setup["notes"]
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)

    diff_payload = {
        "type": "card",
        "note_id": notes[0].id,
        "original": {"Recto": "Q1", "Verso": "R1"},
        "modified": {"Recto": "Q1 mod", "Verso": "R1 mod"},
        "original_tags": ["physique"],
        "modified_tags": ["physique", "appliquee"],
    }
    widget.set_patch(diff_payload)

    field_rows = widget.get_field_rows()
    assert "_tags" in field_rows
    assert "physique" in field_rows["_tags"].orig_browser.toPlainText()
    assert "appliquee" in field_rows["_tags"].mod_editor.toPlainText()
