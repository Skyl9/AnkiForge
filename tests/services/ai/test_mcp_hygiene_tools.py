"""Tests d'intégration pour les outils MCP d'hygiène en masse via la surface mcp.call_tool().

Couvre :
- sanitize_fields_html (nettoyage direct, 2-phase commit sur grand volume, preview_and_apply_patch)
- set_tags_bulk (ajout, retrait, écrivain canonique, protection des tags de traçabilité)
- delete_unused_note_type (garde-fou 0 note, confirmation requise, all_unused)
- move_cards_to_deck (déplacement cartes, sous-paquets hiérarchiques)
- list_empty_cards / delete_empty_cards (détection cartes à front vide, confirmation requise, suppression)
- notification des mutations via register_mutation_listener
"""

import asyncio
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
from ankiforge.services.ai.mcp_server import mcp, register_mutation_listener, unregister_mutation_listener
from ankiforge.utils.tags import parse_note_tags

pytestmark = pytest.mark.integration


def _extract_text(tool_result) -> str:
    if hasattr(tool_result, "content") and tool_result.content:
        return tool_result.content[0].text
    return str(tool_result)


@pytest.fixture
def mcp_hygiene_setup(mock_db):
    uid = uuid.uuid4().hex[:6]
    deck_main = DeckModel.create(name=f"Deck_MCP_{uid}")
    nt_main = NoteTypeModel.create(
        name=f"Model_MCP_{uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Standard", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]),
    )
    nt_second = NoteTypeModel.create(
        name=f"Model_Unused_{uid}",
        fields_schema=json.dumps(["Q", "A"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Q}}", "afmt": "{{A}}"}]),
    )

    n1 = NoteModel.create(note_type=nt_main, tags='["initial", "doc:guide_mcp"]')
    n1.add_version(
        {"Front": '<span style="font-size:12px;">Question avec <font color="red">couleur</font></span>', "Back": "Réponse"},
        source="init",
    )
    c1 = CardModel.create(note=n1, deck=deck_main, template_index=0)

    return {
        "deck_main": deck_main,
        "nt_main": nt_main,
        "nt_second": nt_second,
        "n1": n1,
        "c1": c1,
        "uid": uid,
    }


def test_mcp_sanitize_fields_html_direct_and_staged(mcp_hygiene_setup):
    """Vérifie le nettoyage HTML via MCP en direct et en Two-Phase Commit."""

    async def _run():
        n1 = mcp_hygiene_setup["n1"]
        nt = mcp_hygiene_setup["nt_main"]

        # 1. Nettoyage direct avec force_apply=True
        res_direct = await mcp.call_tool(
            "sanitize_fields_html",
            {
                "note_ids": [n1.id],
                "force_apply": True,
            },
        )
        data_direct = json.loads(_extract_text(res_direct))
        assert data_direct["status"] == "applied"
        assert data_direct["modified_count"] == 1

        v1 = NoteVersionModel.get(note=n1, is_active=True)
        c1 = json.loads(v1.content)
        assert "style=" not in c1["Front"]
        assert "<font" not in c1["Front"]
        assert "Question avec couleur" in c1["Front"]

        # 2. Création de notes pour déclencher le staged patch (Two-Phase Commit)
        created_notes = []
        for i in range(4):
            n = NoteModel.create(note_type=nt)
            n.add_version({"Front": f'<p style="color:red;">Item {i}</p>', "Back": "B"}, source="init")
            created_notes.append(n)

        note_ids_staged = [n.id for n in created_notes]
        res_staged = await mcp.call_tool(
            "sanitize_fields_html",
            {
                "note_ids": note_ids_staged,
                "stage_threshold": 2,  # 4 notes > 2 -> staged_diff
                "force_apply": False,
            },
        )
        data_staged = json.loads(_extract_text(res_staged))
        assert data_staged["status"] == "staged_diff"
        patch_id = data_staged["patch_id"]
        assert patch_id.startswith("patch_")

        # Application du patch via preview_and_apply_patch
        res_apply = await mcp.call_tool("preview_and_apply_patch", {"patch_id": patch_id})
        data_apply = json.loads(_extract_text(res_apply))
        assert data_apply["status"] == "applied"

        # Vérifier que les notes ont été mises à jour
        v_applied = NoteVersionModel.get(note=created_notes[0], is_active=True)
        c_applied = json.loads(v_applied.content)
        assert "style=" not in c_applied["Front"]
        assert "Item 0" in c_applied["Front"]

    asyncio.run(_run())


def test_mcp_set_tags_bulk(mcp_hygiene_setup):
    """Vérifie la gestion des tags en masse via MCP."""

    async def _run():
        n1 = mcp_hygiene_setup["n1"]

        # Ajout de tags
        res_add = await mcp.call_tool(
            "set_tags_bulk",
            {
                "note_ids": [n1.id],
                "tags": ["examen", "japonais"],
                "mode": "add",
            },
        )
        data_add = json.loads(_extract_text(res_add))
        assert data_add["status"] == "success"

        n1_reloaded = NoteModel.get_by_id(n1.id)
        tags = parse_note_tags(n1_reloaded.tags)
        assert "examen" in tags
        assert "japonais" in tags
        assert "doc:guide_mcp" in tags

        # Retrait d'un tag
        res_rem = await mcp.call_tool(
            "set_tags_bulk",
            {
                "note_ids": [n1.id],
                "tags": ["examen"],
                "mode": "remove",
            },
        )
        data_rem = json.loads(_extract_text(res_rem))
        assert data_rem["status"] == "success"

        tags_after = parse_note_tags(NoteModel.get_by_id(n1.id).tags)
        assert "examen" not in tags_after
        assert "japonais" in tags_after

    asyncio.run(_run())


def test_mcp_delete_unused_note_type(mcp_hygiene_setup):
    """Vérifie le garde-fou référentiel et la confirmation pour la suppression de modèle via MCP."""

    async def _run():
        nt_main = mcp_hygiene_setup["nt_main"]
        nt_second = mcp_hygiene_setup["nt_second"]

        # 1. Refus car utilisé par n1
        res_busy = await mcp.call_tool(
            "delete_unused_note_type",
            {
                "name": nt_main.name,
                "confirm": True,
            },
        )
        data_busy = json.loads(_extract_text(res_busy))
        assert data_busy["status"] == "error"
        assert "note(s) y sont rattachées" in data_busy["message"]

        # 2. Confirmation requise quand confirm=False
        res_conf = await mcp.call_tool(
            "delete_unused_note_type",
            {
                "name": nt_second.name,
                "confirm": False,
            },
        )
        data_conf = json.loads(_extract_text(res_conf))
        assert data_conf["status"] == "confirmation_required"

        # 3. Suppression validée avec confirm=True
        res_del = await mcp.call_tool(
            "delete_unused_note_type",
            {
                "name": nt_second.name,
                "confirm": True,
            },
        )
        data_del = json.loads(_extract_text(res_del))
        assert data_del["status"] == "deleted"
        assert NoteTypeModel.get_or_none(NoteTypeModel.id == nt_second.id) is None

    asyncio.run(_run())


def test_mcp_move_cards_to_deck(mcp_hygiene_setup):
    """Vérifie le déplacement de cartes vers un sous-paquet hiérarchique via MCP."""

    async def _run():
        c1 = mcp_hygiene_setup["c1"]
        d_main = mcp_hygiene_setup["deck_main"]
        target = f"{d_main.name}::Chapitre1"

        res = await mcp.call_tool(
            "move_cards_to_deck",
            {
                "card_ids": [c1.id],
                "deck": target,
            },
        )
        data = json.loads(_extract_text(res))
        assert data["status"] == "success"
        assert data["moved_count"] == 1

        c1_reloaded = CardModel.get_by_id(c1.id)
        assert c1_reloaded.deck.name == target
        assert c1_reloaded.deck.parent_deck.id == d_main.id

    asyncio.run(_run())


def test_mcp_list_and_delete_empty_cards(mcp_hygiene_setup):
    """Vérifie la détection et suppression des cartes à front vide via MCP."""

    async def _run():
        nt = mcp_hygiene_setup["nt_main"]
        deck = mcp_hygiene_setup["deck_main"]

        # Création d'une note à front vide
        n_empty = NoteModel.create(note_type=nt)
        n_empty.add_version({"Front": "<p>&nbsp;</p>", "Back": "Réponse"}, source="init")
        c_empty = CardModel.create(note=n_empty, deck=deck, template_index=0)

        # 1. Détection via list_empty_cards
        res_list = await mcp.call_tool("list_empty_cards", {})
        data_list = json.loads(_extract_text(res_list))
        assert data_list["status"] == "success"
        assert data_list["total_empty_cards"] >= 1
        found_ids = [item["card_id"] for item in data_list["empty_cards"]]
        assert c_empty.id in found_ids

        # 2. Sécurité Two-Phase Commit : delete_empty_cards prépare un StagedPatch sans suppression directe
        res_del = await mcp.call_tool("delete_empty_cards", {"confirm": True})
        data_del = json.loads(_extract_text(res_del))
        assert data_del["status"] == "staged"
        assert data_del["patch_type"] == "empty_cards_delete"
        patch_id = data_del["patch_id"]
        assert patch_id.startswith("patch_")
        assert CardModel.get_or_none(CardModel.id == c_empty.id) is not None

        # 3. Application du patch via preview_and_apply_patch
        res_apply = await mcp.call_tool("preview_and_apply_patch", {"patch_id": patch_id})
        data_apply = json.loads(_extract_text(res_apply))
        assert data_apply["status"] == "applied"
        assert CardModel.get_or_none(CardModel.id == c_empty.id) is None

    asyncio.run(_run())


def test_mcp_mutation_notification_listener(mcp_hygiene_setup):
    """Vérifie que les mutations d'hygiène via MCP notifient les écouteurs enregistrés."""

    async def _run():
        n1 = mcp_hygiene_setup["n1"]
        events_received = []

        def _on_mutation(data):
            events_received.append(data)

        register_mutation_listener(_on_mutation)
        try:
            await mcp.call_tool(
                "set_tags_bulk",
                {
                    "note_ids": [n1.id],
                    "tags": ["tag_notif_test"],
                    "mode": "add",
                },
            )
            assert len(events_received) >= 1
            last_event = events_received[-1]
            assert last_event.get("type") == "set_tags_bulk"
        finally:
            unregister_mutation_listener(_on_mutation)

    asyncio.run(_run())


def test_mcp_audit_tag_hygiene_and_merge(mcp_hygiene_setup):
    """Vérifie l'audit et la fusion de tags via les outils MCP audit_tag_hygiene et merge_tag_clusters."""

    async def _run():
        nt = mcp_hygiene_setup["nt_main"]
        n_a = NoteModel.create(note_type=nt, tags='["Cardiologie", "doc:99"]')
        _ = NoteModel.create(note_type=nt, tags='["cardiologie", "source:cours"]')

        res_audit = await mcp.call_tool("audit_tag_hygiene", {"include_levenshtein": True})
        audit_data = json.loads(_extract_text(res_audit))
        assert audit_data["status"] == "success"
        assert audit_data["total_clusters"] >= 1

        case_clusters = audit_data["case_clusters"]
        cardio_cluster = next((c for c in case_clusters if c["canonical_tag"].lower() == "cardiologie"), None)
        assert cardio_cluster is not None

        # Exécuter la fusion via MCP
        res_merge = await mcp.call_tool(
            "merge_tag_clusters",
            {
                "merges": [
                    {
                        "tags_to_merge": ["Cardiologie"],
                        "target_tag": "cardiologie",
                    }
                ]
            },
        )
        merge_data = json.loads(_extract_text(res_merge))
        assert merge_data["status"] == "success"
        assert merge_data["modified_notes_count"] >= 1

        # Vérifier en BDD
        tags_a = parse_note_tags(NoteModel.get_by_id(n_a.id).tags)
        assert "cardiologie" in tags_a
        assert "Cardiologie" not in tags_a
        assert "doc:99" in tags_a

        # Test audit avec deck_id inexistant
        res_audit_deck = await mcp.call_tool("audit_tag_hygiene", {"deck_id": 999999})
        audit_deck_data = json.loads(_extract_text(res_audit_deck))
        assert audit_deck_data["status"] == "success"
        assert audit_deck_data["total_clusters"] == 0

    asyncio.run(_run())
