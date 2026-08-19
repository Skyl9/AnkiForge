# Plan d'Implémentation Global (Architecture & Modules Implémentés)

Ce document récapitule l'implémentation technique complète d'AnkiForge, détaillant les modules opérationnels, les modèles de données et l'intégration des vues.

---

## 1. Moteur d'Orchestration (Core Backend)
* **État Actuel :** ✅ **Moteur DAG Implémenté & Validé par Tests.**
  - `PipelineRunState` gère la mémoire d'état partagée, les variables, l'historique et la sérialisation.
  - `PipelineOrchestrator` prend en charge `LLM_PROMPT`, `RAG_RETRIEVAL`, `MAP_REDUCE`, `HUMAN_VALIDATION`, `PYTHON_TOOL`, les sauts de graphe conditionnels (`on_success_step`, `on_failure_step`), les interruptions thread-safe et l'annulation.
  - Exécution asynchrone multithreadée dans `QThreadPool` avec émission de signaux réactifs (`step_started`, `step_progress`, `human_validation_required`, `pipeline_finished`).

## 2. Vue Éditeur de Pipelines (`pipelines_view.py`) & Système d'Outils Python
* **État Actuel :** ✅ **Éditeur DAG, Inspecteur JetBrains & Outils Python 100% Opérationnels.**
  - Prise en charge complète des Actions Système (`HUMAN_VALIDATION`, `RAG_RETRIEVAL`, `MAP_REDUCE`, `PYTHON_TOOL`) et des Agents IA (`LLM_PROMPT`).
  - Volet Maître-Détail JetBrains via `QSplitter` avec `StepInspectorPanel` isolé dans une `QScrollArea` (zéro chevauchement graphique) et configuration `config_data`.
  - **Système d'Outils Python Déterministes (`ToolService`) :**
    - 4 Outils natifs intégrés : `clean_html_latex` (normalisation LaTeX/HTML), `deduplicate_cards_levenshtein` (déduplication sémantique), `validate_json_schema` (extraction/réparation JSON), `compute_stats_and_metrics` (statistiques et densité).
    - Persistance des scripts personnalisés en base SQLite (`PythonToolModel`, migration 013).
    - Éditeur de scripts Python intégré (`ToolEditorDialog`) avec console de test unitaire.
    - **Capacités MCP pour le Consultant IA (`MCPToolService`)** permettant à l'agent IA de créer, modifier, lister et tester des outils Python réutilisables dans la forge.
  - Sauvegarde atomique Peewee en deux passes avec résolution des clés récursives (`PipelineStepModel`).

## 3. Vue Studio de Création (`creation_view.py`)
* **État Actuel :** ✅ **Raccordé au Moteur DAG & Pause Copilote Interactive.**
  - Exécution multi-étapes asynchrone pilotée par `PipelineOrchestrator` dans `QThreadPool`.
  - Prise en charge des étapes `HUMAN_VALIDATION` via la modale interactive `HumanValidationDialog` (ajustement du plan, injection de `map_items`, reprise `resume()` ou arrêt `cancel()`).
  - Transmission transparente des titres et instructions configurés dans les étapes (`human_validation_config`).
  - Nettoyage et mappage automatique des champs selon le modèle de note sélectionné (`fields_schema`).

## 4. Vue Éditeur d'Agents (`agents_view.py`)
* **État Actuel :** ✅ **Dossiers & Sous-Dossiers Récursifs, Portée Pipeline vs MCP & Onglets JetBrains.**
  - **Système de Dossiers & Sous-dossiers (`PersonaFolderModel`, Migrations 015 & 016) :** Arborescence récursive à N niveaux avec `parent_id`, méthode `get_full_path()`, création de sous-dossiers en 1-clic, suppression récursive sécurisée et réassignation fluide.
  - **Différenciation de Portée (`persona_type`, Migration 014) :** Filtrage instantané `⚡ Pipeline`, `🤝 MCP`, `🌐 Universel` avec pills ultra-arrondies (`border-radius: 9999px`).
  - **Éditeur Riche à 3 Onglets :** Identité & Dossier arborescent, Prompt Jinja2 avec palette de snippets en 1-clic et aperçu interpolé, Grille de permissions d'outils MCP & Python déterministes.
  - **Modale de Test Unitaire (`AgentTestDialog`) :** Simulation en direct avec texte source de test.

## 5. Vue Laboratoire de Tests A/B (`ab_tests_view.py`)
* **État Actuel :** ✅ **Comparaison Multi-niveaux, Bannière KPIs & Import 1-Clic dans la Forge.**
  - **3 Modes de Comparaison :** Modèle vs Modèle (`LLMConfigModel`), Prompt vs Prompt (`PersonaModel`) et Pipeline vs Pipeline (`PipelineModel`).
  - **Exécution Concurrente Asynchrone :** Deux instances distinctes de `PipelineOrchestrator` exécutées en parallèle dans `QThreadPool`.
  - **Bannière de KPIs & Métriques en Direct :** Durée d'exécution chronométrée (⏱️), nombre de flashcards extraites (🃏), tokens estimés (🪙), coût en $ ou gratuité locale (💰) et statut de conformité.
  - **Affichage Symétrique Tri-mode :** `Rendu Cartes` (avec templates NoteType), `Tableau des Champs` (inspection clé/valeur) et `JSON Brut`.
  - **Navigation Synchronisée & Import Forge :** Navigation synchrone optionnelle (A ↔ B) et bouton *Importer dans la Forge* en 1-clic générant les `NoteModel`, `NoteVersionModel` et `CardModel` en SQLite.

## 6. Vue Consultant IA & MCP (`consultant_view.py`)
* **État Actuel :** ✅ **Moteur Autonome ReAct, Outils In-Process MCP & Blocs Interactifs.**
  - **Moteur ReAct Multi-Étapes :** Boucle (*Thought ➔ Action ➔ Observation ➔ Response*) avec émission structurée d'événements et détection automatique des tool calls natifs et JSON manuels.
  - **Registre d'Outils In-Process & MCP :** Interrogation SQL sécurisée en lecture seule (`query_peewee`), calcul de statistiques SRS et cartes sangsues (`get_deck_stats`), recherche de cartes (`get_cards_by_deck_or_tag`), injection CSS dynamique (`update_card_model_css`) et exécution d'outils Python déterministes (`execute_python_tool`).
  - **Widgets Visuels Riches :** `ThoughtStepWidget` (cartouche repliable de raisonnement), `ToolCallWidget` (carte d'appel d'outil avec inspection du JSON d'entrée et observation retournée) et `ChatMessageWidget` (avec détection automatique de CSS et cartes avec boutons d'application/import en 1-clic).
  - **Quick Prompts & Filtre Personas :** Suggestions rapides en capsules arrondies et filtrage ciblé des personas de type `mcp` et `universal`.

## 7. Hub Documentaire (`documents_view.py`) & RAG Local
* **État Actuel :** ✅ **Modale de Délimitation, Vectorisation FAISS & Recherche Sémantique.**
  - **Modale de Délimitation Intelligente :** `DocumentDelimitationDialog` permettant de définir les bornes de pagination, de filtrer les sections utiles et d'exclure le bruit documentaire.
  - **Gestion Lazy Loading Marker OCR :** Détection de la présence de Marker dans l'environnement local avec boîte de confirmation et fallback transparent vers les parseurs standards.
  - **Vectorisation Locale FAISS/ChromaDB & Statut Live :** Stockage matriciel local (`RAGService`, `VectorManager`), badge de statut (`🟢 Indexé FAISS (N chunks)` / `⏳ Non indexé`).
  - **Boîte de Test Sémantique RAG :** `RAGTestDialog` pour interroger instantanément l'index FAISS local avec score de pertinence et localisation des fragments.
  - **Indicateurs de Couverture SRS & Forging :** Sommaire avec statut (`🟢 Couvert` / `⚠️ Non couvert`), jauge de couverture globale et bouton *⚡ Forger la section* raccordé directement à la vue Création.

## 8. L'Hôpital : Analyse & Audit (`analysis_view.py`)
* **État Actuel :** ✅ **Linter Wozniak, Règles Personnalisées, Diagnostic Sources RAG, Tokens/SRS & Matrice de Doublons 3 Panneaux.**
  - **Audit & Linter Wozniak :** Catégories interactives (Atomicité, KaTeX, Non-interférence, Questions univoques), règles personnalisables (`LinterRuleModel`, migration 017), badges pills (`border-radius: 9999px`), inspecteur déroulant des 5 champs SQLite vs proposition IA et scission/mutation 1-clic.
  - **Diagnostic des Sources & Anti-Hallucination :** Grille des documents de cours, liens `NoteChunkLinkModel` et calcul de couverture en direct avec routage immédiat vers l'Usine de Création.
  - **Simulateur Économique & FSRS-4.5 :** Dépenses cumulées en jetons IA par fournisseur/modèle (`TokenUsageModel`), détection des cartes sangsues et canvas QPainter de courbe de rétention.
  - **Matrice de Doublons & Fusion 3 Panneaux :** Détection hybride (Levenshtein natif C + Vectoriel FAISS), boîte de dialogue de fusion (Merge Dialog) à 3 colonnes avec permutation A ↔ B et injection sélective de champs.

## 9. Atelier Modèles de Cartes (`card_models_view.py`) & Édition (`edition_view.py`, `batch_view.py`)
* **État Actuel :** ✅ **Édition HTML/CSS/Jinja2, Rendu KaTeX & Time Machine.**
  - Éditeur de modèles avec prévisualisation fidèle WebEngine (`safe_web_preview.py`).
  - Édition des notes avec saisie mathématique KaTeX en direct (`katex_editor.py`) et gestionnaire d'occlusions (`cloze_manager.py`).
  - Visualiseur d'historique de versions Time Machine (`time_machine_dialog.py`, `NoteVersionModel`).
  - Traitements et étiquetage par lot (`batch_edit_dialog.py`, `auto_tag_dialog.py`).

## 10. Multi-Profils & Gestion des Données
* **État Actuel :** ✅ **Isolation Totale Multi-Profils (`ProfileManager`).**
  - Profils indépendants sous `~/.ankiforge/profiles/<profile_name>/`.
  - Base SQLite et répertoire de médias isolés par profil.
  - Sélecteur de profil instantané dans l'interface (`profile_selector.py`).
  - Suite globale de **146/146 tests** unitaires et UI au vert.
