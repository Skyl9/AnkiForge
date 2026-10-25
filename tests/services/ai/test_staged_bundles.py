"""Tests unitaires et d'intégration pour les Staged Bundles, Staged Overlay et Fail-Fast Reject."""

import asyncio
import json
from typing import Any

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    StagedBundleModel,
    StagedPatchModel,
    db,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.staged_patch_registry import StagedOverlay, StagedPatchRegistry

pytestmark = pytest.mark.integration


@pytest.fixture
def test_setup():
    """Initialise un environnement de test minimal."""
    with db.atomic():
        deck = DeckModel.create(name="Deck Existant")
        note_type = NoteTypeModel.create(
            name="Modèle Test Bundle",
            fields_schema=json.dumps(["Front", "Back"]),
            templates=json.dumps([{"name": "Standard", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
            css_style=".card { font-family: arial; }",
        )
    return {"deck": deck, "note_type": note_type}


def _extract_text(tool_result: Any) -> str:
    if hasattr(tool_result, "content") and tool_result.content:
        return str(tool_result.content[0].text)
    return str(tool_result)


def test_staged_overlay_tracks_virtual_entities():
    """Vérifie le fonctionnement isolé de StagedOverlay."""
    overlay = StagedOverlay(bundle_id="bundle_test_1")

    assert not overlay.is_deck_available("Sciences::Biologie")
    overlay.register_created_deck("Sciences::Biologie")
    assert overlay.is_deck_available("Sciences::Biologie")

    assert not overlay.has_duplicate_first_field("Sciences::Biologie", "Mitochondrie")
    overlay.register_created_note_first_field("Sciences::Biologie", "Mitochondrie")
    assert overlay.has_duplicate_first_field("Sciences::Biologie", "Mitochondrie")
    assert overlay.has_duplicate_first_field("Sciences::Biologie", "mitochondrie")  # Case-insensitive


def test_bundle_lifecycle_begin_create_commit(test_setup):
    """Vérifie le cycle de vie complet d'un bundle : begin -> patchs ordonnés -> commit."""
    # 1. Ouvrir le bundle
    bundle_id = StagedPatchRegistry.begin_bundle(
        title="Création de cours de Biologie",
        explanation="Ajout du paquet et des cartes de biologie cellulaire.",
    )
    assert bundle_id.startswith("bundle_")

    bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == bundle_id)
    assert bundle is not None
    assert bundle.status == "building"
    assert bundle.total_steps == 0
    assert bundle.current_step == 1

    # 2. Enregistrer 2 patchs dans le bundle
    p1 = StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": "Sciences::Biologie", "title": "Créer Deck Biologie"},
    )
    assert p1.bundle.bundle_id == bundle_id
    assert p1.step_order == 1

    p2 = StagedPatchRegistry.create_patch(
        patch_type="note_create",
        diff_payload={"note_type_name": "Modèle Test Bundle", "deck_name": "Sciences::Biologie", "title": "Créer Carte 1"},
    )
    assert p2.bundle.bundle_id == bundle_id
    assert p2.step_order == 2

    # Vérifier que le bundle s'est mis à jour
    bundle = StagedBundleModel.get_by_id(bundle.id)
    assert bundle.total_steps == 2

    # 3. Commit du bundle
    res = StagedPatchRegistry.commit_bundle(bundle_id)
    assert res["status"] == "staged"
    assert res["bundle_id"] == bundle_id
    assert res["total_steps"] == 2

    bundle = StagedBundleModel.get_by_id(bundle.id)
    assert bundle.status == "pending"


def test_commit_empty_bundle_fails():
    """Vérifie qu'un bundle sans étapes ne peut pas être scellé."""
    bundle_id = StagedPatchRegistry.begin_bundle(title="Bundle Vide")
    with pytest.raises(ValueError, match="contient aucune étape"):
        StagedPatchRegistry.commit_bundle(bundle_id)


def test_abort_bundle_cleans_up(test_setup):
    """Vérifie que l'annulation supprime le bundle et ses patchs."""
    bundle_id = StagedPatchRegistry.begin_bundle(title="Bundle à Annuler")
    p1 = StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": "À Supprimer"},
    )
    assert StagedPatchModel.get_or_none(StagedPatchModel.patch_id == p1.patch_id) is not None

    ok = StagedPatchRegistry.abort_bundle(bundle_id)
    assert ok is True

    assert StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == bundle_id) is None
    assert StagedPatchModel.get_or_none(StagedPatchModel.patch_id == p1.patch_id) is None


def test_fail_fast_reject_cascade(test_setup):
    """Vérifie la règle d'arrêt en cascade (Fail-Fast Reject) sur refus d'une étape."""
    bundle_id = StagedPatchRegistry.begin_bundle(title="Bundle Multi-Étapes")
    p1 = StagedPatchRegistry.create_patch(patch_type="deck_create", diff_payload={"deck_name": "Deck 1"})
    p2 = StagedPatchRegistry.create_patch(patch_type="note_create", diff_payload={"title": "Carte 1"})
    p3 = StagedPatchRegistry.create_patch(patch_type="note_create", diff_payload={"title": "Carte 2"})
    p4 = StagedPatchRegistry.create_patch(patch_type="note_create", diff_payload={"title": "Carte 3"})
    StagedPatchRegistry.commit_bundle(bundle_id)

    # Rejeter l'étape 2
    res_reject = StagedPatchRegistry.reject_bundle_step(bundle_id, step_order=2, reason="Erreur de concept à l'étape 2")
    assert res_reject["status"] == "rejected"
    assert res_reject["rejected_steps_count"] == 3  # étapes 2, 3, 4

    p1 = StagedPatchModel.get_by_id(p1.id)
    p2 = StagedPatchModel.get_by_id(p2.id)
    p3 = StagedPatchModel.get_by_id(p3.id)
    p4 = StagedPatchModel.get_by_id(p4.id)

    assert p1.status == "pending"
    assert p2.status == "rejected"
    assert p3.status == "rejected"
    assert p4.status == "rejected"

    bundle = StagedBundleModel.get(StagedBundleModel.bundle_id == bundle_id)
    assert bundle.status in ("rejected", "partial")


def test_bundle_sequential_application(test_setup):
    """Vérifie l'application étape par étape d'un bundle avec création de deck puis de note."""
    nt = test_setup["note_type"]
    bundle_id = StagedPatchRegistry.begin_bundle(title="Bundle Application Séquentielle")

    # Étape 1 : Créer le deck
    StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": "Biologie::Génétique", "description": "Deck génétique"},
    )
    # Étape 2 : Créer la note dans ce deck
    StagedPatchRegistry.create_patch(
        patch_type="note_create",
        diff_payload={
            "note_type_name": nt.name,
            "deck_name": "Biologie::Génétique",
            "fields": {"Front": "Qu'est-ce que l'ADN ?", "Back": "Acide désoxyribonucléique"},
        },
    )
    StagedPatchRegistry.commit_bundle(bundle_id)

    # Appliquer étape 1
    res1 = StagedPatchRegistry.apply_bundle_step(bundle_id, step_order=1)
    assert res1["status"] == "applied"
    assert DeckModel.get_or_none(DeckModel.name == "Biologie::Génétique") is not None

    bundle = StagedBundleModel.get(StagedBundleModel.bundle_id == bundle_id)
    assert bundle.current_step == 2
    assert bundle.status == "pending"

    # Appliquer étape 2
    res2 = StagedPatchRegistry.apply_bundle_step(bundle_id, step_order=2)
    assert res2["status"] == "applied"

    bundle = StagedBundleModel.get_by_id(bundle.id)
    assert bundle.status == "applied"

    # Vérifier que la note a été créée dans le nouveau deck
    note = NoteModel.get_by_id(res2["note_id"])
    card = CardModel.get(CardModel.note == note)
    assert card.deck.name == "Biologie::Génétique"


def test_bundle_atomic_apply_all(test_setup):
    """Vérifie l'application globale 'Tout valider le bloc' en une seule transaction atomique."""
    nt = test_setup["note_type"]
    bundle_id = StagedPatchRegistry.begin_bundle(title="Bundle Tout Appliquer")

    StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": "Chimie::Organique"},
    )
    StagedPatchRegistry.create_patch(
        patch_type="note_create",
        diff_payload={
            "note_type_name": nt.name,
            "deck_name": "Chimie::Organique",
            "fields": {"Front": "Formule du méthane", "Back": "CH4"},
        },
    )
    StagedPatchRegistry.commit_bundle(bundle_id)

    res = StagedPatchRegistry.apply_bundle_all(bundle_id)
    assert res["status"] == "applied"
    assert res["applied_steps_count"] == 2

    bundle = StagedBundleModel.get(StagedBundleModel.bundle_id == bundle_id)
    assert bundle.status == "applied"
    assert DeckModel.get_or_none(DeckModel.name == "Chimie::Organique") is not None


def test_mcp_fastmcp_bundle_endpoints(test_setup):
    """Vérifie les endpoints FastMCP : begin, create_deck, create_note avec overlay, inspect, commit."""
    nt = test_setup["note_type"]

    async def _run() -> None:
        # 1. begin_staged_bundle
        res_begin = await mcp.call_tool(
            "begin_staged_bundle",
            {"title": "Bundle MCP FastMCP", "explanation": "Test de session MCP"},
        )
        data_begin = json.loads(_extract_text(res_begin))
        assert data_begin["status"] == "bundle_opened"
        bundle_id = data_begin["bundle_id"]

        # 2. create_deck dans le bundle (doit devenir staged et alimenter l'overlay)
        res_deck = await mcp.call_tool(
            "create_deck",
            {"deck_name": "Physique::Optique", "description": "Deck d'optique"},
        )
        data_deck = json.loads(_extract_text(res_deck))
        assert data_deck["status"] == "staged"
        assert data_deck["deck_name"] == "Physique::Optique"
        assert data_deck["step_order"] == 1

        # 3. create_note ciblant ce deck virtuel (contrôle d'hallucination satisfait par l'overlay)
        res_note = await mcp.call_tool(
            "create_note",
            {
                "note_type_name": nt.name,
                "deck_name": "Physique::Optique",
                "fields_json": json.dumps({"Front": "Loi de Snell-Descartes", "Back": "n1 sin(i1) = n2 sin(i2)"}),
            },
        )
        data_note = json.loads(_extract_text(res_note))
        assert data_note["status"] == "staged"
        assert data_note["deck"] == "Physique::Optique"

        # 4. get_staged_pending_operations
        res_ops = await mcp.call_tool("get_staged_pending_operations", {"bundle_id": bundle_id})
        data_ops = json.loads(_extract_text(res_ops))
        assert data_ops["status"] == "success"
        assert len(data_ops["steps"]) == 2

        # 5. commit_staged_bundle
        res_commit = await mcp.call_tool("commit_staged_bundle", {"bundle_id": bundle_id})
        data_commit = json.loads(_extract_text(res_commit))
        assert data_commit["status"] == "staged"
        assert data_commit["total_steps"] == 2

    asyncio.run(_run())


def test_bundle_immutability_and_empty_apply_all(test_setup):
    """Vérifie la protection contre le re-commit, l'ajout sur bundle clos, et l'apply_all vide."""
    bundle_id = StagedPatchRegistry.begin_bundle(title="Bundle Immuable")
    p1 = StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": "Test Immuable"},
        bundle_id=bundle_id,
    )
    assert p1.bundle.bundle_id == bundle_id
    StagedPatchRegistry.commit_bundle(bundle_id)

    # 1. Re-commit d'un bundle déjà 'pending' doit être rejeté
    with pytest.raises(ValueError, match="ne peut pas être scellé"):
        StagedPatchRegistry.commit_bundle(bundle_id)

    # 2. create_patch ciblant ce bundle clos ne s'y rattache pas
    p2 = StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": "Hors Bundle"},
        bundle_id=bundle_id,
    )
    assert p2.bundle is None

    # 3. Rejeter la seule étape du bundle
    StagedPatchRegistry.reject_bundle_step(bundle_id, step_order=1, reason="Test rejet total")

    # 4. apply_bundle_all sur ce bundle sans étapes pending doit renvoyer une erreur
    res_apply = StagedPatchRegistry.apply_bundle_all(bundle_id)
    assert res_apply["status"] == "error"
    assert "Aucune étape en attente" in res_apply["message"]
