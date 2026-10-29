"""Tests unitaires pour le filtrage et la sécurisation des agents dédiés au MCP."""

import json

import pytest

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_personas():
    """Crée un ensemble de personas pour tester les autorisations."""
    p_universal = PersonaModel.create(
        name="Agent Universel Test",
        persona_type="universal",
        allowed_tools=json.dumps(["*"]),
        system_prompt="Prompt universel",
    )
    p_wozniak = PersonaModel.create(
        name="Agent Wozniak Test",
        persona_type="mcp",
        allowed_tools=json.dumps(["audit_deck_wozniak", "find_duplicate_cards"]),
        system_prompt="Prompt wozniak",
    )
    p_empty = PersonaModel.create(
        name="Agent Empty Test",
        persona_type="mcp",
        allowed_tools="[]",
        system_prompt="Prompt vide",
    )
    return {
        "universal": p_universal,
        "wozniak": p_wozniak,
        "empty": p_empty,
    }


def test_mcp_tool_registry_agent_methods(sample_personas):
    """Vérifie les méthodes list_mcp_agents et get_mcp_agent_details."""
    list_str = MCPToolRegistry.list_mcp_agents(scope="all")
    assert "Agent Wozniak Test" in list_str
    assert "Agent Universel Test" in list_str

    details = MCPToolRegistry.get_mcp_agent_details("Agent Wozniak Test")
    assert "Agent Wozniak Test" in details
    assert "audit_deck_wozniak" in details
    assert "Prompt wozniak" in details
