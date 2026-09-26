"""
Tests unitaires et d'intégration pour le pont RAG et les citations déterministes du Consultant IA (MCP-ADV-03).
"""

import json
from unittest.mock import patch

import pytest

from ankiforge.database.models import DocumentModel
from ankiforge.services.ai.consultant_engine import (
    _SYSTEM_PROMPT_TEMPLATE,
    DEFAULT_CONSULTANT_TOOLS,
    ConsultantEngine,
    ConsultantToolRegistry,
)
from ankiforge.services.ai.mcp_server import mcp

pytestmark = pytest.mark.integration


def test_search_knowledge_context_no_documents():
    """Vérifie le repli gracieux lorsqu'aucun document n'est indexé."""
    DocumentModel.delete().execute()
    res = ConsultantToolRegistry.search_knowledge_context("mitochondrie")
    assert "Aucun document" in res


def test_search_knowledge_context_no_results():
    """Vérifie le message quand la recherche ne retourne aucun résultat."""
    _doc = DocumentModel.create(title="Cours de Chimie.pdf", file_path="/fake/chimie.pdf", format="pdf")
    with patch("ankiforge.services.ai.rag_service.RAGService.search", return_value=[]):
        res = ConsultantToolRegistry.search_knowledge_context("concept_introuvable_xyz")
        assert "Aucun passage pertinent trouvé" in res


def test_search_knowledge_context_with_results():
    """Vérifie la génération des citations déterministes et du bloc structuré."""
    doc = DocumentModel.create(title="Biologie Cellulaire.pdf", file_path="/fake/bio.pdf", format="pdf")

    mock_chunks = [
        {
            "chunk_id": 42,
            "chunk_index": 2,
            "content": "La mitochondrie est le siège de la respiration cellulaire et de la production d'ATP par phosphorylation oxydative.",
            "heading_path": "Cytologie > Organites > Mitochondrie",
            "page_number": 15,
            "score": 0.892,
        },
        {
            "chunk_id": 43,
            "chunk_index": 3,
            "content": "Le cycle de Krebs se déroule dans la matrice mitochondriale.",
            "heading_path": "Cytologie > Métabolisme",
            "page_number": 16,
            "score": 0.741,
        },
    ]

    with patch("ankiforge.services.ai.rag_service.RAGService.search", return_value=mock_chunks):
        res = ConsultantToolRegistry.search_knowledge_context("mitochondrie ATP", max_chunks=2)

    assert "Contexte Documentaire RAG" in res
    assert "[Source: Biologie Cellulaire.pdf | p.15 | mitochondrie]" in res
    assert "La mitochondrie est le siège de la respiration" in res
    assert "doc:" in res
    assert "page:15" in res
    assert "section:mitochondrie" in res

    # Vérification du bloc JSON
    assert "### FRAGMENTS STRUCTURÉS (JSON) :" in res
    json_start = res.find("### FRAGMENTS STRUCTURÉS (JSON) :") + len("### FRAGMENTS STRUCTURÉS (JSON) :")
    json_text = res[json_start:].strip()
    if "\n\n💡" in json_text:
        json_text = json_text.split("\n\n💡")[0].strip()

    data = json.loads(json_text)
    assert len(data) == 2
    assert data[0]["doc_id"] == doc.id
    assert data[0]["page_number"] == 15
    assert data[0]["section_slug"] == "mitochondrie"
    assert "doc:" in " ".join(data[0]["suggested_tags"])
    assert "page:15" in " ".join(data[0]["suggested_tags"])


def test_search_knowledge_context_consultant_engine_dispatch():
    """Vérifie le routage dans la boucle ReAct de ConsultantEngine."""
    DocumentModel.create(title="Cours Pharmacologie.pdf", file_path="/fake/pharma.pdf", format="pdf")
    engine = ConsultantEngine()

    mock_chunks = [
        {
            "chunk_id": 10,
            "content": "L'aspirine inhibe les enzymes COX-1 et COX-2.",
            "heading_path": "AINS > Mécanisme",
            "page_number": 3,
            "score": 0.95,
        }
    ]

    with patch("ankiforge.services.ai.rag_service.RAGService.search", return_value=mock_chunks):
        obs, is_err = engine._execute_tool_call(
            "search_knowledge_context",
            {"query": "aspirine COX", "max_chunks": 1},
        )

    assert is_err is False
    assert "Contexte Documentaire RAG" in obs
    assert ("[Source: Cours Pharmacologie.pdf | p.3 | mécanisme]" in obs) or ("[Source: Cours Pharmacologie.pdf | p.3 | mecanisme]" in obs)


def test_search_knowledge_context_schema_and_fastmcp():
    """Vérifie la déclaration dans DEFAULT_CONSULTANT_TOOLS et sur le serveur FastMCP."""
    import asyncio

    tool_names = [t["function"]["name"] for t in DEFAULT_CONSULTANT_TOOLS]
    assert "search_knowledge_context" in tool_names

    async def _check():
        tools = await mcp.list_tools()
        return [t.name for t in tools]

    mcp_tools = asyncio.run(_check())
    assert "search_knowledge_context" in mcp_tools


def test_system_prompt_includes_rag_provenance_rules():
    """Vérifie que les consignes système incitent au sourcing et aux tags déterministes."""
    assert "search_knowledge_context" in _SYSTEM_PROMPT_TEMPLATE
    assert "provenance" in _SYSTEM_PROMPT_TEMPLATE.lower() or "source" in _SYSTEM_PROMPT_TEMPLATE.lower()
