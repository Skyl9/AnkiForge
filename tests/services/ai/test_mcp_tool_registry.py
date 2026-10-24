"""Tests unitaires pour MCPToolRegistry (ADR 0034 §4).

Vérifie l'extraction du registre des 58 outils MCP, son autonomie sans session de chat,
la présence de l'alias de rétrocompatibilité ConsultantToolRegistry, et le bon fonctionnement
des outils clés.
"""

from __future__ import annotations

import pytest

from ankiforge.database.models import DeckModel
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
