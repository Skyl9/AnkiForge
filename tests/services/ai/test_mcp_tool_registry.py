"""Tests unitaires pour MCPToolRegistry (ADR 0034 §4).

Vérifie l'extraction du registre des 58 outils MCP, son autonomie sans session de chat,
la présence de l'alias de rétrocompatibilité ConsultantToolRegistry, et le bon fonctionnement
des outils clés.
"""

from __future__ import annotations

import json

import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.ai.linter import WozniakLinterEngine
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


def test_audit_deck_wozniak_aligned_on_contract(mock_db, monkeypatch):
    """L'outil MCP lit score_global, categories[*].title et count — jamais total_notes/notes_flagged/name."""
    fake_report = {
        "score_global": 78,
        "enable_cloze_audit": True,
        "categories": {
            "cat-atomicite": {"title": "Atomicité & Restructuration", "count": 3, "items": []},
            "cat-katex": {"title": "Formules & Clarté", "count": 0, "items": []},
        },
    }
    monkeypatch.setattr(WozniakLinterEngine, "audit_deck", staticmethod(lambda *a, **k: fake_report))

    deck = DeckModel.create(name="Deck Contrat Wozniak")
    res = MCPToolRegistry.audit_deck_wozniak(deck.name)

    assert "Rapport d'Audit Qualité Wozniak" in res
    assert "Score de conformité global : 78/100" in res
    assert "Atomicité & Restructuration : 3 anomalies détectées" in res
    assert "total_notes" not in res
    assert "notes_flagged" not in res
    assert "'name'" not in res


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


# =====================================================================
# TESTS RESOURCE MCP : INTROSPECTION DE SCHÉMA (ankiforge://schema/{table})
# =====================================================================


def test_mcp_tool_registry_get_table_schema_data_notes_table(mock_db):
    """Vérifie l'introspection de schéma pour la table 'notemodel'."""
    result = MCPToolRegistry._get_table_schema_data("notemodel")

    assert result["table_name"] == "notemodel"
    assert isinstance(result["columns"], list)
    assert len(result["columns"]) >= 8

    # Vérifier la structure des colonnes (selon NoteModel réel)
    col_names = {c["name"] for c in result["columns"]}
    assert "id" in col_names
    assert "guid" in col_names
    assert "note_type_id" in col_names  # FK vers NoteTypeModel (colonne SQLite réelle)
    assert "tags" in col_names
    assert "status" in col_names
    assert "anki_id" in col_names
    assert "anki_content_hash" in col_names
    assert "sort_field" in col_names

    # Vérifier la clé primaire
    pk_cols = [c for c in result["columns"] if c["primary_key"]]
    assert len(pk_cols) == 1
    assert pk_cols[0]["name"] == "id"

    # Vérifier les index
    assert isinstance(result["indexes"], list)

    # Vérifier les foreign keys (note_type_id vers notetypemodel)
    assert isinstance(result["foreign_keys"], list)
    fk_from_cols = {fk["from"] for fk in result["foreign_keys"]}
    assert "note_type_id" in fk_from_cols

    # Vérifier les contraintes
    assert isinstance(result["constraints"], list)
    constraint_types = {c["type"] for c in result["constraints"]}
    assert "PRIMARY KEY" in constraint_types


def test_mcp_tool_registry_get_table_schema_data_cards_table(mock_db):
    """Vérifie l'introspection de schéma pour la table 'cardmodel'."""
    result = MCPToolRegistry._get_table_schema_data("cardmodel")

    assert result["table_name"] == "cardmodel"
    col_names = {c["name"] for c in result["columns"]}
    assert "id" in col_names
    assert "note_id" in col_names
    assert "deck_id" in col_names
    assert "ivl" in col_names
    assert "reps" in col_names
    assert "lapses" in col_names
    assert "flags" in col_names


def test_mcp_tool_registry_get_table_schema_data_decks_table(mock_db):
    """Vérifie l'introspection de schéma pour la table 'deckmodel'."""
    result = MCPToolRegistry._get_table_schema_data("deckmodel")

    assert result["table_name"] == "deckmodel"
    col_names = {c["name"] for c in result["columns"]}
    assert "id" in col_names
    assert "name" in col_names
    assert "description" in col_names


def test_mcp_tool_registry_get_table_schema_data_documents_table(mock_db):
    """Vérifie l'introspection de schéma pour la table 'documentmodel'."""
    result = MCPToolRegistry._get_table_schema_data("documentmodel")

    assert result["table_name"] == "documentmodel"
    col_names = {c["name"] for c in result["columns"]}
    assert "id" in col_names
    assert "title" in col_names
    assert "folder_id" in col_names


def test_mcp_tool_registry_get_table_schema_rejects_sqlite_master(mock_db):
    """Vérifie que les tables système sont rejetées."""
    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("sqlite_master")

    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("sqlite_schema")

    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("sqlite_temp_master")


def test_mcp_tool_registry_get_table_schema_rejects_sensitive_tables(mock_db):
    """Vérifie que les tables sensibles sont rejetées."""
    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("llm_configs")

    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("settings")

    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("settingmodel")


def test_mcp_tool_registry_get_table_schema_rejects_unknown_table(mock_db):
    """Vérifie que les tables inconnues ou non listées sont rejetées."""
    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("nonexistent_table")

    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("random_table")


def test_mcp_tool_registry_get_table_schema_case_insensitive(mock_db):
    """Vérifie que le nom de table est traité de manière insensible à la casse."""
    result_lower = MCPToolRegistry._get_table_schema_data("notemodel")
    result_upper = MCPToolRegistry._get_table_schema_data("NOTEMODEL")
    result_mixed = MCPToolRegistry._get_table_schema_data("NoteModel")

    assert result_lower["table_name"] == "notemodel"
    assert result_upper["table_name"] == "notemodel"
    assert result_mixed["table_name"] == "notemodel"


def test_mcp_tool_registry_get_table_schema_json_structure(mock_db):
    """Vérifie la structure JSON exacte retournée."""
    result = MCPToolRegistry._get_table_schema_data("notemodel")

    # Vérifier les clés principales
    assert set(result.keys()) == {"table_name", "columns", "indexes", "foreign_keys", "constraints"}

    # Vérifier structure colonne
    for col in result["columns"]:
        assert set(col.keys()) == {"name", "type", "not_null", "default", "primary_key"}

    # Vérifier structure index
    for idx in result["indexes"]:
        assert set(idx.keys()) == {"name", "columns", "unique"}

    # Vérifier structure foreign key
    for fk in result["foreign_keys"]:
        assert set(fk.keys()) == {"from", "to_table", "to_column", "on_update", "on_delete"}

    # Vérifier structure contrainte
    for constr in result["constraints"]:
        assert set(constr.keys()) == {"name", "type", "columns"}
