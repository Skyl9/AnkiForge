"""Tests d'intégration et de non-régression pour les outils MCP de délimitation documentaire, sauvegarde et réindexation RAG.

Conforme à l'ADR 0010 (exclusion non destructive), l'ADR 0042 (périmètre mutations MCP) et aux règles d'ingénierie AnkiForge.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import pytest

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    FolderModel,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry
from ankiforge.utils.event_bus import MCPDataMutatedEvent, event_bus
from ankiforge.utils.region_address import (
    RegionScope,
    parse_region_addresses,
    validate_canonical_region_address,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_document(mock_db: Any) -> DocumentModel:
    """Crée un document de test avec des sections et des chunks initiaux."""
    folder = FolderModel.create(name="Cours Médicaux")
    content = (
        "# Chapitre 1 : Cardiologie Générale\n\n"
        "Introduction à la physiologie cardiovasculaire.\n\n"
        "## Section 1.1 : Le Myocarde\n\n"
        "Le tissu musculaire du cœur assure la contraction myocardique.\n\n"
        "## Section 1.2 : Les Valvules\n\n"
        "Les valvules cardiaques empêchent le reflux sanguin.\n\n"
        "# Annexes et Errata\n\n"
        "Ce bloc contient des errata hors-sujet qui doivent être exclus du périmètre de couverture.\n"
    )
    doc = DocumentModel.create(
        title="Manuel de Cardiologie",
        content=content,
        file_type="md",
        folder=folder,
    )
    # Chunks initiaux simulant une ingestion initiale
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        content="Introduction à la physiologie cardiovasculaire.",
        heading_path="Chapitre 1 : Cardiologie Générale",
        content_hash="hash0",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        content="Le tissu musculaire du cœur assure la contraction myocardique.",
        heading_path="Chapitre 1 : Cardiologie Générale > Section 1.1 : Le Myocarde",
        content_hash="hash1",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        content="Les valvules cardiaques empêchent le reflux sanguin.",
        heading_path="Chapitre 1 : Cardiologie Générale > Section 1.2 : Les Valvules",
        content_hash="hash2",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=3,
        content="Ce bloc contient des errata hors-sujet qui doivent être exclus du périmètre de couverture.",
        heading_path="Annexes et Errata",
        content_hash="hash3",
    )
    return doc


def test_validate_canonical_region_address() -> None:
    """Vérifie la validation stricte des adresses de région canoniques (node:, heading:, page:)."""
    # 1. Formats valides
    addr1, err1 = validate_canonical_region_address("heading:Chapitre 1")
    assert err1 is None
    assert addr1 is not None
    assert addr1.scope == RegionScope.HEADING
    assert addr1.value == "Chapitre 1"

    addr2, err2 = validate_canonical_region_address("node:Introduction")
    assert err2 is None
    assert addr2 is not None
    assert addr2.scope == RegionScope.NODE
    assert addr2.value == "Introduction"

    addr3, err3 = validate_canonical_region_address("page:5")
    assert err3 is None
    assert addr3 is not None
    assert addr3.scope == RegionScope.PAGE
    assert addr3.value == "5"

    # 2. Formats invalides (rejets stricts)
    # Sans préfixe canonique
    addr_err, err = validate_canonical_region_address("Chapitre 1 nu")
    assert addr_err is None
    assert err is not None
    assert "préfixe canonique" in err

    # Préfixe inconnu
    addr_err, err = validate_canonical_region_address("section:Cardiologie")
    assert addr_err is None
    assert err is not None

    # Page non numérique ou négative/zéro
    addr_err, err = validate_canonical_region_address("page:zero")
    assert addr_err is None
    assert err is not None

    addr_err, err = validate_canonical_region_address("page:0")
    assert addr_err is None
    assert err is not None

    # Valeur vide
    addr_err, err = validate_canonical_region_address("heading:")
    assert addr_err is None
    assert err is not None

    addr_err, err = validate_canonical_region_address("")
    assert addr_err is None
    assert err is not None


def test_exclude_document_region_success_and_non_destructive(sample_document: DocumentModel) -> None:
    """Vérifie l'exclusion non destructive d'une région et la préservation intégrale des fragments en base."""
    mutations_captured: list[MCPDataMutatedEvent] = []

    def _on_event(evt: MCPDataMutatedEvent) -> None:
        mutations_captured.append(evt)

    event_bus.subscribe(MCPDataMutatedEvent, _on_event)
    try:
        # Nombre de chunks initiaux
        initial_chunk_count = DocumentChunkModel.select().where(DocumentChunkModel.document == sample_document).count()
        assert initial_chunk_count == 4

        # Exclusion de la section "Annexes et Errata"
        res_json = MCPToolRegistry.exclude_document_region(
            document_id=sample_document.id,
            region_address="heading:Annexes et Errata",
            reason="Sections parasites non examinables",
        )
        data = json.loads(res_json)
        assert data["status"] == "success"
        assert data["document_id"] == sample_document.id
        assert data["region_address"] == "heading:Annexes et Errata"

        # Vérification en base sur le DocumentModel
        refreshed_doc = DocumentModel.get_by_id(sample_document.id)
        excluded = parse_region_addresses(refreshed_doc.excluded_headings)
        assert any(addr.render() == "heading:Annexes et Errata" for addr in excluded)

        # Règle d'or ADR 0010 : NON-DESTRUCTIVITÉ DES FRAGMENTS
        # Les 4 chunks sont toujours présents en base physique SQLite
        current_chunk_count = DocumentChunkModel.select().where(DocumentChunkModel.document == sample_document).count()
        assert current_chunk_count == initial_chunk_count

        # Vérification de l'événement émis
        assert len(mutations_captured) == 1
        evt = mutations_captured[0]
        assert evt.domain == "docs"
        assert evt.mutation_type == "exclude_document_region"
        assert evt.target_id == sample_document.id
    finally:
        event_bus.unsubscribe(MCPDataMutatedEvent, _on_event)


def test_exclude_document_region_validation_errors(sample_document: DocumentModel) -> None:
    """Vérifie le rejet des adresses invalides et des identifiants inconnus."""
    # Document inexistant
    res_err1 = MCPToolRegistry.exclude_document_region(document_id=99999, region_address="heading:Test")
    data1 = json.loads(res_err1)
    assert data1["status"] == "error"
    assert "99999" in data1["message"]

    # Adresse non canonique
    res_err2 = MCPToolRegistry.exclude_document_region(document_id=sample_document.id, region_address="Titre sans prefixe")
    data2 = json.loads(res_err2)
    assert data2["status"] == "error"
    assert "canonique" in data2["message"]


def test_neutralize_document_region_lifecycle(sample_document: DocumentModel) -> None:
    """Vérifie la neutralisation d'une région (retrait du dénominateur de couverture) et son annulation."""
    mutations_captured: list[MCPDataMutatedEvent] = []

    def _on_event(evt: MCPDataMutatedEvent) -> None:
        mutations_captured.append(evt)

    event_bus.subscribe(MCPDataMutatedEvent, _on_event)
    try:
        # 1. Neutraliser
        res_json = MCPToolRegistry.neutralize_document_region(
            document_id=sample_document.id,
            region_address="node:Chapitre 1 : Cardiologie Générale",
            neutralized=True,
        )
        data = json.loads(res_json)
        assert data["status"] == "success"
        assert data["neutralized"] is True

        refreshed_doc = DocumentModel.get_by_id(sample_document.id)
        neutralized = parse_region_addresses(refreshed_doc.neutralized_regions)
        assert any(addr.render() == "node:Chapitre 1 : Cardiologie Générale" for addr in neutralized)

        # 2. Dé-neutraliser
        res_un = MCPToolRegistry.neutralize_document_region(
            document_id=sample_document.id,
            region_address="node:Chapitre 1 : Cardiologie Générale",
            neutralized=False,
        )
        data_un = json.loads(res_un)
        assert data_un["status"] == "success"
        assert data_un["neutralized"] is False

        refreshed_doc2 = DocumentModel.get_by_id(sample_document.id)
        neutralized2 = parse_region_addresses(refreshed_doc2.neutralized_regions)
        assert not any(addr.render() == "node:Chapitre 1 : Cardiologie Générale" for addr in neutralized2)

        # Événements reçus
        assert len(mutations_captured) == 2
        assert all(e.domain == "docs" for e in mutations_captured)
    finally:
        event_bus.unsubscribe(MCPDataMutatedEvent, _on_event)


def test_update_document_content_and_chunk_sync(sample_document: DocumentModel) -> None:
    """Vérifie la mise à jour pérenne du contenu Markdown et la synchronisation différentielle des chunks."""
    mutations_captured: list[MCPDataMutatedEvent] = []

    def _on_event(evt: MCPDataMutatedEvent) -> None:
        mutations_captured.append(evt)

    event_bus.subscribe(MCPDataMutatedEvent, _on_event)
    try:
        new_content = (
            "# Chapitre 1 : Cardiologie Générale\n\n"
            "Introduction corrigée à la physiologie cardiovasculaire humaine.\n\n"
            "## Section 1.1 : Le Myocarde\n\n"
            "Le tissu musculaire du cœur assure la contraction myocardique automatique.\n\n"
            "## Section 1.3 : La Vascularisation Coronaire\n\n"
            "Les artères coronaires vascularisent le myocarde.\n"
        )
        res_json = MCPToolRegistry.update_document_content(
            document_id=sample_document.id,
            content=new_content,
            reason="Ajout de la section 1.3 et correction orthographique",
        )
        data = json.loads(res_json)
        assert data["status"] == "success"
        assert data["document_id"] == sample_document.id
        assert data["chunks_created"] >= 1

        refreshed_doc = DocumentModel.get_by_id(sample_document.id)
        assert "La Vascularisation Coronaire" in refreshed_doc.content

        # Chunks mis à jour
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == sample_document))
        headings = [c.heading_path for c in chunks]
        assert any(h and "Section 1.3" in h for h in headings)

        # Événement émis
        assert len(mutations_captured) == 1
        assert mutations_captured[0].domain == "docs"
        assert mutations_captured[0].mutation_type == "update_document_content"
    finally:
        event_bus.unsubscribe(MCPDataMutatedEvent, _on_event)


def test_update_document_content_validation(sample_document: DocumentModel) -> None:
    """Vérifie la validation des paramètres de update_document_content."""
    # Document inexistant
    res1 = MCPToolRegistry.update_document_content(document_id=99999, content="texte")
    assert json.loads(res1)["status"] == "error"

    # Contenu vide
    res2 = MCPToolRegistry.update_document_content(document_id=sample_document.id, content="   ")
    assert json.loads(res2)["status"] == "error"


def test_reindex_document_success_with_params(sample_document: DocumentModel) -> None:
    """Vérifie le recalcul des chunks et l'appel à la vectorisation avec chunk_size et overlap."""
    mutations_captured: list[MCPDataMutatedEvent] = []

    def _on_event(evt: MCPDataMutatedEvent) -> None:
        mutations_captured.append(evt)

    event_bus.subscribe(MCPDataMutatedEvent, _on_event)
    try:
        with patch("ankiforge.services.rag.vector_manager.VectorManager.index_document", return_value=True):
            res_json = MCPToolRegistry.reindex_document(
                document_id=sample_document.id,
                chunk_size=150,
                overlap=25,
            )
            data = json.loads(res_json)
            assert data["status"] == "success"
            assert data["document_id"] == sample_document.id
            assert data["chunks_count"] > 0
            assert data["chunk_size"] == 150
            assert data["overlap"] == 25

            # Événement émis
            assert len(mutations_captured) == 1
            assert mutations_captured[0].domain == "docs"
            assert mutations_captured[0].mutation_type == "reindex_document"
    finally:
        event_bus.unsubscribe(MCPDataMutatedEvent, _on_event)


def _extract_text(tool_result: Any) -> str:
    if hasattr(tool_result, "content") and tool_result.content:
        return str(tool_result.content[0].text)
    return str(tool_result)


def test_fastmcp_direct_tool_invocation(sample_document: DocumentModel) -> None:
    """Vérifie que les 4 outils sont déclarés et invocables directement via le protocole FastMCP."""

    async def _run() -> None:
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert "exclude_document_region" in tool_names
        assert "neutralize_document_region" in tool_names
        assert "update_document_content" in tool_names
        assert "reindex_document" in tool_names

        # Appel direct exclude_document_region
        res_exclude = await mcp.call_tool(
            "exclude_document_region",
            {"document_id": sample_document.id, "region_address": "page:1", "reason": "Page de garde"},
        )
        exclude_data = json.loads(_extract_text(res_exclude))
        assert exclude_data["status"] == "success"

        # Appel direct neutralize_document_region
        res_neutral = await mcp.call_tool(
            "neutralize_document_region",
            {"document_id": sample_document.id, "region_address": "heading:Annexes et Errata", "neutralized": True},
        )
        neutral_data = json.loads(_extract_text(res_neutral))
        assert neutral_data["status"] == "success"

    asyncio.run(_run())
