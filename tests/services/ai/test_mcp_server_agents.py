"""Tests unitaires pour l'exposition des agents dédiés sur le serveur FastMCP."""

import asyncio
import json

import pytest

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.mcp_server import mcp


@pytest.fixture
def sample_mcp_agent():
    return PersonaModel.create(
        name="Agent MCP Spécialisé",
        description="Agent de test pour endpoints MCP",
        system_prompt="Tu es un agent spécialisé pour tester FastMCP.",
        persona_type="mcp",
        allowed_tools=json.dumps(["audit_deck_wozniak", "list_note_types"]),
    )


def test_mcp_server_agent_tools_and_resources(sample_mcp_agent):
    """Vérifie la présence et l'exécution des outils, ressources et prompts FastMCP."""

    async def _run():
        # 1. Vérification des outils
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "list_mcp_agents" in tool_names
        assert "get_mcp_agent_details" in tool_names
        assert "invoke_mcp_agent" in tool_names
        assert "create_or_update_mcp_agent" in tool_names

        # 2. Appel outil list_mcp_agents
        res_list = await mcp.call_tool("list_mcp_agents", {"scope": "all"})
        assert res_list is not None
        assert any("Agent MCP Spécialisé" in str(c) for c in res_list)

        # 3. Appel outil get_mcp_agent_details
        res_details = await mcp.call_tool("get_mcp_agent_details", {"agent_name": "Agent MCP Spécialisé"})
        assert res_details is not None
        assert any("audit_deck_wozniak" in str(c) for c in res_details)

        # 4. Appel outil create_or_update_mcp_agent
        res_create = await mcp.call_tool(
            "create_or_update_mcp_agent",
            {
                "name": "Nouvel Agent Créé",
                "description": "Agent créé dynamiquement via MCP",
                "system_prompt": "Prompt dynamique",
                "allowed_tools_json": '["search_document"]',
                "persona_type": "mcp",
            },
        )
        assert res_create is not None
        assert any("Succès" in str(c) for c in res_create)

        created_ag = PersonaModel.get_or_none(PersonaModel.name == "Nouvel Agent Créé")
        assert created_ag is not None
        assert created_ag.description == "Agent créé dynamiquement via MCP"

        # 5. Vérification des ressources
        resources = await mcp.list_resources()
        res_uris = [r.uri for r in resources]
        assert any("agents://list" in str(uri) for uri in res_uris)

        # 6. Vérification du prompt
        prompts = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts]
        assert "run_with_agent" in prompt_names

    asyncio.run(_run())
