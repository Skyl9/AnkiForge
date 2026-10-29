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


def test_abort_staged_patch_is_unitary(sample_data):
    """Vérifie l'annulation MCP d'un patch sans suppression du bundle ni des patches frères."""
    bundle_id = StagedPatchRegistry.begin_bundle(title="Bundle Annulation Unitaire")
    first_patch = StagedPatchRegistry.create_patch(patch_type="card", diff_payload={"modified": {"Back": "Paris"}})
    sibling_patch = StagedPatchRegistry.create_patch(patch_type="card", diff_payload={"modified": {"Back": "Lyon"}})
    StagedPatchRegistry.commit_bundle(bundle_id)

    result = StagedPatchRegistry.abort_staged_patch(first_patch.patch_id, reason="Correction ciblée")

    assert result == {
        "status": "aborted",
        "patch_id": first_patch.patch_id,
        "bundle_id": bundle_id,
        "reason": "Correction ciblée",
        "message": f"Le patch '{first_patch.patch_id}' a été annulé.",
    }
    assert StagedPatchRegistry.get_patch(first_patch.patch_id).status == "aborted"
    assert StagedPatchRegistry.get_patch(sibling_patch.patch_id).status == "pending"


def test_abort_staged_patch_tool_returns_structured_result(sample_data):
    """Vérifie l'exposition FastMCP de l'annulation unitaire."""
    import asyncio

    patch = StagedPatchRegistry.create_patch(patch_type="card", diff_payload={"modified": {"Back": "Paris"}})

    async def _run():
        raw_result = await mcp.call_tool("abort_staged_patch", {"patch_id": patch.patch_id, "reason": "Invalidé"})
        return json.loads(raw_result.content[0].text)

    result = asyncio.run(_run())

    assert result["status"] == "aborted"
    assert result["patch_id"] == patch.patch_id
    assert result["reason"] == "Invalidé"


def test_abort_staged_patch_rejects_missing_or_terminal_patch(sample_data):
    """Vérifie les erreurs explicites pour un patch inexistant ou déjà annulé."""
    missing_result = StagedPatchRegistry.abort_staged_patch("patch_missing")
    assert missing_result["status"] == "error"
    assert "introuvable" in missing_result["message"]

    patch = StagedPatchRegistry.create_patch(patch_type="card", diff_payload={"modified": {"Back": "Paris"}})
    StagedPatchRegistry.abort_staged_patch(patch.patch_id)
    terminal_result = StagedPatchRegistry.abort_staged_patch(patch.patch_id)
    assert terminal_result["status"] == "error"
    assert "aborted" in terminal_result["message"]


def test_list_pending_exposes_only_pending_patches(sample_data):
    """list_pending() n'expose que les patchs encore en attente, du plus ancien au plus récent."""
    note = sample_data["note"]
    v1 = sample_data["v1"]

    def _create(modified):
        return StagedPatchRegistry.create_patch(
            patch_type="card",
            target_id=note.id,
            original_version_id=v1.id,
            diff_payload={
                "original": {"Front": "Capitale de la France ?", "Back": "Lyon"},
                "modified": modified,
            },
        )

    first = _create({"Back": "Paris"})
    second = _create({"Back": "Marseille"})
    applied = _create({"Back": "Nantes"})
    rejected = _create({"Back": "Lille"})

    StagedPatchRegistry.apply_staged_patch(applied.patch_id)
    StagedPatchRegistry.reject_staged_patch(rejected.patch_id, reason="Proposition erronée")

    pending_ids = [p.patch_id for p in StagedPatchRegistry.list_pending()]

    assert pending_ids == [first.patch_id, second.patch_id]
    assert applied.patch_id not in pending_ids
    assert rejected.patch_id not in pending_ids


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


def test_apply_staged_patch_model(sample_data):
    """Vérifie l'application d'un patch de type 'model' (branche réparée)."""
    nt = sample_data["note_type"]

    patch = StagedPatchRegistry.create_patch(
        patch_type="model",
        target_id=nt.id,
        diff_payload={
            "modified": {
                "description": "Nouvelle description pour l'IA",
                "css_style": ".card { font-size: 20px; }",
            },
            "metadata": {"note_type_name": nt.name, "note_type_id": nt.id},
        },
    )

    result = StagedPatchRegistry.apply_staged_patch(patch.patch_id)
    assert result["status"] == "applied"
    assert result["patch_id"] == patch.patch_id

    reloaded = NoteTypeModel.get_by_id(nt.id)
    assert reloaded.description == "Nouvelle description pour l'IA"
    assert "20px" in reloaded.css_style


def test_propose_note_type_refactor_returns_real_patch_id(sample_data):
    """Vérifie que propose_note_type_refactor renvoie un vrai patch_id enregistrant un patch pending."""
    from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry

    nt = sample_data["note_type"]
    res_str = MCPToolRegistry.propose_note_type_refactor(
        note_type_name=nt.name,
        new_css=".card { color: red; }",
        new_description="Refactorisé via consultant",
    )
    res_json = json.loads(res_str)
    assert res_json["status"] == "staged_diff"
    assert "patch_id" in res_json
    p_id = res_json["patch_id"]

    # Vérification que le patch est en attente
    patch = StagedPatchRegistry.get_patch(p_id)
    assert patch is not None
    assert patch.status == "pending"
    assert patch.patch_type == "model"

    # Application
    apply_res = StagedPatchRegistry.apply_staged_patch(p_id)
    assert apply_res["status"] == "applied"
    assert NoteTypeModel.get_by_id(nt.id).description == "Refactorisé via consultant"


def test_staged_patch_note_type_create():
    """Vérifie le cycle complet de proposition et d'application d'un patch 'note_type_create'."""
    patch = StagedPatchRegistry.create_patch(
        patch_type="note_type_create",
        diff_payload={
            "name": "Nouveau Type Créé Par Patch",
            "fields_schema": ["Terme", "Definition"],
            "templates": [{"name": "Carte 1", "qfmt": "{{Terme}}", "afmt": "{{FrontSide}}<hr>{{Definition}}"}],
            "css_style": ".card { background: white; }",
            "description": "Type créé par agent",
            "on_conflict": "error",
        },
    )

    assert patch.patch_id.startswith("patch_")
    assert patch.status == "pending"

    # N'existe pas encore en base avant validation
    assert NoteTypeModel.get_or_none(NoteTypeModel.name == "Nouveau Type Créé Par Patch") is None

    result = StagedPatchRegistry.apply_staged_patch(patch.patch_id)
    assert result["status"] == "applied"
    assert result["note_type_name"] == "Nouveau Type Créé Par Patch"

    created = NoteTypeModel.get_or_none(NoteTypeModel.name == "Nouveau Type Créé Par Patch")
    assert created is not None
    assert created.description == "Type créé par agent"


def test_staged_patch_note_type_change(sample_data):
    """Vérifie le cycle complet de proposition et d'application d'un patch 'note_type_change'."""
    note = sample_data["note"]
    nt_source = sample_data["note_type"]

    nt_target = NoteTypeModel.create(
        name="Cible Migration Patch",
        fields_schema=json.dumps(["Recto", "Verso"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}]),
    )

    patch = StagedPatchRegistry.create_patch(
        patch_type="note_type_change",
        diff_payload={
            "note_ids": [note.id],
            "target_model": nt_target.name,
            "mapping_champs": {"Front": "Recto", "Back": "Verso"},
        },
    )

    assert patch.status == "pending"
    # Note toujours sur le modèle source
    assert NoteModel.get_by_id(note.id).note_type.id == nt_source.id

    result = StagedPatchRegistry.apply_staged_patch(patch.patch_id)
    assert result["status"] == "applied"
    assert result["count"] == 1

    # Note migrée sur le modèle cible
    reloaded_note = NoteModel.get_by_id(note.id)
    assert reloaded_note.note_type.id == nt_target.id


def test_sync_direct_edit_updates_payload_before_apply(sample_data):
    """Vérifie que sync_direct_edit modifie le payload du patch en attente et que l'application prend en compte la retouche."""
    note = sample_data["note"]
    v1 = sample_data["v1"]

    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=note.id,
        original_version_id=v1.id,
        diff_payload={
            "original": {"Front": "Question 1", "Back": "Réponse brute"},
            "modified": {"Front": "Question 1", "Back": "Réponse proposée par IA"},
            "explanation": "Refactor initial",
        },
    )

    # Retouche utilisateur en direct (correction avant validation)
    retouche_utilisateur = {"Front": "Question 1 raffinée", "Back": "Réponse validée et corrigée"}
    ok = StagedPatchRegistry.sync_direct_edit(patch.patch_id, retouche_utilisateur)
    assert ok is True

    # Vérification que le patch en BDD a bien été mis à jour
    reloaded_patch = StagedPatchRegistry.get_patch(patch.patch_id)
    assert reloaded_patch is not None
    payload = json.loads(reloaded_patch.diff_payload)
    assert payload["modified"] == retouche_utilisateur

    # Application du patch : la note doit contenir la version retouchée
    result = StagedPatchRegistry.apply_staged_patch(patch.patch_id)
    assert result["status"] == "applied"

    active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
    assert active_v is not None
    active_content = json.loads(active_v.content)
    assert active_content == retouche_utilisateur


def test_sync_direct_edit_fails_on_nonexistent_or_closed_patch(sample_data):
    """Vérifie que sync_direct_edit renvoie False pour un patch inconnu ou déjà clos."""
    note = sample_data["note"]
    assert StagedPatchRegistry.sync_direct_edit("patch_inconnu_999", {"Front": "X"}) is False

    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=note.id,
        diff_payload={"original": {}, "modified": {}},
    )
    StagedPatchRegistry.reject_staged_patch(patch.patch_id)

    assert StagedPatchRegistry.sync_direct_edit(patch.patch_id, {"Front": "Y"}) is False


def test_create_patch_emits_event_bus_and_mcp_listener(sample_data):
    """Vérifie que create_patch notifie à la fois event_bus et les écouteurs MCP enregistrés."""
    from ankiforge.services.ai.mcp_server import register_staged_patch_listener, unregister_staged_patch_listener
    from ankiforge.utils.event_bus import MCPPatchStagedEvent, event_bus

    bus_events: list[MCPPatchStagedEvent] = []
    mcp_events: list[dict] = []

    def on_bus_event(ev: MCPPatchStagedEvent) -> None:
        bus_events.append(ev)

    def on_mcp_event(data: dict) -> None:
        mcp_events.append(data)

    event_bus.subscribe(MCPPatchStagedEvent, on_bus_event)
    register_staged_patch_listener(on_mcp_event)

    try:
        patch = StagedPatchRegistry.create_patch(
            patch_type="card",
            target_id=sample_data["note"].id,
            diff_payload={"title": "Test Notification Live", "original": {}, "modified": {}},
        )

        assert len(bus_events) >= 1
        assert any(e.patch_id == patch.patch_id for e in bus_events)
        matching_bus = next(e for e in bus_events if e.patch_id == patch.patch_id)
        assert matching_bus.patch_type == "card"
        assert matching_bus.target_id == sample_data["note"].id

        assert len(mcp_events) >= 1
        assert any(d.get("patch_id") == patch.patch_id for d in mcp_events)
    finally:
        event_bus.unsubscribe(MCPPatchStagedEvent, on_bus_event)
        unregister_staged_patch_listener(on_mcp_event)
