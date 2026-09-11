"""Tests unitaires pour les outils et ressources de documentation dans MCP et Consultant IA."""

from ankiforge.services.ai.consultant_engine import ConsultantEngine, ConsultantToolRegistry
from ankiforge.services.ai.mcp_server import mcp


def test_consultant_tool_registry_doc_tools():
    """Vérifie que les méthodes statiques du registry délèguent correctement vers AppDocumentationService."""
    # 1. Recherche doc
    res_search = ConsultantToolRegistry.search_app_documentation("wozniak", limit=3)
    assert "Résultats de recherche" in res_search
    assert "linter_wozniak.md" in res_search or "Wozniak" in res_search

    # 2. Lecture page doc
    res_read = ConsultantToolRegistry.read_app_doc_page("features/consultant_mcp.md")
    assert "Documentation : `features/consultant_mcp.md`" in res_read
    assert "ReAct" in res_read

    # 3. Liste des sujets
    res_topics = ConsultantToolRegistry.list_app_doc_topics()
    assert "Sommaire de la Documentation" in res_topics

    # 4. Aide rapide
    res_help = ConsultantToolRegistry.get_feature_quick_help("katex")
    assert "Éditeur de Notes KaTeX" in res_help


def test_consultant_engine_execute_doc_tool_calls():
    """Vérifie que le moteur du Consultant dispatche correctement les 4 nouveaux outils."""
    engine = ConsultantEngine()

    # Tool search_app_documentation
    obs, is_err = engine._execute_tool_call("search_app_documentation", {"query": "dag", "limit": 2})
    assert not is_err
    assert "Résultats de recherche" in obs

    # Tool read_app_doc_page
    obs, is_err = engine._execute_tool_call("read_app_doc_page", {"doc_path": "features/editeur_notes_katex.md"})
    assert not is_err
    assert "KaTeX" in obs

    # Tool list_app_doc_topics
    obs, is_err = engine._execute_tool_call("list_app_doc_topics", {})
    assert not is_err
    assert "Sommaire" in obs

    # Tool get_feature_quick_help
    obs, is_err = engine._execute_tool_call("get_feature_quick_help", {"feature_name": "ollama"})
    assert not is_err
    assert "Ollama" in obs


def test_mcp_server_doc_tools_and_resources():
    """Vérifie que le serveur FastMCP expose les outils, ressources et prompts de documentation."""
    import asyncio

    async def _run():
        # Vérification des outils enregistrés
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "search_app_documentation" in tool_names
        assert "read_app_doc_page" in tool_names
        assert "list_app_doc_topics" in tool_names
        assert "get_feature_quick_help" in tool_names

        # Vérification des ressources enregistrées
        resources = await mcp.list_resources()
        resource_uris = [r.uri for r in resources]
        assert any("docs://topics" in str(uri) for uri in resource_uris)

        # Vérification des prompts enregistrés
        prompts = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts]
        assert "explain_ankiforge_feature" in prompt_names
        assert "audit_architecture_compliance" in prompt_names

        # Appel d'un outil via FastMCP
        call_res = await mcp.call_tool("get_feature_quick_help", {"feature_name": "wozniak"})
        assert call_res is not None
        assert any("Wozniak" in str(c) for c in call_res)

    asyncio.run(_run())
