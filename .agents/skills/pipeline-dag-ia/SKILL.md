---
name: pipeline-dag-ia
description: >-
  Expert en orchestration de pipelines DAG IA pour AnkiForge. Conçoit, exécute et débogue le moteur PipelineOrchestrator (6 types d'étapes, branching, reprise sur échec, budgets de tokens), la surcharge locale de persona (persona_override.py) et l'intégration du serveur MCP in-process.
  Use when the user asks to "créer un pipeline IA", "modifier une étape de pipeline", "orchestrateur DAG", "PipelineOrchestrator", "surcharge locale de persona", "prompt override", "outil MCP", "étape MAP_REDUCE", or works with AI DAG workflows.
  When NOT to use: Do not use for security or prompt-injection audit only (use audit-ia-pipeline) or raw file chunking for RAG (use rag-smart-coverage).
---

# ⚡ Moteur d'Orchestration DAG IA & Personas — AnkiForge

En tant qu'**Architecte des Pipelines d'IA**, tu conçois, fais évoluer et débogues le moteur d'orchestration DAG d'AnkiForge (`PipelineOrchestrator`), les étapes de transformation IA et l'intégration des outils MCP.

> **Code source clé** :
> - `src/ankiforge/services/ai/orchestrator.py` : Moteur DAG et boucle d'exécution de `PipelineRunState`.
> - `src/ankiforge/services/ai/persona_override.py` : Coutures uniques de surcharge locale de persona.
> - `src/ankiforge/services/ai/mcp_server.py` : Serveur MCP in-process et outils sécurisés.
> - `docs/Dossier_architecture/06_moteur_orchestration_ia.md` : Spécification complète du moteur DAG.

## 1. Principes & Types d'Étapes

Le moteur DAG supporte 6 types d'étapes d'orchestration :
1. **`LLM_PROMPT`** : Invocation directe d'un modèle d'IA avec template Jinja2 et interpolation de variables.
2. **`RAG_RETRIEVAL`** : Recherche sémantique vectorielle via `VectorManager` et injection de contexte.
3. **`MAP_REDUCE`** : Découpage en sous-tâches parallèles (map) et consolidation synthétique (reduce).
4. **`HUMAN_VALIDATION`** : Point d'arrêt suspensif pour validation humaine intermédiaire.
5. **`PYTHON_TOOL`** : Exécution d'un script ou calcul Python sécurisé.
6. **`AUDIO_TTS`** : Synthèse vocale de champs pour génération de fichiers audio Anki.

## 2. Garde-Fous & Résilience du Moteur

- **Garde-fous anti-boucles et budgets** :
  - `max_step_executions` : plafond d'exécutions par étape pour interdire tout cycle infini.
  - `max_tokens_budget` / `max_total_tokens` : interruption nette si le quota de tokens est dépassé.
- **Persistance & Reprise interactive** :
  - Chaque exécution est tracée en base de données SQLite via `PipelineRunModel`.
  - La reprise interactive d'un lot (`resume_run`) réutilise l'état sans recalculer les étapes déjà terminées (`COMPLETED`).
- **Branchements conditionnels** : gestion stricte de `on_success_step` et `on_failure_step`.

## 3. Surcharge Locale de Persona (`persona_override.py`)

La surcharge locale est **un réglage de l'étape du pipeline**, jamais une mutation du modèle de persona (`PersonaModel`) :
- `resolve_prompt_source()` / `resolve_system_prompt()` : ordre de résolution `surcharge figée → agent de l'étape → défaut du fournisseur`.
- `apply_persona_override()` : écrit le prompt surchargé, horodate (`prompt_override_frozen_at`) et calcule l'empreinte SHA-256 (`prompt_override_base_digest`).
- Consommé de manière unifiée par `orchestrator.py` (`LLM_PROMPT` et `MAP_REDUCE`), l'inspecteur d'étape et le simulateur d'aperçu.

## 4. Règle de Test : Mocks Obligatoires

- **Aucun appel réseau ou API LLM réel en test** (règle 21 `GEMINI.md`).
- Tous les fournisseurs (OpenAI, Gemini, Anthropic, Ollama) sont mockés de manière déterministe dans la suite pytest (`mock_llm_response`).

## 5. Extension FastMCP & Synchronisation du Catalogue IHM

Lors de l'ajout d'un nouvel outil décoré `@mcp.tool()` sur le serveur in-process (`src/ankiforge/services/ai/mcp_server.py`) :
1. **Classification IHM obligatoire** : enregistrer l'outil dans les deux dictionnaires de `src/ankiforge/ui/views/consultant_view/widgets/mcp_tool_catalog_widget.py` :
   - `TOOL_DOMAIN_MAP` : affectation au domaine métier (`DOMAIN_CARDS`, `DOMAIN_DOCS`, `DOMAIN_KNOWLEDGE`, `DOMAIN_PIPELINES`, `DOMAIN_MCP`, etc.).
   - `TOOL_SAFEGUARDS_MAP` : affectation du niveau de garde-fou (`SAFEGUARD_TWO_PHASE_COMMIT` pour toute mutation/staging, ou `SAFEGUARD_DIRECT_EXECUTION` pour la consultation en lecture seule).
2. **Parité de dispatch `ConsultantEngine` obligatoire (`T-25`)** :
   - Déclarer l'outil dans `DEFAULT_CONSULTANT_TOOLS` de `src/ankiforge/services/ai/consultant_engine.py`.
   - Ajouter impérativement son cas de traitement dans `ConsultantEngine._execute_tool_call()` avec routage vers `mcp_tool_registry.py` pour que l'agent conversationnel interne puisse l'invoquer sans déclencher `Tool execution failed: Tool <nom> not found`.
3. **Synchronisation des assertions de tests d'introspection** : mettre à jour le décompte d'outils attendu dans `tests/ui/test_mcp_tool_catalog_widget.py::test_introspection_fastmcp_real_tools` (`assert len(tools) == N`) et dans `test_mcp_dashboard_widget_integration_catalog_tab`.
4. **Contrat d'invocation de test FastMCP (`mcp.call_tool`) (`T-24`)** : `await mcp.call_tool(tool_name, arguments)` renvoie une instance typée `CallToolResult` et non une liste. Pour extraire la réponse textuelle, utiliser `res.content[0].text` (ou un helper `_extract_text`) sans jamais tenter d'indexer directement `res[0]` ou d'appeler `len(res)`.
5. **Couverture d'overlay virtuel (`StagedOverlay`)** : pour tout patch 2PC modifiant la structure des données (création/renommage de paquets, création/suppression de notes), enregistrer l'effet dans `overlay.register_*` au sein de `StagedPatchRegistry.create_patch()` afin que les lectures virtuelles consécutives dans un même bundle reflètent l'état projeté.
6. **Variables locales qualifiées sous Mypy Strict (`T-28`)** : dans `ConsultantEngine._execute_tool_call()` et les répartiteurs d'étapes, employer impérativement des variables locales qualifiées (ex: `plate_target_id`, `card_id_int`, `patch_id_str`) au lieu d'abréviations courtes partagées (`p_id`, `res`) pour prévenir tout conflit d'assignation de type sous Mypy.

## 6. Mutations Destructives & Paquets Hiérarchiques 2PC (`T-27`)

Lors de la conception d'opérations de suppression ou restructuration de paquets sous 2PC (`deck_delete`, etc.) :
- **Interdiction de déplacement vers un descendant** : vérifier rigoureusement que le paquet cible `move_to` n'est pas un sous-paquet du paquet à supprimer (`target.name.startswith(f"{source.name}::")`), sous peine de détruire immédiatement les cartes déplacées.
- **Réassignation récursive de l'arborescence** : identifier tous les sous-paquets descendants (`DeckRepository.get_descendant_decks(deck.id)`) et réassigner leurs cartes en cascade vers le paquet de repli avant d'exécuter la suppression de la branche.
- **Atomicité stricte `with db.atomic():`** : encapsuler le déplacement des cartes, la suppression du paquet et l'enregistrement du statut de patch dans une transaction SQLite unique pour garantir un état intègre même en cas d'erreur intermédiaire.

## When NOT to use this skill

- L'objectif est uniquement d'auditer la sécurité des prompts et la gestion des coûts sans coder → utiliser `audit-ia-pipeline`.
- La tâche consiste à manipuler l'extraction ou la segmentation d'un document brut → utiliser `rag-smart-coverage`.
- La demande concerne la création de gabarits HTML/CSS pour les types de cartes Anki → utiliser `modeles-cartes-jinja`.
