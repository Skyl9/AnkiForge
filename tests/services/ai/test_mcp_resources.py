"""Tests d'intégration pour les Resources MCP (ADR 0034 §4).

Vérifie l'enregistrement et le bon fonctionnement des resources MCP exposées
par le serveur (docs://, agents://, workspace://, ankiforge://schema/{table}).
"""

from __future__ import annotations

import json

import pytest

from ankiforge.services.ai.mcp_server import mcp

pytestmark = pytest.mark.integration


def test_mcp_resource_docs_topics_registered():
    """Vérifie que la resource docs://topics est enregistrée."""
    tools_and_resources = mcp._resource_manager.list_resources()
    resource_uris = [r.uri for r in tools_and_resources]
    assert "docs://topics" in resource_uris


def test_mcp_resource_docs_page_template_works(mock_db):
    """Vérifie que la resource template docs://page/{doc_path} fonctionne."""
    from ankiforge.services.ai.mcp_server import get_doc_page_resource

    # Appel direct - devrait retourner une erreur 404 mais pas planter
    result = get_doc_page_resource("nonexistent/path")
    assert isinstance(result, str)
    assert "Erreur" in result or "n'a pas été trouvée" in result


def test_mcp_resource_agents_list_registered():
    """Vérifie que la resource agents://list est enregistrée."""
    tools_and_resources = mcp._resource_manager.list_resources()
    resource_uris = [r.uri for r in tools_and_resources]
    assert "agents://list" in resource_uris


def test_mcp_resource_agents_template_works(mock_db):
    """Vérifie que la resource template agents://{agent_name} fonctionne."""
    from ankiforge.services.ai.mcp_server import get_agent_profile_resource

    result = get_agent_profile_resource("nonexistent_agent")
    assert isinstance(result, str)
    # Doit retourner les détails de l'agent ou une erreur
    assert "Erreur" in result or "Aucun agent" in result or "introuvable" in result


def test_mcp_resource_workspace_agent_guide_registered():
    """Vérifie que la resource workspace://agent-guide est enregistrée."""
    tools_and_resources = mcp._resource_manager.list_resources()
    resource_uris = [r.uri for r in tools_and_resources]
    assert "workspace://agent-guide" in resource_uris


def test_mcp_resource_ankiforge_schema_template_works(mock_db):
    """Vérifie que le template de resource ankiforge://schema/{table_name} fonctionne."""
    from ankiforge.services.ai.mcp_server import get_table_schema_resource

    # Appel direct - doit fonctionner pour une table valide
    result = get_table_schema_resource("notemodel")
    data = json.loads(result)
    assert data["table_name"] == "notemodel"
    assert "columns" in data


def test_mcp_resource_ankiforge_schema_read_notes(mock_db):
    """Vérifie la lecture de la resource ankiforge://schema/notemodel."""
    from ankiforge.services.ai.mcp_server import get_table_schema_resource

    result = get_table_schema_resource("notemodel")
    data = json.loads(result)

    assert data["table_name"] == "notemodel"
    assert isinstance(data["columns"], list)
    assert len(data["columns"]) >= 7

    col_names = {c["name"] for c in data["columns"]}
    assert "id" in col_names
    assert "guid" in col_names
    assert "note_type_id" in col_names
    assert "tags" in col_names

    # Vérifier la structure complète
    assert "indexes" in data
    assert "foreign_keys" in data
    assert "constraints" in data


def test_mcp_resource_ankiforge_schema_read_cards(mock_db):
    """Vérifie la lecture de la resource ankiforge://schema/cardmodel."""
    from ankiforge.services.ai.mcp_server import get_table_schema_resource

    result = get_table_schema_resource("cardmodel")
    data = json.loads(result)

    assert data["table_name"] == "cardmodel"
    col_names = {c["name"] for c in data["columns"]}
    assert "id" in col_names
    assert "note_id" in col_names
    assert "deck_id" in col_names
    assert "ivl" in col_names
    assert "reps" in col_names
    assert "lapses" in col_names
    assert "flags" in col_names


def test_mcp_resource_ankiforge_schema_read_decks(mock_db):
    """Vérifie la lecture de la resource ankiforge://schema/deckmodel."""
    from ankiforge.services.ai.mcp_server import get_table_schema_resource

    result = get_table_schema_resource("deckmodel")
    data = json.loads(result)

    assert data["table_name"] == "deckmodel"
    col_names = {c["name"] for c in data["columns"]}
    assert "id" in col_names
    assert "name" in col_names
    assert "description" in col_names


def test_mcp_resource_ankiforge_schema_rejects_sqlite_master(mock_db):
    """Vérifie que les tables système sont rejetées avec erreur FORBIDDEN."""
    from ankiforge.services.ai.mcp_server import get_table_schema_resource

    result = get_table_schema_resource("sqlite_master")
    data = json.loads(result)

    assert data["status"] == "error"
    assert data["error_code"] == "FORBIDDEN"
    msg = data["message"].lower()
    assert "non autorisée" in msg or "forbidden" in msg


def test_mcp_resource_ankiforge_schema_rejects_llm_configs(mock_db):
    """Vérifie que les tables sensibles sont rejetées avec erreur FORBIDDEN."""
    from ankiforge.services.ai.mcp_server import get_table_schema_resource

    result = get_table_schema_resource("llm_configs")
    data = json.loads(result)

    assert data["status"] == "error"
    assert data["error_code"] == "FORBIDDEN"


def test_mcp_resource_ankiforge_schema_rejects_unknown_table(mock_db):
    """Vérifie que les tables inconnues sont rejetées (non dans l'allow-list)."""
    from ankiforge.services.ai.mcp_server import get_table_schema_resource

    result = get_table_schema_resource("nonexistent_table")
    data = json.loads(result)

    assert data["status"] == "error"
    # Rejeté par l'allow-list (FORBIDDEN) car pas dans _ALLOWED_SCHEMA_TABLES
    assert data["error_code"] == "FORBIDDEN"


def test_mcp_resource_ankiforge_schema_case_insensitive(mock_db):
    """Vérifie que le nom de table est traité de manière insensible à la casse."""
    from ankiforge.services.ai.mcp_server import get_table_schema_resource

    result_lower = json.loads(get_table_schema_resource("notemodel"))
    result_upper = json.loads(get_table_schema_resource("NOTEMODEL"))
    result_mixed = json.loads(get_table_schema_resource("NoteModel"))

    assert result_lower["table_name"] == "notemodel"
    assert result_upper["table_name"] == "notemodel"
    assert result_mixed["table_name"] == "notemodel"


def test_mcp_resource_docs_topics_read(mock_db):
    """Vérifie la lecture de la resource docs://topics."""
    from ankiforge.services.ai.mcp_server import get_docs_topics_resource

    result = get_docs_topics_resource()
    assert isinstance(result, str)
    assert len(result) > 0


def test_mcp_resource_agents_list_read(mock_db):
    """Vérifie la lecture de la resource agents://list."""
    from ankiforge.services.ai.mcp_server import get_agents_list_resource

    result = get_agents_list_resource()
    assert isinstance(result, str)
    assert len(result) > 0
