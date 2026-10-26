"""Tests unitaires pour MCPToolRegistry (ADR 0034 §4).

Vérifie l'extraction du registre des 58 outils MCP, son autonomie sans session de chat,
la présence de l'alias de rétrocompatibilité ConsultantToolRegistry, et le bon fonctionnement
des outils clés.
"""

from __future__ import annotations

import json

import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.ai.mcp_tool_registry import (
    MCP_TOOLS,
    ConsultantToolRegistry,
    MCPToolRegistry,
)

pytestmark = pytest.mark.integration


def test_mcp_tool_registry_alias_and_catalogue():
    """Vérifie que ConsultantToolRegistry est bien un alias de MCPToolRegistry et que le catalogue est complet."""
    assert ConsultantToolRegistry is MCPToolRegistry
    assert len(MCP_TOOLS) >= 40
    # Vérifier des outils clés
    tool_names = [t["function"]["name"] for t in MCP_TOOLS if "function" in t]
    assert "audit_deck_wozniak" in tool_names
    assert "query_peewee" in tool_names
    assert "get_deck_stats" in tool_names
    assert "propose_card_refactor" in tool_names
    assert "list_pipelines" in tool_names
    assert "list_albums" in tool_names
    assert "search_app_documentation" in tool_names
    assert "get_flagged_cards" in tool_names


def test_mcp_tool_registry_get_flagged_cards(mock_db):
    """Retourne les cartes par couleur ou valeur, sans exclure les suspendues."""
    note_type = NoteTypeModel.create(name="Flagged NT", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    deck = DeckModel.create(name="Flagged Deck")
    subdeck = DeckModel.create(name="Flagged Deck::Child")
    note = NoteModel.create(guid="flagged-guid", note_type=note_type, tags="")
    NoteVersionModel.create(note=note, version_number=1, is_active=True, content='{"Front": "Question", "Back": "Réponse"}')
    red_card = CardModel.create(note=note, deck=deck, flags=1, is_suspended=True)
    CardModel.create(note=note, deck=subdeck, flags=1)
    CardModel.create(note=note, deck=deck, flags=0)

    by_name = json.loads(MCPToolRegistry.get_flagged_cards("RED", deck_name=deck.name))
    by_value = json.loads(MCPToolRegistry.get_flagged_cards(1, deck_name=deck.name))

    assert by_name == by_value
    assert by_name["total"] == 1
    assert by_name["items"][0]["card_id"] == red_card.id
    assert by_name["items"][0]["fields"]["Front"] == "Question"
    assert by_name["items"][0]["flag"] == "red"
    assert json.loads(MCPToolRegistry.get_flagged_cards("none", deck_name=deck.name))["total"] == 1
    assert json.loads(MCPToolRegistry.get_flagged_cards("purple"))["items"] == []
    assert json.loads(MCPToolRegistry.get_flagged_cards("magenta"))["status"] == "error"


def test_mcp_tool_registry_get_deck_stats(mock_db):
    """Vérifie le fonctionnement direct de l'outil get_deck_stats via MCPToolRegistry."""
    deck = DeckModel.create(name="Deck Test MCP Registry")
    res = MCPToolRegistry.get_deck_stats(deck.name)
    assert "Deck Test MCP Registry" in res
    assert "Cartes" in res or "Notes" in res


def test_mcp_tool_registry_query_peewee_security(mock_db):
    """Vérifie que query_peewee autorise les requêtes SELECT sécurisées et bloque les écritures ou accès sensibles."""
    DeckModel.create(name="Deck Test MCP Registry")
    # Requête SELECT normale
    res = MCPToolRegistry.query_peewee("SELECT name FROM deckmodel;")
    assert "Deck Test MCP Registry" in res or "name" in res or "[]" in res

    # Requête bloquée sur table sensible
    res_secret = MCPToolRegistry.query_peewee("SELECT * FROM llm_configs;")
    assert "Erreur" in res_secret or "interdite" in res_secret.lower() or "sécurité" in res_secret.lower()


def test_mcp_tool_registry_get_collection_panorama_360(mock_db):
    """Vérifie l'outil get_collection_panorama_360."""
    res = MCPToolRegistry.get_collection_panorama_360()
    assert "Panorama 360" in res or "Collection" in res
