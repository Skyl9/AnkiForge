---
name: audit-ia-pipeline
description: Audit de qualité et de robustesse du moteur IA d'AnkiForge (DAG, MCP, fournisseurs LLM). Use when the user asks to "audit IA", "audit pipeline", "audit orchestrator", "audit MCP", "prompt injection", "parsing JSON IA", "robustesse LLM", "tokens/coûts", "agnosticisme fournisseurs" or "simulateur de personas". Checks JSON decoding, Jinja2 prompt handling, provider abstraction, token cost tracking and MCP tool safety; produces a report under audits/.
---

# Audit Moteur IA & Pipeline AnkiForge

En tant qu'**Auditeur Moteur IA & Orchestration**, tu évalues la robustesse et la sécurité des pipelines IA (DAG), du protocole MCP et de la couche fournisseurs LLM d'AnkiForge, puis tu produis un rapport priorisé.

## 1. Périmètre & Sources de Vérité

- `src/ankiforge/services/ai/orchestrator.py` : `PipelineOrchestrator`, `PipelineRunState`, 5 types d'étapes (`LLM_PROMPT`, `RAG_RETRIEVAL`, `MAP_REDUCE`, `HUMAN_VALIDATION`, `PYTHON_TOOL`) et sauts conditionnels.
- `src/ankiforge/services/ai/mcp_server.py` + `MCPToolService` : outils exposés (`query_peewee`, `get_deck_stats`, `get_cards_by_deck_or_tag`, `update_card_model_css`, `execute_python_tool`).
- `src/ankiforge/services/ai/flexible_service.py` : abstraction fournisseurs (OpenAI/Anthropic/Gemini/Ollama), `providers/` (`model_catalog.py`), `pricing_service.py`, `TokenUsageModel`.
- `src/ankiforge/services/ai/prompt_interpolator.py` + `src/ankiforge/utils/jinja_sandbox.py` (`create_prompt_environment`).
- `GEMINI.md` règle 3 (DAG), règle 4 (MCP sécurisé), règle 5 (personas), règle 10 (agnosticisme LLM) ; `docs/Dossier_architecture/05_services_ia_et_analyse.md`, `06_moteur_orchestration_ia.md`.

## 2. Commandes d'Investigation

```bash
# Parsing JSON depuis l'IA SANS try/except json.JSONDecodeError (robustesse)
grep -rInE "json\.loads\(" src/ankiforge/services/ | rg -v "except" | head -30 || true
# Concaténation de prompts au lieu de Jinja2 sandboxé
grep -rInE "prompt\s*[+]=?|f\".*prompt" src/ankiforge/services/ai/ --include="*.py" | head -30 || true
# Clés API en dur dans la couche IA
grep -rInE "(api[_-]?key|token|sk-|AIza|sk-ant)" src/ankiforge/services/ai/ --include="*.py" || true
# Appels de sortie non mappés (exceptions non gérées)
grep -rInE "\.create\(|\.chat\.completions|\.generate_content|\.messages\.create" src/ankiforge/services/ai/ --include="*.py" | head -30 || true
```

## 3. Points de Contrôle

1. **Robustesse du parsing IA** : tout `json.loads` sur une réponse LLM doit être dans `try/except json.JSONDecodeError` avec repli/retry (et le JSON trouvé entre délimiteurs markdown ```json ``` si besoin). Signal toute réponse non isolée.
2. **Prompts & templates** : les prompts complexes passent par Jinja2 **sandboxé** (`create_prompt_environment` de `src/ankiforge/utils/jinja_sandbox.py`) et non par concaténation/f-strings avec entrée utilisateur ; vérifier les 4 sites migrés (prompt_interpolator, agent_test_dialog, prompt_preview_dialog) et qu'aucun nouveau site brute-force ne persiste.
3. **Injection de prompt & périmètre** : les contours user content / instructions système sont délimités (pas d'exécution du contenu utilisateur comme instruction) ; les vignettes RAG injectées ne doivent pas pouvoir forcer des actions ; `execute_python_tool` / `PYTHON_TOOL` passe bien par `tube_python_tool` sandboxé (cf. `audit-securite`).
4. **Agnosticisme fournisseurs** : `flexible_service.create_provider()` centralise la création ; Gemini utilise l'en-tête `x-goog-api-key` (jamais dans l'URL) ; Ollama borné à localhost (`_is_loopback_url`) ; aucun fournisseur conditionnel requiert un import non lazy.
5. **Gestion des erreurs fournisseurs** : timeouts configurés, retry politique, dégradation gracieuse (WARNING rule 19), pas d'exception nue remontée à l'UI.
6. **Suivi des coûts** : `TokenUsageModel` + `pricing_service` alimentés à chaque appel ; totaux par pipeline/persona affichés (réf. règle 7 A/B lab).
7. **MCP** : les outils exposés ne renvoient jamais de secret ni ne sortent du périmètre utilisateur ; `query_peewee` limité en lecture ; `update_card_model_css` validé ; `ThoughtStepWidget`/`ToolCallWidget` ne log pas les réponses brutes.
8. **Personas & contexte** : héritage `PersonaFolderModel` correct, snippets Jinja2 contextuels `generate` aux bons événements (réf. règle 5).

## 4. Rapport

`audits/audit-ia-pipeline.md` :

### 📊 Synthèse
Anomalies par sévérité et par catégorie (Parsing, Prompts/Jinja2, Injection, Fournisseurs, Erreurs/Timeout, Coûts, MCP, Personas).

### 🔍 Violations détaillées
Liens cliquables `[fichier.py:Lnn](file://<abs>/...#Lnn)` · règle · extrait · correction (ex. envelopper `json.loads` du try/except, mettre un retry policy dans `flexible_service`).

### 🗺️ Plan priorisé
Ordre : robustesse parsing + injection (critiques) → erreurs/retry → coûts → hygiène MCP.

## ⛔ Ne PAS utiliser ce skill si...

- La demande est d'**écrire ou modifier un pipeline DAG** (utiliser les outils d'édition directement, le skill est un auditeur).
- L'utilisateur veut tester une **connexion LLM en direct** (hors périmètre du skill — jamais d'appels réels en audit).
- La demande concerne uniquement la **sécurité des clés API stockées** → utiliser `audit-securite`.
- La demande concerne uniquement les **performances Qt/BDD** → utiliser `audit-performance`.
- Le projet n'utilise pas `PipelineOrchestrator` ni `MCPToolService` (hors périmètre AnkiForge).

## 5. Clôture

Résume les risques IA majeurs dans le chat, indique le chemin du rapport, propose les correctifs (try/except JSON, migration de prompt vers Jinja2, retry/timeouts).
