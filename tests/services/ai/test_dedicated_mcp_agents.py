"""Tests unitaires pour le filtrage et la sécurisation des agents dédiés au MCP."""

import json

import pytest

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.consultant_engine import ConsultantEngine, ConsultantToolRegistry


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


def test_consultant_engine_allowed_tool_names(sample_personas):
    """Vérifie l'extraction et la résolution des outils autorisés."""
    # 1. Universel avec wildcard
    eng_univ = ConsultantEngine(persona=sample_personas["universal"])
    assert eng_univ._get_allowed_tool_names() is None
    assert eng_univ._is_tool_allowed("audit_deck_wozniak")
    assert eng_univ._is_tool_allowed("query_peewee")

    # 2. Agent restreint
    eng_woz = ConsultantEngine(persona=sample_personas["wozniak"])
    allowed = eng_woz._get_allowed_tool_names()
    assert allowed == {"audit_deck_wozniak", "find_duplicate_cards"}
    assert eng_woz._is_tool_allowed("audit_deck_wozniak")
    assert eng_woz._is_tool_allowed("find_duplicate_cards")
    assert not eng_woz._is_tool_allowed("query_peewee")
    assert not eng_woz._is_tool_allowed("execute_python_tool")

    # 3. Agent avec liste vide (rétrocompatible universel)
    eng_empty = ConsultantEngine(persona=sample_personas["empty"])
    assert eng_empty._get_allowed_tool_names() is None
    assert eng_empty._is_tool_allowed("query_peewee")


def test_consultant_engine_blocks_unauthorized_tool(sample_personas):
    """Vérifie que _execute_tool_call bloque tout outil non autorisé avec une alerte de sécurité."""
    eng_woz = ConsultantEngine(persona=sample_personas["wozniak"])

    # Tentative d'exécution d'un outil SQL interdit
    obs, is_err = eng_woz._execute_tool_call("query_peewee", {"sql_query": "SELECT * FROM notes"})
    assert is_err is True
    assert "⛔ Accès refusé" in obs
    assert "query_peewee" in obs
    assert "Agent Wozniak Test" in obs


def test_consultant_tool_registry_agent_methods(sample_personas):
    """Vérifie les méthodes list_mcp_agents et get_mcp_agent_details."""
    list_str = ConsultantToolRegistry.list_mcp_agents(scope="all")
    assert "Agent Wozniak Test" in list_str
    assert "Agent Universel Test" in list_str

    details = ConsultantToolRegistry.get_mcp_agent_details("Agent Wozniak Test")
    assert "Agent Wozniak Test" in details
    assert "audit_deck_wozniak" in details
    assert "Prompt wozniak" in details
