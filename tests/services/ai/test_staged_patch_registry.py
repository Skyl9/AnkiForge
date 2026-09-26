"""Tests unitaires et d'intégration pour le registre StagedPatch et Two-Phase Commit MCP."""

import json

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_data():
    with db.atomic():
        deck = DeckModel.create(name="Deck Test StagedPatch")
        note_type = NoteTypeModel.create(
            name="Modèle Test",
            fields_schema=json.dumps(["Front", "Back"]),
            templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
            css_style=".card { font-family: arial; }",
        )
        note = NoteModel.create(note_type=note_type, tags="test")
        v1 = NoteVersionModel.create(
            note=note,
            version_number=1,
            content=json.dumps({"Front": "Capitale de la France ?", "Back": "Lyon"}, ensure_ascii=False),
            source="manual",
            is_active=True,
        )
        card = CardModel.create(note=note, deck=deck, template_index=0)
    return {"deck": deck, "note_type": note_type, "note": note, "v1": v1, "card": card}


def test_create_and_inspect_staged_patch(sample_data):
    """Vérifie la création d'un patch en attente avec ID unique et statut pending."""
    note = sample_data["note"]
    v1 = sample_data["v1"]

    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=note.id,
        original_version_id=v1.id,
        diff_payload={
            "original": {"Front": "Capitale de la France ?", "Back": "Lyon"},
            "modified": {"Front": "Capitale de la France ?", "Back": "Paris"},
            "explanation": "Correction de la capitale.",
        },
    )

    assert patch.patch_id.startswith("patch_")
    assert patch.status == "pending"
    assert patch.target_id == note.id
    assert patch.original_version_id == v1.id

    fetched = StagedPatchRegistry.get_patch(patch.patch_id)
    assert fetched is not None
    assert fetched.patch_id == patch.patch_id
    assert fetched.status == "pending"


def test_apply_staged_patch_success(sample_data):
    """Vérifie l'application réussie d'un patch avec versioning Time Machine et statut applied."""
    note = sample_data["note"]
    v1 = sample_data["v1"]

    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=note.id,
        original_version_id=v1.id,
        diff_payload={
            "original": {"Front": "Capitale de la France ?", "Back": "Lyon"},
            "modified": {"Front": "Capitale de la France ?", "Back": "Paris"},
            "explanation": "Correction de la capitale.",
        },
    )

    result = StagedPatchRegistry.apply_staged_patch(patch.patch_id)
    assert result["status"] == "applied"
    assert result["patch_id"] == patch.patch_id

    # Vérification BDD
    updated_patch = StagedPatchRegistry.get_patch(patch.patch_id)
    assert updated_patch.status == "applied"
    assert updated_patch.applied_at is not None

    # Vérification de la note et des versions
    v1_refetched = NoteVersionModel.get_by_id(v1.id)
    assert not v1_refetched.is_active

    active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
    assert active_v is not None
    assert active_v.version_number == 2
    content = json.loads(active_v.content)
    assert content["Back"] == "Paris"


def test_apply_staged_patch_optimistic_locking_conflict(sample_data):
    """Vérifie que la modification concurrente de la note cible provoque un conflit et bloque le patch."""
    note = sample_data["note"]
    v1 = sample_data["v1"]

    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=note.id,
        original_version_id=v1.id,
        diff_payload={
            "original": {"Front": "Capitale de la France ?", "Back": "Lyon"},
            "modified": {"Front": "Capitale de la France ?", "Back": "Paris"},
        },
    )

    # Modification concurrente de la note
    with db.atomic():
        v1.is_active = False
        v1.save()
        NoteVersionModel.create(
            note=note,
            version_number=2,
            content=json.dumps({"Front": "Capitale de la France ?", "Back": "Marseille"}),
            is_active=True,
        )

    # Tentative d'application du patch -> doit échouer pour conflit
    result = StagedPatchRegistry.apply_staged_patch(patch.patch_id)
    assert result["status"] == "conflict"
    assert "conflit" in result["message"].lower()

    # Le patch doit rester pending ou passer en conflit sans modifier la note
    updated_patch = StagedPatchRegistry.get_patch(patch.patch_id)
    assert updated_patch.status == "pending"


def test_reject_staged_patch(sample_data):
    """Vérifie le rejet d'un patch en attente."""
    note = sample_data["note"]
    v1 = sample_data["v1"]

    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=note.id,
        original_version_id=v1.id,
        diff_payload={"modified": {"Back": "Bordeaux"}},
    )

    result = StagedPatchRegistry.reject_staged_patch(patch.patch_id, reason="Proposition erronée")
    assert result["status"] == "rejected"

    updated_patch = StagedPatchRegistry.get_patch(patch.patch_id)
    assert updated_patch.status == "rejected"

    # La note ne doit pas avoir changé
    active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
    assert active_v.id == v1.id


def test_mcp_preview_and_apply_patch_tool(sample_data):
    """Vérifie l'exposition et l'exécution de preview_and_apply_patch via l'interface MCP."""
    import asyncio

    async def _run():
        note = sample_data["note"]
        v1 = sample_data["v1"]

        patch = StagedPatchRegistry.create_patch(
            patch_type="card",
            target_id=note.id,
            original_version_id=v1.id,
            diff_payload={
                "original": {"Front": "Capitale de la France ?", "Back": "Lyon"},
                "modified": {"Front": "Capitale de la France ?", "Back": "Paris"},
            },
        )

        # Appel via le serveur FastMCP
        raw_res = await mcp.call_tool("preview_and_apply_patch", {"patch_id": patch.patch_id})
        assert raw_res is not None
        res_text = raw_res.content[0].text if hasattr(raw_res, "content") and raw_res.content else str(raw_res)
        res_data = json.loads(res_text)
        assert res_data["status"] == "applied"
        assert res_data["patch_id"] == patch.patch_id

    asyncio.run(_run())
