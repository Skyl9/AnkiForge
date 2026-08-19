# Services IA et Analyse (AnkiForge)

## 1. Agnosticisme et Stratégie des Modèles
L'application adopte une stratégie **Agnostique et Local-First** pour protéger les données de l'utilisateur tout en garantissant des performances maximales.
* **Le Pattern Adapter :** Le code d'AnkiForge n'est pas lié à un SDK propriétaire. Il utilise une couche d'abstraction unifiée (`flexible_service.py`, `gemini_service.py`) permettant d'interfacer n'importe quel modèle local ou cloud.
* **Ollama (Local) :** Par défaut, pour des raisons de confidentialité et d'autonomie hors-ligne, l'application pointe vers un daemon local Ollama sur `localhost:11434`.
* **Cloud APIs & Suivi des Coûts :** Prise en charge des clés API (OpenAI, Anthropic, Gemini). Chaque appel est tracé par `pricing_service.py` et historisé dans `TokenUsageModel` (tokens d'entrée/sortie, coût en USD, temps d'inférence).

## 2. Deux Paradigmes IA Complémentaires

### A. Le Moteur de Workflows DAG & Map-Reduce (`PipelineOrchestrator`)
* **Cas d'usage :** Les vues `creation_view.py`, `pipelines_view.py`, `ab_tests_view.py` et `analysis_view.py`.
* **Philosophie :** Traitements automatisés, reproductibles et déterministes.
* **Mécanique :** 
  * Graphe orienté acyclique (DAG) avec mémoire partagée (`PipelineRunState`).
  * 5 types d'étapes : `LLM_PROMPT` (Persona), `RAG_RETRIEVAL` (recherche vectorielle FAISS/ChromaDB), `MAP_REDUCE` (parallélisation multithread par lot), `HUMAN_VALIDATION` (pause interactive copilote), `PYTHON_TOOL` (outils déterministes en sandbox).
  * Branchements conditionnels (`on_success_step`, `on_failure_step`, `failure_behavior`).
* **Avantage :** Vitesse d'exécution maximale en multithread, zéro hallucination structurelle, et supervision humaine en continu.

### B. Le Système Agentique ReAct & MCP (`ConsultantEngine`)
* **Cas d'usage :** La vue `consultant_view.py`.
* **Philosophie :** Exploration dynamique, raisonnement autonome et assistance conversationnelle avancée.
* **Mécanique :** 
  * Boucle ReAct (*Thought ➔ Action ➔ Observation ➔ Response*) avec auto-correction d'erreurs.
  * Serveur MCP in-process (`mcp_server.py`, `MCPToolService`) exposant des outils sécurisés : `query_peewee`, `get_deck_stats`, `get_cards_by_deck_or_tag`, `update_card_model_css`, `execute_python_tool`.
  * Rendu visuel interactif dans le chat (cartouches de pensée repliables, widgets d'appels d'outils, injection directe de CSS et cartes Anki).

## 3. Cartographie des Fonctionnalités d'Analyse

### Dans Création & Pipelines (Génération)
* **Génération Hiérarchique & Squelettes :** Extraction de plans structurés depuis les documents sources avant génération des cartes pour préserver le contexte pédagogique.
* **Délimitation & Chunking Sémantique :** Sélection des plages de pages utiles (`DocumentDelimitationDialog`) et scission préservant la pagination et les titres (`ChunkingService`).
* **Auto-Tagging :** Classification et étiquetage automatique selon l'ontologie du cours.

### Dans Analyse & Audit (L'Hôpital)
* **Linter Wozniak & Règles Personnalisées :** Application des 20 règles de formulation de Piotr Wozniak et de règles sur-mesure configurables en base (`LinterRuleModel`), avec catégories visuelles et propositions de scission/reformulation atomique.
* **Détection Hybride de Doublons :** Détection textuelle ultra-rapide par extension C native Levenshtein (`c_ext/levenshtein_distance.c`) avec fallback Python transparent (`c_bridge.py`), complétée par une recherche de similarité sémantique vectorielle (FAISS).
* **Smart Coverage & Traçabilité :** Liaison systématique Note ↔ Fragment (`NoteChunkLinkModel`), calcul du taux de couverture documentaire et détection des zones non couvertes (Gap Analysis).
* **Audit FSRS & Leeches :** Identification des cartes difficiles/sangsues et analyse de rétention selon les algorithmes FSRS-4.5.

### Dans Modèles de Cartes (Stylisation)
* **Assistance Design CSS :** Génération et injection dynamique de styles HTML/CSS/Jinja2 dans les modèles de notes avec prévisualisation immédiate WebEngine.
