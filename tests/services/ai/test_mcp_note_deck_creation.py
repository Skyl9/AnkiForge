"""Tests TDD pour les outils MCP de création de paquets et de notes (Two-Phase Commit).

Couvre :
- list_decks & create_deck (écriture directe, arborescence '::', idempotence)
- create_note :
  - rejet strict des paquets inexistants (contrôle d'hallucination)
  - rejet des types de notes inexistants et clés inconnues
  - complétion des champs omis par chaîne vide
  - avertissement préventif de doublon non bloquant
  - staging Two-Phase Commit et application atomique
- create_notes_batch :
  - validation tout-ou-rien à la soumission
  - héritage par défaut et surcharges locales
  - staging groupé en un seul patch et application atomique
"""

import asyncio
import json
from typing import Any

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    StagedPatchModel,
    db,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_setup():
    """Initialise un environnement de test avec types de note et paquets."""
    with db.atomic():
        deck_lang = DeckModel.create(name="Langues")
        deck_jp = DeckModel.create(name="Langues::Japonais", parent_deck=deck_lang)

        nt_basic = NoteTypeModel.create(
            name="Basic Model MCP",
            fields_schema=json.dumps(["Front", "Back", "Notes"]),
            templates=json.dumps(
                [
                    {"name": "Standard", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}<br>{{Notes}}"},
                ]
            ),
            css_style=".card { color: black; }",
            description="Modèle basique",
        )

        nt_cloze = NoteTypeModel.create(
            name="Cloze Model MCP",
            fields_schema=json.dumps(["Text", "Extra"]),
            templates=json.dumps(
                [
                    {"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"},
                ]
            ),
            css_style=".card { color: blue; }",
            description="Modèle texte à trous",
        )

    return {
        "deck_lang": deck_lang,
        "deck_jp": deck_jp,
        "nt_basic": nt_basic,
        "nt_cloze": nt_cloze,
    }


def _extract_text(tool_result: Any) -> str:
    if hasattr(tool_result, "content") and tool_result.content:
        return str(tool_result.content[0].text)
    return str(tool_result)


def test_create_deck_and_list_decks(sample_setup):
    """Vérifie la création directe, hiérarchique et idempotente de paquets et list_decks."""

    async def _run() -> None:
        # 1. Lister les paquets initiaux
        res_list = await mcp.call_tool("list_decks", {})
        data_list = json.loads(_extract_text(res_list))
        assert data_list["status"] == "success"
        deck_names = [d["name"] for d in data_list["decks"]]
        assert "Langues" in deck_names
        assert "Langues::Japonais" in deck_names

        # 2. Créer un nouveau paquet hiérarchique
        res_create = await mcp.call_tool(
            "create_deck",
            {"deck_name": "Sciences::Physique::Quantique", "description": "Deck de physique"},
        )
        data_create = json.loads(_extract_text(res_create))
        assert data_create["status"] == "success"
        assert data_create["deck_name"] == "Sciences::Physique::Quantique"
        assert data_create["is_new"] is True

        # Vérifier en BDD que l'arborescence complète existe
        p_root = DeckModel.get_or_none(DeckModel.name == "Sciences")
        p_mid = DeckModel.get_or_none(DeckModel.name == "Sciences::Physique")
        p_leaf = DeckModel.get_or_none(DeckModel.name == "Sciences::Physique::Quantique")
        assert p_root is not None
        assert p_mid is not None
        assert p_leaf is not None
        assert p_mid.parent_deck.id == p_root.id
        assert p_leaf.parent_deck.id == p_mid.id

        # 3. Idempotence : recréer le même deck ne crée pas de doublon
        res_dup = await mcp.call_tool(
            "create_deck",
            {"deck_name": "Sciences::Physique::Quantique"},
        )
        data_dup = json.loads(_extract_text(res_dup))
        assert data_dup["status"] == "success"
        assert data_dup["is_new"] is False
        assert data_dup["deck_id"] == p_leaf.id

        # 4. Filtrage dans list_decks
        res_filter = await mcp.call_tool("list_decks", {"filter": "Quantique"})
        data_filter = json.loads(_extract_text(res_filter))
        assert len(data_filter["decks"]) == 1
        assert data_filter["decks"][0]["name"] == "Sciences::Physique::Quantique"

    asyncio.run(_run())


def test_create_note_hallucinated_deck_rejection(sample_setup):
    """Vérifie le rejet strict si le paquet cible n'existe pas en base."""

    async def _run() -> None:
        res = await mcp.call_tool(
            "create_note",
            {
                "note_type_name": "Basic Model MCP",
                "deck_name": "Deck::Inexistant::Fantome",
                "fields_json": json.dumps({"Front": "Question", "Back": "Réponse"}),
            },
        )
        data = json.loads(_extract_text(res))
        assert data["status"] == "error"
        assert "inexistant" in data["message"].lower() or "introuvable" in data["message"].lower()
        # Aucun StagedPatch ne doit être créé
        assert StagedPatchModel.select().count() == 0

    asyncio.run(_run())


def test_create_note_validation_errors(sample_setup):
    """Vérifie le rejet des types de notes inconnus, clés invalides et champs vides."""

    async def _run() -> None:
        # 1. Type de note inconnu
        res1 = await mcp.call_tool(
            "create_note",
            {
                "note_type_name": "TypeInexistant",
                "deck_name": "Langues::Japonais",
                "fields_json": json.dumps({"Front": "Q"}),
            },
        )
        data1 = json.loads(_extract_text(res1))
        assert data1["status"] == "error"
        assert "introuvable" in data1["message"].lower()

        # 2. Clé inconnue non présente dans le schéma
        res2 = await mcp.call_tool(
            "create_note",
            {
                "note_type_name": "Basic Model MCP",
                "deck_name": "Langues::Japonais",
                "fields_json": json.dumps({"Front": "Q", "CleInconnue": "V"}),
            },
        )
        data2 = json.loads(_extract_text(res2))
        assert data2["status"] == "error"
        assert "cleinconnue" in data2["message"].lower()

        # 3. Tous les champs vides
        res3 = await mcp.call_tool(
            "create_note",
            {
                "note_type_name": "Basic Model MCP",
                "deck_name": "Langues::Japonais",
                "fields_json": json.dumps({"Front": "", "Back": "   "}),
            },
        )
        data3 = json.loads(_extract_text(res3))
        assert data3["status"] == "error"
        assert "vide" in data3["message"].lower()

    asyncio.run(_run())


def test_create_note_success_flow_and_two_phase_commit(sample_setup):
    """Vérifie le flux complet : proposition staged, non persistance immédiate, puis application."""

    async def _run() -> None:
        initial_notes_count = NoteModel.select().count()
        initial_cards_count = CardModel.select().count()

        # 1. Proposer la note avec un champ omis ('Notes')
        res_stage = await mcp.call_tool(
            "create_note",
            {
                "note_type_name": "Basic Model MCP",
                "deck_name": "Langues::Japonais",
                "fields_json": json.dumps({"Front": "Neko", "Back": "Chat"}),
                "tags": "vocabulaire, facile",
            },
        )
        data_stage = json.loads(_extract_text(res_stage))
        assert data_stage["status"] == "staged"
        patch_id = data_stage["patch_id"]
        assert patch_id.startswith("patch_")

        # Vérifier que rien n'a été inséré en base pour le moment
        assert NoteModel.select().count() == initial_notes_count
        assert CardModel.select().count() == initial_cards_count

        # Vérifier le StagedPatch en attente
        patch = StagedPatchRegistry.get_patch(patch_id)
        assert patch is not None
        assert patch.status == "pending"
        assert patch.patch_type == "note_create"

        # 2. Appliquer le patch
        res_apply = await mcp.call_tool("apply_patch", {"patch_id": patch_id})
        data_apply = json.loads(_extract_text(res_apply))
        assert data_apply["status"] == "applied"
        created_note_id = data_apply["note_id"]

        # 3. Vérifications en BDD
        note = NoteModel.get_or_none(NoteModel.id == created_note_id)
        assert note is not None
        assert note.note_type.name == "Basic Model MCP"
        assert "vocabulaire" in note.tags
        assert "facile" in note.tags

        # Vérifier le contenu de la version
        version = note.versions.first()
        assert version is not None
        content = json.loads(version.content)
        assert content["Front"] == "Neko"
        assert content["Back"] == "Chat"
        assert content["Notes"] == ""  # Omis complété par chaîne vide

        # Vérifier la carte physique créée
        cards = list(note.cards)
        assert len(cards) == 1
        assert cards[0].deck.name == "Langues::Japonais"

    asyncio.run(_run())


def test_create_note_duplicate_warning(sample_setup):
    """Vérifie qu'une alerte non bloquante est générée si le premier champ existe déjà."""

    async def _run() -> None:
        # Créer d'abord une première note existante
        nt = sample_setup["nt_basic"]
        dk = sample_setup["deck_jp"]
        with db.atomic():
            n = NoteModel.create(note_type=nt)
            n.add_version({"Front": "Inu", "Back": "Chien", "Notes": ""})
            CardModel.create(note=n, deck=dk, template_index=0)

        # Proposer une seconde note avec le même Front ("Inu")
        res = await mcp.call_tool(
            "create_note",
            {
                "note_type_name": "Basic Model MCP",
                "deck_name": "Langues::Japonais",
                "fields_json": json.dumps({"Front": "Inu", "Back": "Un chien domestique"}),
            },
        )
        data = json.loads(_extract_text(res))
        assert data["status"] == "staged"
        assert len(data.get("warnings", [])) >= 1
        assert "doublon" in data["warnings"][0].lower()

    asyncio.run(_run())


def test_create_notes_batch_flow(sample_setup):
    """Vérifie le comportement de create_notes_batch (tout-ou-rien et application atomique)."""

    async def _run() -> None:
        # 1. Échec tout-ou-rien si une note a un paquet inexistant
        batch_bad = [
            {"fields": {"Front": "Un", "Back": "1"}},
            {"fields": {"Front": "Deux", "Back": "2"}, "deck": "Inexistant"},
        ]
        res_fail = await mcp.call_tool(
            "create_notes_batch",
            {
                "notes_json": json.dumps(batch_bad),
                "default_deck": "Langues::Japonais",
                "default_note_type": "Basic Model MCP",
            },
        )
        data_fail = json.loads(_extract_text(res_fail))
        assert data_fail["status"] == "error"
        assert "inexistant" in data_fail["message"].lower() or "introuvable" in data_fail["message"].lower()

        # 2. Succès du lot valide avec héritage et surcharges
        batch_good = [
            {"fields": {"Front": "Mizu", "Back": "Eau"}},
            {"fields": {"Front": "Hi", "Back": "Feu"}, "tags": ["nature"]},
            {
                "note_type": "Cloze Model MCP",
                "fields": {"Text": "La capitale du Japon est {{c1::Tokyo}}.", "Extra": "Grande ville"},
                "tags": ["geo"],
            },
        ]
        res_batch = await mcp.call_tool(
            "create_notes_batch",
            {
                "notes_json": json.dumps(batch_good),
                "default_deck": "Langues::Japonais",
                "default_note_type": "Basic Model MCP",
                "default_tags": "japonais",
            },
        )
        data_batch = json.loads(_extract_text(res_batch))
        assert data_batch["status"] == "staged"
        patch_id = data_batch["patch_id"]
        assert data_batch["count"] == 3

        # Vérifier que rien n'est encore en base
        assert NoteModel.select().where(NoteModel.tags.contains("japonais")).count() == 0

        # 3. Application du patch groupé
        res_apply = await mcp.call_tool("apply_patch", {"patch_id": patch_id})
        data_apply = json.loads(_extract_text(res_apply))
        assert data_apply["status"] == "applied"
        created_ids = data_apply["created_note_ids"]
        assert len(created_ids) == 3

        # Vérifier en BDD
        notes = list(NoteModel.select().where(NoteModel.id.in_(created_ids)))
        assert len(notes) == 3
        # La 3ème note doit avoir créé une carte cloze
        cloze_note = next(n for n in notes if n.note_type.name == "Cloze Model MCP")
        assert cloze_note.cards.count() == 1

    asyncio.run(_run())
