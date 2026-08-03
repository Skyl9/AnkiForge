# Plan d'Implémentation Global (Gap Analysis)

Ce document confronte le code actuel du projet avec la nouvelle vision définie dans le `Dossier_architecture`. Il sert de feuille de route pour les prochains sprints de développement.

## 1. Moteur d'Orchestration (Core Backend)
* **État Actuel :** La base de données possède `AgentModel`, `PipelineModel`, et `PipelineStepModel` pour un flux linéaire.
* **Cible (Dossier 06) :** Moteur DAG avec gestion du contexte (State) et types d'étapes.
* **Actions Métier :**
  1. Ajouter `step_type` (Enum: LLM, RAG, MAP_REDUCE, HUMAN_VALIDATION) dans `PipelineStepModel`.
  2. Créer la classe Python `PipelineOrchestrator` capable de lire ce DAG, d'itérer (Map-Reduce) via `QThreadPool`, et de s'interrompre en renvoyant un signal à l'UI pour la validation humaine.
  3. Ajouter le champ `allowed_tools` JSON au `AgentModel` (Persona).

## 2. Hub Documentaire (`documents_view.py`)
* **État Actuel :** Vue balbutiante.
* **Cible (Dossier 06) :** Le point de départ du RAG.
* **Actions Métier :**
  1. Implémenter la modale IHM de **Délimitation** (Scan léger via `pypdf` -> Sélection des plages de pages).
  2. Implémenter le script de *Lazy Loading* pour installer `Marker` dans le dossier `data` uniquement au premier import de PDF.
  3. Intégrer FAISS ou ChromaDB local. Créer le pipeline d'ingestion (Texte -> Chunking Sémantique -> Vectorisation -> BDD).

## 3. L'Usine : Création (`creation_view.py` & `pipelines_view.py`)
* **État Actuel :** Génération simple.
* **Cible (Dossier 01 & 06) :** Génération hiérarchique avec RAG et pause utilisateur.
* **Actions Métier :**
  1. Dans `pipelines_view.py`, l'IHM doit permettre de configurer des étapes de type `RAG_RETRIEVAL` pointant vers un document.
  2. Dans `creation_view.py`, l'IHM doit s'abonner aux signaux du `PipelineOrchestrator`. Quand une étape `HUMAN_VALIDATION` est atteinte (ex: Plan du cours généré), afficher l'arbre interactif, attendre la correction de l'utilisateur, puis renvoyer le signal `resume()`.

## 4. L'Hôpital : Analyse & Audit (`analysis_view.py`)
* **Note sur les maquettes :** Les maquettes HTML originelles de cette vue sont en partie obsolètes. La nouvelle architecture orientée "Pipeline Batch" dicte une UX différente.
* **État Actuel :** Implémentations disparates (Diagnostic Sources, Fusions & Doublons statiques).
* **Cible (Dossier 06) :** Traitement de masse par Map-Reduce.
* **Actions Métier :**
  1. **Linter Wozniak :** Remplacer l'appel LLM synchrone par le lancement d'un Pipeline `MAP_REDUCE`. L'UI affiche un loader, puis récupère uniquement le sous-ensemble de "Cartes Malades" à valider dans une grille.
  2. **Diagnostic Sources :** Implémenter la logique d'Audit Anti-hallucination. L'IA doit pouvoir faire un `RAG_RETRIEVAL` sur le document lié à la carte pour vérifier la véracité du Verso.
  3. **Fusions & Doublons :** Conserver la Matrice et l'Inspecteur (excellents composants UI), mais remplacer la détection de texte brut par une requête de similarité vectorielle (Embeddings) pour trouver les doublons sémantiques.

## 5. Le Consultant (`consultant_view.py` & `agents_view.py`)
* **État Actuel :** Chat classique.
* **Cible (Dossier 05) :** Pattern ReAct, Copilote autonome.
* **Actions Métier :**
  1. Coder le moteur de boucle ReAct (Thought -> Action -> Observation -> Response).
  2. Implémenter un **Serveur MCP (Model Context Protocol)** natif embarqué qui expose les `Tools` Python sécurisés (ex: `query_peewee(sql)`, `update_card_style(css)`). L'Agent interrogera le backend via ce protocole standardisé.
  3. L'UI doit gérer l'affichage de ces actions (ex: au lieu de juste répondre du texte, le Chat affiche un composant `QTableView` contenant les cartes trouvées par la requête SQL du Consultant).

## 6. L'Atelier : Édition & Modèles (`edition_view.py` & `card_models_view.py`)
* **État Actuel :** Édition standard.
* **Cible (Dossier 03 & 04) :** IDE hybride avec Inventaire de Styles.
* **Actions Métier :**
  1. Implémenter le **Smart Merge** (3 panneaux) dans l'éditeur pour la résolution de conflits.
  2. Créer la BDD ou le stockage JSON pour l'"Inventaire de Styles" (Snippets CSS/HTML réutilisables).
  3. Connecter le Consultant à cette vue pour qu'il puisse y injecter du CSS généré.
