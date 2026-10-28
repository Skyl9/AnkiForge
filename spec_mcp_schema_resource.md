# Spécification Technique — MCP Resource : Introspection de Schéma BDD (`ankiforge://schema/{table}`)

## Problématique (Problem Statement)

Le serveur MCP d'AnkiForge expose actuellement un outil `query_peewee` permettant l'exécution de requêtes SQL SELECT en lecture seule, protégé par un authorizer SQLite bloquant l'accès aux tables système (`sqlite_master`, `sqlite_schema`, etc.). Les agents MCP externes (Claude Code, Cursor, Antigravity CLI) ne peuvent donc pas découvrir la structure des tables métier (colonnes, types, index, clés étrangères, contraintes) sans tenter des requêtes sur `sqlite_master`, ce qui est refusé par sécurité.

L'enquête documentaire et l'analyse de l'écosystème MCP (serveurs de référence, spécification officielle, avis NSA, audits GitHub) convergent vers une **séparation nette** :
- **Resources MCP** = contexte passif, lecture seule, contrôlé par l'hôte (schéma, documentation, fichiers)
- **Tools MCP** = actions, effets de bord, contrôlé par le modèle (requêtes, mutations)

Exposer l'introspection de schéma comme un **Tool** (`get_table_schema`, `describe_table`) contredit ce principe, augmente la surface d'attaque (injection SQL potentielle, énumération de tables) et complexifie l'auditabilité.

## Solution proposée

Implémenter l'introspection de schéma comme une **Resource MCP** native, exposée via le protocole standard `resources/list` et `resources/read`, avec URI template `ankiforge://schema/{table_name}`.

### Caractéristiques clés
- **URI template** : `ankiforge://schema/{table_name}` (ex: `ankiforge://schema/notes`, `ankiforge://schema/cards`)
- **Format de sortie** : JSON structuré (colonnes, index, foreign keys, contraintes)
- **Sécurité** : allow-list stricte des tables métier autorisées, zéro interpolation SQL, connexion read-only
- **Découverte** : listée dans `resources/list` avec métadonnées (description, MIME type `application/json`)
- **Caching** : TTL court côté serveur (schéma stable), invalidation sur migration

## User Stories (Extensives)

1. **En tant qu'** agent MCP externe (Claude Code, Cursor, agy)  
   **Je veux** lire la resource `ankiforge://schema/notes`  
   **Afin de** connaître les colonnes, types, index et FK de la table `notes` pour écrire une requête `query_peewee` correcte sans deviner.

2. **En tant qu'** développeur d'agent MCP  
   **Je veux** découvrir les resources disponibles via `resources/list`  
   **Afin de** présenter à l'utilisateur la liste des tables introspectables sans appeler d'outil.

3. **En tant qu'** utilisateur AnkiForge (via UI)  
   **Je veux** que l'hôte (AnkiForge) décide quand injecter le schéma dans le contexte de l'agent  
   **Afin de** garder le contrôle sur la fuite d'informations de structure (principe application-driven).

4. **En tant qu'** auditeur de sécurité  
   **Je veux** vérifier qu'aucun outil MCP n'expose `sqlite_master` ni ne permet d'énumérer les tables système  
   **Afin de** valider le principe de moindre privilège.

## Décisions d'Implémentation

### Modules et interfaces touchés

| Fichier | Rôle | Changement |
|---------|------|------------|
| `src/ankiforge/services/ai/mcp_tool_registry.py` | Logique métier | Nouvelle méthode statique `_get_table_schema_data(table_name: str) -> dict` réutilisable |
| `src/ankiforge/services/ai/mcp_server.py` | Serveur MCP | Enregistrement de la resource via `server.resource()` avec URI template |
| `src/ankiforge/services/ai/tools_catalog.py` | Catalogue outils | **Aucun** — resource, pas tool (cohérence MCP) |
| `src/ankiforge/database/models.py` | Modèles Peewee | Référence pour allow-list tables métier (`DeckModel`, `NoteModel`, `CardModel`, `DocumentModel`, `DocumentChunkModel`, `FolderModel`, `PersonaModel`, `PipelineModel`, `LLMConfigModel`, `NoteTypeModel`, `NoteVersionModel`, `MediaModel`, `AuditRecordModel`) |

### Schéma de base de données / migrations

**Aucune migration** — lecture seule sur schéma existant.

### Contrats d'API et flux d'état

#### Resource MCP : `ankiforge://schema/{table_name}`

**Requête** : `resources/read` avec URI `ankiforge://schema/notes`

**Réponse** (`application/json`) :
```json
{
  "table_name": "notes",
  "columns": [
    {"name": "id", "type": "INTEGER", "not_null": true, "default": null, "primary_key": true},
    {"name": "guid", "type": "TEXT", "not_null": true, "default": null, "primary_key": false},
    {"name": "note_type_id", "type": "INTEGER", "not_null": true, "default": null, "primary_key": false},
    {"name": "deck_id", "type": "INTEGER", "not_null": true, "default": null, "primary_key": false},
    {"name": "tags", "type": "TEXT", "not_null": false, "default": "''", "primary_key": false},
    {"name": "created_at", "type": "INTEGER", "not_null": true, "default": null, "primary_key": false},
    {"name": "updated_at", "type": "INTEGER", "not_null": true, "default": null, "primary_key": false}
  ],
  "indexes": [
    {"name": "idx_notes_deck_id", "columns": ["deck_id"], "unique": false},
    {"name": "idx_notes_note_type_id", "columns": ["note_type_id"], "unique": false},
    {"name": "idx_notes_guid", "columns": ["guid"], "unique": true}
  ],
  "foreign_keys": [
    {"from": "note_type_id", "to_table": "note_types", "to_column": "id", "on_delete": "CASCADE", "on_update": "CASCADE"},
    {"from": "deck_id", "to_table": "decks", "to_column": "id", "on_delete": "CASCADE", "on_update": "CASCADE"}
  ],
  "constraints": [
    {"name": "notes_pkey", "type": "PRIMARY KEY", "columns": ["id"]},
    {"name": "notes_guid_unique", "type": "UNIQUE", "columns": ["guid"]}
  ]
}
```

**Erreurs** :
- Table inconnue ou non autorisée → `404` Resource not found (MCP error response)
- Table système (`sqlite_master`, etc.) → `403` Forbidden (MCP error response)

#### Allow-list tables métier (dure)

```python
_ALLOWED_SCHEMA_TABLES = frozenset(
    {
        "decks",
        "notes",
        "cards",
        "note_types",
        "note_versions",
        "documents",
        "document_pages",
        "document_chunks",
        "folders",
        "personas",
        "pipelines",
        "pipeline_steps",
        "pipeline_runs",
        "llm_configs",
        "settings",
        "media",
        "audit_records",
    }
)
```

### Composants d'interface utilisateur

**Aucun** — resource MCP, pas d'UI directe. L'hôte (AnkiForge UI) peut lister les resources via `resources/list` et choisir de les injecter dans le contexte du Consultant IA.

## Décisions de Test

### Stratégie de test aux coutures clés

| Niveau | Cible | Outil | Scénarios |
|--------|-------|-------|-----------|
| **Unitaire** | `MCPToolRegistry._get_table_schema_data()` | `pytest` (unit) | Tables valides, table inconnue, table système bloquée, format JSON exact |
| **Intégration** | `mcp_server.py` resource registration | `pytest` (integration) | `resources/list` contient URI templates, `resources/read` retourne JSON valide |
| **Contractuel** | Protocole MCP | `pytest` + client MCP test | Conformité spec 2025-06-18/2026-07-28 (URI template, pagination, MIME) |
| **Sécurité** | Authorizer + allow-list | `pytest` (security) | Refus `sqlite_master`, `sqlite_schema`, injection via table_name |

### Fixtures et précédents existants

- `tests/conftest.py` : `db` fixture (SQLite mémoire partagée), `mcp_server` fixture
- `tests/services/ai/test_mcp_tool_registry.py` : tests existants `query_peewee`, `get_deck_stats`
- `tests/services/ai/test_mcp_server.py` : tests outils MCP enregistrés
- Pattern `resources/list` + `resources/read` à ajouter dans `test_mcp_server.py`

### Exemple de test unitaire

```python
def test_get_table_schema_data_notes_table():
    from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry

    result = MCPToolRegistry._get_table_schema_data("notes")
    assert result["table_name"] == "notes"
    assert len(result["columns"]) >= 7
    assert any(c["name"] == "id" and c["primary_key"] for c in result["columns"])
    assert any(fk["from"] == "deck_id" for fk in result["foreign_keys"])


def test_get_table_schema_data_rejects_sqlite_master():
    from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry

    with pytest.raises(PermissionError):
        MCPToolRegistry._get_table_schema_data("sqlite_master")
```

## Hors Périmètre (Out of Scope)

1. **Outil `get_table_schema` / `describe_table`** — explicitement exclu au profit de la Resource MCP
2. **Modification de schéma** (CREATE/ALTER/DROP) — write opt-in non requis pour cette spécification
3. **Introspection cross-database** — AnkiForge est single-tenant, single-profile, single-DB
4. **Vectorisation du schéma pour RAG** — hors sujet (resource = contexte passif, pas indexation)
5. **UI de visualisation de schéma dans AnkiForge** — l'hôte décide de l'affichage ; pas de composant dédié dans cette spec
6. **Migration vers `resources/templates` (RFC)** — suivre l'évolution du spec MCP ultérieurement