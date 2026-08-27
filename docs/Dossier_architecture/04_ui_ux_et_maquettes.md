# Ergonomie, UI/UX et Architecture des Vues (AnkiForge)

## 1. Principes Techniques de l'Interface
L'application repose sur un cahier des charges strict pour garantir des performances de type "Desktop App" de qualité professionnelle :
* **100% PySide6 Natif :** Pas d'architecture Electron ni de WebViews systématiques. L'interface est dessinée nativement par Qt pour une fluidité maximale et une consommation mémoire maîtrisée.
* **L'Exception WebEngine (Prévisualisation) :** La seule exception au rendu natif concerne l'aperçu du *Verso/Recto* des fiches Anki. L'application utilise `QWebEngineView` uniquement pour garantir un rendu HTML/CSS et LaTeX (KaTeX/MathJax) identique au pixel près à ce que l'utilisateur verra dans la véritable application Anki.
* **Le Pont Maquette ➔ Qt :** Les maquettes sont initialement prototypées en HTML/CSS (`maquette_all`). Le pont de traduction vers PySide6 n'est qu'une aide visuelle (guideline) et demande une réécriture manuelle (via `ankiforge-qt-translator`) pour s'adapter aux contraintes natives.

## 2. Standards d'Industrie et Expérience Utilisateur (UX)
AnkiForge s'aligne sur les standards des meilleurs IDE (IntelliJ, VSCode) :
* **Multi-fenêtrage et Panneaux Détachables :** L'UI repose sur des systèmes de `IdePanel` et `QDockWidget` permettant à l'utilisateur de réorganiser son espace (ex: détacher l'aperçu de la carte sur un deuxième écran).
* **Design Tokens & Cohérence :** Utilisation centralisée de variables (Design System) pour les espacements, les typographies (polices lisibles type Inter/Roboto) et les palettes de couleurs.
* **Dark Mode Natif :** Le mode sombre n'est pas une option esthétique, c'est le mode de conception prioritaire pour réduire la fatigue visuelle lors de longues sessions d'audit.
* **Accessibilité (WCAG) :** Contrastes validés, navigation au clavier (Tabulation) et raccourcis clavier standards (Ctrl+S, Ctrl+Z) impératifs sur toutes les vues.
* **Feedback Immédiat :** Utilisation systématique de `loading spinners`, de barres de progression et de fenêtres modales "non bloquantes" pour les processus asynchrones (Zéro-Freeze).

## 3. Cartographie Scrupuleuse des Vues Existantes

L'application est découpée en modules fonctionnels (Vues) précis. Voici leur rôle et leurs interactions clés :

### 📊 Tableau de Bord (`dashboard_view.py`)
* **Rôle :** Point d'entrée. Offre une vue d'ensemble de la base locale AnkiForge, sélecteur de profil et métriques globales.
* **Actions/Boutons :** *Boutons de navigation vers les modules, sélecteur de profil actif (`profile_selector.py`), KPIs globaux (Nombre de cartes, documents ingérés, répartition par paquets).*

### 📚 Documents (`documents_view.py`)
* **Rôle :** Hub d'ingestion (Porte d'entrée des sources) et base de connaissances vectorielle.
* **Actions/Boutons :** *Import (PDF via Marker OCR lazy-loadé, Markdown, URL, vidéo YouTube)*, *Délimitation intelligente de la portée (`DocumentDelimitationDialog`)*, *Vectorisation sémantique FAISS/ChromaDB avec badge live*, *Recherche et test RAG instantané (`RAGTestDialog`)*, *Bouton "⚡ Forger la section" vers la Création*.

### 🏭 Création & Pipelines (`creation_view.py` & `pipelines_view.py`)
* **Rôle :** Orchestration de la génération de masse de cartes à partir des sources via le moteur DAG.
* **Actions/Boutons :**
  * Dans Pipelines : *Créer/Éditer un Pipeline DAG*, *Ajouter une étape (`LLM_PROMPT`, `RAG_RETRIEVAL`, `MAP_REDUCE`, `HUMAN_VALIDATION`, `PYTHON_TOOL`)*, *Inspecteur d'étape JetBrains (`StepInspectorPanel`)*, *Éditeur d'outils Python déterministes (`ToolEditorDialog`)*.
  * Dans Création : *Lancer le workflow DAG dans QThreadPool*, *Modale de validation humaine interactive (`HumanValidationDialog`)*, *Mappage automatique des champs selon le modèle de note*, *Générer les cartes*.

### 🏥 Analyse & Audit IA (`analysis_view.py`)
* **Rôle :** Maintenance, audit cognitif et réparation des paquets (Divisée en 4 onglets interactifs).
* **Onglets & Actions Clés :**
  * *Audit Wozniak & Règles Custom :* Sélecteur de paquet, gestionnaire de règles (`linter_rules_dialog.py`), catégories (`cat-atomicite`, `cat-interferences`, etc.), inspecteur comparatif 5 champs SQLite vs proposition IA, boutons *Scinder la carte*, *Appliquer la mutation*, *Ignorer*.
  * *Diagnostic Sources & Smart Coverage :* Analyse de traçabilité via `NoteChunkLinkModel`, détection des lacunes (Gap Analysis) et génération ciblée des cartes manquantes.
  * *Fusions & Doublons :* Matrice de similitude hybride (C-Levenshtein + FAISS vectoriel), inspecteur 3 colonnes avec permutation A ↔ B et injection sélective de champs.
  * *Suivi Financier & FSRS :* Suivi des dépenses en jetons IA par modèle/fournisseur, courbe de rétention FSRS-4.5 et détection des cartes sangsues (Leeches).

### 📝 Édition & Batch Factory (`edition_view.py` & `batch_view.py`)
* **Rôle :** Éditeur manuel façon Browser Anki pour les retouches chirurgicales ou actions en masse.
* **Actions/Boutons :** *Barre de recherche omnibox complexe*, *Éditeur de note avec saisie KaTeX live (`katex_editor.py`)*, *Time Machine et historique de version (`time_machine_dialog.py`)*, *Édition et taggage par lot (`batch_edit_dialog.py`, `auto_tag_dialog.py`)*.

### 🎨 Modèles de Cartes & A/B Tests (`card_models_view.py` & `ab_tests_view.py`)
* **Rôle :** L'Atelier de design des templates et laboratoire comparatif de performance IA.
* **Actions/Boutons :**
  * Dans Modèles : *Éditeur HTML/CSS/Jinja2*, *Aperçu fidèle WebEngine (`safe_web_preview.py`)*, *Inventaire de styles et composants réutilisables*.
  * Dans Tests A/B : *3 modes de comparaison (Modèle vs Modèle, Prompt vs Prompt, Pipeline vs Pipeline)*, *Exécution concurrente dans `QThreadPool`*, *Bannière KPIs en direct (durée, cartes, tokens, coût)*, *Affichage symétrique (Rendu, Champs, JSON)*, *Bouton "Importer dans la Forge" en 1-clic*.

### 🤖 Personas & Consultant IA (`agents_view.py` & `consultant_view.py`)
* **Rôle :** Configuration des agents IA et Copilote autonome ReAct / MCP.
* **Actions/Boutons :**
  * Dans Agents : *Arborescence récursive de dossiers (`PersonaFolderModel`)*, *Filtrage par portée (`⚡ Pipeline`, `🤝 MCP`, `🌐 Universel`)*, *Éditeur 3 onglets (Identité, Prompt Jinja2 avec palette de snippets, Permissions Tools)*, *Simulation unitaire (`AgentTestDialog`)*.
  * Dans Consultant : *Boucle ReAct autonome*, *Cartouches repliables de raisonnement (`ThoughtStepWidget`)*, *Cartes d'appel d'outils MCP (`ToolCallWidget`)*, *Messages avec boutons d'injection CSS et import de cartes (`ChatMessageWidget`)*, *Quick prompts*.

### 🔀 Résolveur de Conflits (`merge_view.py`)
* **Rôle :** Boîte de dialogue de fusion (Merge Dialog) à 3 panneaux lors de la synchronisation `.apkg` ou de mise à jour documentaire.
* **Actions/Boutons :** *Panneau Gauche (Base locale)*, *Panneau Droit (Base entrante)*, *Panneau Central (Éditeur avec coloration différentielle et boutons d'acceptation sélective)*.
