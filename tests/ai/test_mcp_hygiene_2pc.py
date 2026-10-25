"""Tests d'intégration et de sécurité Two-Phase Commit (2PC) pour l'hygiène, les suppressions et la restructuration.

Conforme à l'ADR 0042, l'ADR 0043 et aux exigences du ticket 'Hygiène : 100% 2PC sur suppressions, restructuration de paquets et correctifs'.
Garantit qu'aucune suppression ou mutation destructive n'a lieu en base sans validation explicite.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

pytestmark = pytest.mark.integration


def _extract_text(res: Any) -> str:
    """Helper canonique d'extraction du texte d'un CallToolResult."""
    return str(res.content[0].text) if hasattr(res, "content") and res.content else str(res)


@pytest.fixture
def hygiene_env(mock_db: Any) -> dict[str, Any]:
    """Prépare un environnement de test avec paquets, modèles de note et cartes."""
    deck_main = DeckModel.create(name="Sciences::Physique")
    deck_fallback = DeckModel.create(name="Poubelle::Archives")

    fields = json.dumps([{"name": "Front"}, {"name": "Back"}])
    templates = json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}])
    nt = NoteTypeModel.create(
        name="Basique Test 2PC",
        fields_schema=fields,
        templates=templates,
        css_style=".card { font-family: arial; }",
    )

    # Note 1 avec carte
    n1 = NoteModel.create(note_type=nt, tags="sciences, physique")
    n1.add_version({"Front": "Quelle est la vitesse de la lumière ?", "Back": "300 000 km/s"}, source="test")
    c1 = CardModel.create(note=n1, deck=deck_main, template_index=0)

    # Note 2 avec carte
    n2 = NoteModel.create(note_type=nt, tags="sciences")
    n2.add_version({"Front": "Formule de la relativité ?", "Back": "E=mc^2"}, source="test")
    c2 = CardModel.create(note=n2, deck=deck_main, template_index=0)

    return {
        "deck_main": deck_main,
        "deck_fallback": deck_fallback,
        "nt": nt,
        "n1": n1,
        "n2": n2,
        "c1": c1,
        "c2": c2,
    }


def test_propose_card_deletion_requires_2pc(hygiene_env: dict[str, Any]) -> None:
    """Vérifie que propose_card_deletion génère un StagedPatch sans supprimer la note en base."""

    async def _run() -> None:
        n1 = hygiene_env["n1"]
        c1 = hygiene_env["c1"]

        # 1. Appel de l'outil MCP
        res = await mcp.call_tool("propose_card_deletion", {"note_id": n1.id, "reason": "Carte obsolète"})
        payload = json.loads(_extract_text(res))

        assert payload["status"] == "staged"
        assert payload["patch_type"] == "note_delete"
        assert payload["note_id"] == n1.id
        patch_id = payload["patch_id"]
        assert patch_id.startswith("patch_")

        # 2. Sécurité : La note et la carte sont TOUJOURS en base SQLite
        assert NoteModel.get_or_none(NoteModel.id == n1.id) is not None
        assert CardModel.get_or_none(CardModel.id == c1.id) is not None

        # 3. Application explicite du patch
        res_apply = StagedPatchRegistry.apply_staged_patch(patch_id)
        assert res_apply["status"] == "applied"
        assert res_apply["deleted_count"] == 1

        # 4. Confirmation de suppression effective post-validation
        assert NoteModel.get_or_none(NoteModel.id == n1.id) is None
        assert CardModel.get_or_none(CardModel.id == c1.id) is None

    asyncio.run(_run())


def test_propose_card_deletion_optimistic_conflict(hygiene_env: dict[str, Any]) -> None:
    """Vérifie le conflit optimiste si la note est modifiée entre la proposition et la validation."""

    async def _run() -> None:
        n1 = hygiene_env["n1"]

        # 1. Création de la proposition
        res = await mcp.call_tool("propose_card_deletion", {"note_id": n1.id, "reason": "Doublon présumé"})
        payload = json.loads(_extract_text(res))
        patch_id = payload["patch_id"]

        # 2. Modification concurrente de la note
        n1.add_version({"Front": "Version modifiée concurrente", "Back": "Nouvelle réponse"}, source="user_edit")

        # 3. Tentative d'application du patch -> Rejet pour conflit optimiste
        res_apply = StagedPatchRegistry.apply_staged_patch(patch_id)
        assert res_apply["status"] == "conflict"
        assert "Conflit de version" in res_apply["message"]

        # 4. Sécurité : La note n'a pas été supprimée
        assert NoteModel.get_or_none(NoteModel.id == n1.id) is not None

    asyncio.run(_run())


def test_propose_batch_card_deletion_requires_2pc(hygiene_env: dict[str, Any]) -> None:
    """Vérifie la suppression groupée de cartes sous Two-Phase Commit."""

    async def _run() -> None:
        n1 = hygiene_env["n1"]
        n2 = hygiene_env["n2"]

        # 1. Proposition groupée
        ids_json = json.dumps([n1.id, n2.id])
        res = await mcp.call_tool("propose_batch_card_deletion", {"note_ids_json": ids_json, "reason": "Purge lot"})
        payload = json.loads(_extract_text(res))

        assert payload["status"] == "staged"
        assert payload["patch_type"] == "batch_note_delete"
        assert payload["notes_count"] == 2
        patch_id = payload["patch_id"]

        # 2. Sécurité : Aucune suppression en base
        assert NoteModel.get_or_none(NoteModel.id == n1.id) is not None
        assert NoteModel.get_or_none(NoteModel.id == n2.id) is not None

        # 3. Application du patch
        res_apply = StagedPatchRegistry.apply_staged_patch(patch_id)
        assert res_apply["status"] == "applied"
        assert res_apply["deleted_count"] == 2

        # 4. Suppression confirmée
        assert NoteModel.get_or_none(NoteModel.id == n1.id) is None
        assert NoteModel.get_or_none(NoteModel.id == n2.id) is None

    asyncio.run(_run())


def test_propose_deck_rename_requires_2pc(hygiene_env: dict[str, Any]) -> None:
    """Vérifie que propose_deck_rename génère un patch sans altération directe de la base."""

    async def _run() -> None:
        deck = hygiene_env["deck_main"]
        old_name = deck.name
        new_name = "Sciences::Astrophysique"

        # 1. Proposition de renommage
        res = await mcp.call_tool("propose_deck_rename", {"old_name": old_name, "new_name": new_name, "reason": "Précision disciplinaire"})
        payload = json.loads(_extract_text(res))

        assert payload["status"] == "staged"
        assert payload["patch_type"] == "deck_rename"
        assert payload["old_name"] == old_name
        assert payload["new_name"] == new_name
        patch_id = payload["patch_id"]

        # 2. Sécurité : Le nom en base est inchangé
        d_check = DeckModel.get_by_id(deck.id)
        assert d_check.name == old_name

        # 3. Application du patch
        res_apply = StagedPatchRegistry.apply_staged_patch(patch_id)
        assert res_apply["status"] == "applied"

        # 4. Le nom est désormais mis à jour
        d_updated = DeckModel.get_by_id(deck.id)
        assert d_updated.name == new_name

    asyncio.run(_run())


def test_propose_deck_deletion_with_card_migration_requires_2pc(hygiene_env: dict[str, Any]) -> None:
    """Vérifie que la suppression d'un paquet sous 2PC réassigne optionnellement les cartes."""

    async def _run() -> None:
        deck_main = hygiene_env["deck_main"]
        deck_fallback = hygiene_env["deck_fallback"]
        c1 = hygiene_env["c1"]

        # 1. Proposition de suppression avec réassignation des cartes vers deck_fallback
        res = await mcp.call_tool(
            "propose_deck_deletion",
            {
                "deck_name": deck_main.name,
                "move_cards_to_deck": deck_fallback.name,
                "reason": "Démantèlement de section",
            },
        )
        payload = json.loads(_extract_text(res))

        assert payload["status"] == "staged"
        assert payload["patch_type"] == "deck_delete"
        assert payload["deck_name"] == deck_main.name
        assert payload["move_cards_to_deck"] == deck_fallback.name
        patch_id = payload["patch_id"]

        # 2. Sécurité : Le paquet existe toujours et la carte y est rattachée
        assert DeckModel.get_or_none(DeckModel.name == deck_main.name) is not None
        c1_check = CardModel.get_by_id(c1.id)
        assert c1_check.deck_id == deck_main.id

        # 3. Application du patch
        res_apply = StagedPatchRegistry.apply_staged_patch(patch_id)
        assert res_apply["status"] == "applied"

        # 4. Le paquet d'origine est supprimé et la carte est déplacée vers le paquet de repli
        assert DeckModel.get_or_none(DeckModel.name == deck_main.name) is None
        c1_moved = CardModel.get_by_id(c1.id)
        assert c1_moved.deck_id == deck_fallback.id

    asyncio.run(_run())


def test_delete_empty_cards_is_staged_2pc(hygiene_env: dict[str, Any]) -> None:
    """Vérifie que delete_empty_cards passe obligatoirement par un StagedPatch (patch_type='empty_cards_delete')."""

    async def _run() -> None:
        nt = hygiene_env["nt"]
        deck = hygiene_env["deck_main"]

        # Création d'une note à front vide avec carte
        n_empty = NoteModel.create(note_type=nt)
        n_empty.add_version({"Front": "   <div></div>   ", "Back": "Explication"}, source="test")
        c_empty = CardModel.create(note=n_empty, deck=deck, template_index=0)

        # 1. Appel de delete_empty_cards (même avec confirm=True !)
        res = await mcp.call_tool("delete_empty_cards", {"confirm": True})
        payload = json.loads(_extract_text(res))

        # Doit être staged, JAMAIS supprimé directement
        assert payload["status"] == "staged"
        assert payload["patch_type"] == "empty_cards_delete"
        assert payload["empty_cards_count"] == 1
        assert c_empty.id in payload["card_ids"]
        patch_id = payload["patch_id"]

        # 2. Sécurité : La carte vide existe toujours en base
        assert CardModel.get_or_none(CardModel.id == c_empty.id) is not None

        # 3. Application du patch
        res_apply = StagedPatchRegistry.apply_staged_patch(patch_id)
        assert res_apply["status"] == "applied"
        assert res_apply["deleted_count"] == 1

        # 4. La carte vide est désormais supprimée
        assert CardModel.get_or_none(CardModel.id == c_empty.id) is None

    asyncio.run(_run())


def test_propose_css_tune_creates_staged_patch(hygiene_env: dict[str, Any]) -> None:
    """Vérifie que propose_css_tune enregistre bien un StagedPatch et retourne son patch_id persistant."""

    async def _run() -> None:
        nt = hygiene_env["nt"]
        initial_css = nt.css_style

        # 1. Appel de propose_css_tune
        css_snippet = ".cloze { color: #00aa00; font-weight: bold; }"
        res = await mcp.call_tool("propose_css_tune", {"note_type_name": nt.name, "css_snippet": css_snippet})
        payload = json.loads(_extract_text(res))

        assert payload["type"] == "css"
        patch_id = payload.get("patch_id")
        assert patch_id is not None
        assert str(patch_id).startswith("patch_")

        # 2. Vérification que le patch est persistant en base
        patch = StagedPatchRegistry.get_patch(str(patch_id))
        assert patch is not None
        assert patch.patch_type == "css"

        # 3. Sécurité : Le CSS en base n'a pas encore changé
        nt_check = NoteTypeModel.get_by_id(nt.id)
        assert nt_check.css_style == initial_css

        # 4. Application du patch
        res_apply = StagedPatchRegistry.apply_staged_patch(str(patch_id))
        assert res_apply["status"] == "applied"

        # 5. Le CSS est désormais mis à jour
        nt_updated = NoteTypeModel.get_by_id(nt.id)
        assert "#00aa00" in nt_updated.css_style

    asyncio.run(_run())


def test_sanitize_fields_html_systematic_2pc(hygiene_env: dict[str, Any]) -> None:
    """Vérifie que sanitize_fields_html génère systématiquement un StagedPatch même pour 1 seule note."""

    async def _run() -> None:
        nt = hygiene_env["nt"]
        # Création d'une note unique avec HTML sale
        n = NoteModel.create(note_type=nt)
        n.add_version({"Front": '<span style="color:red;">Texte sale</span>', "Back": "Propre"}, source="test")

        # Appel sans force_apply (comportement agent) pour 1 seule note (< ancien seuil magique 5)
        res = await mcp.call_tool("sanitize_fields_html", {"note_ids": [n.id]})
        payload = json.loads(_extract_text(res))

        # Doit être staged_diff (Two-Phase Commit systématique)
        assert payload["status"] == "staged_diff"
        assert payload["modified_count"] == 1
        patch_id = payload["patch_id"]
        assert patch_id.startswith("patch_")

        # Sécurité : La version active en base est toujours la version sale
        v_current = NoteVersionModel.get(note=n, is_active=True)
        assert "style=" in v_current.content

        # Application du patch
        res_apply = StagedPatchRegistry.apply_staged_patch(patch_id)
        assert res_apply["status"] == "applied"

        # La version active en base est désormais propre
        v_clean = NoteVersionModel.get(note=n, is_active=True)
        assert "style=" not in v_clean.content
        assert "Texte sale" in v_clean.content

    asyncio.run(_run())


def test_propose_deck_deletion_rejects_subdeck_and_preserves_descendant_cards(hygiene_env: dict[str, Any]) -> None:
    """Vérifie l'interdiction de déplacer vers un sous-paquet et la préservation de toutes les cartes descendantes."""

    async def _run() -> None:
        nt = hygiene_env["nt"]
        deck_main = hygiene_env["deck_main"]  # Sciences::Physique
        deck_fallback = hygiene_env["deck_fallback"]  # Poubelle::Archives

        # 1. Création d'un sous-paquet avec une carte
        sub_deck = DeckModel.create(name="Sciences::Physique::Quantique")
        n_sub = NoteModel.create(note_type=nt)
        n_sub.add_version({"Front": "Qu'est-ce que l'intrication ?", "Back": "Un phénomène quantique"}, source="test")
        c_sub = CardModel.create(note=n_sub, deck=sub_deck, template_index=0)

        # 2. Rejet si move_cards_to_deck est un sous-paquet descendant du paquet supprimé
        res_reject = await mcp.call_tool(
            "propose_deck_deletion",
            {
                "deck_name": deck_main.name,
                "move_cards_to_deck": "Sciences::Physique::Quantique",
            },
        )
        payload_reject = json.loads(_extract_text(res_reject))
        assert payload_reject["status"] == "error"
        assert "sous-paquet" in payload_reject["message"]

        # 3. Proposition valide vers le paquet de repli : l'impact doit compter le parent ET le sous-paquet (2 cartes)
        res_valid = await mcp.call_tool(
            "propose_deck_deletion",
            {
                "deck_name": deck_main.name,
                "move_cards_to_deck": deck_fallback.name,
                "reason": "Suppression avec sous-paquets",
            },
        )
        payload_valid = json.loads(_extract_text(res_valid))
        assert payload_valid["status"] == "staged"
        assert payload_valid["cards_count"] == 3  # c1 (dans Physique) + c2 (dans Physique) + c_sub (dans Quantique)
        patch_id = payload_valid["patch_id"]

        # 4. Application du patch : toutes les cartes (parent et sous-paquet) sont migrées vers deck_fallback
        res_apply = StagedPatchRegistry.apply_staged_patch(patch_id)
        assert res_apply["status"] == "applied"

        c_sub_check = CardModel.get_by_id(c_sub.id)
        assert c_sub_check.deck_id == deck_fallback.id

    asyncio.run(_run())
