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
* **Rôle :** Point d'entrée. Offre une vue d'ensemble de la base locale AnkiForge.
* **Actions/Boutons :** *Boutons de navigation vers les autres modules, KPIs globaux (Nombre de cartes, documents ingérés).*

### 📚 Documents (`documents_view.py`)
* **Rôle :** Hub d'ingestion (Porte d'entrée des sources).
* **Actions/Boutons :** *Bouton d'import (PDF, URL)*, *Bouton de délimitation (Plage de pages)*, *Bouton "Lancer la vectorisation/RAG"*.

### 🏭 Création & Pipelines (`creation_view.py` & `pipelines_view.py`)
* **Rôle :** Orchestration de la génération de masse de cartes à partir des sources.
* **Actions/Boutons :** 
  * Dans Pipelines : *Créer un Pipeline*, *Ajouter une étape (MapReduce/Agent)*.
  * Dans Création : *Lancer le workflow*, *Boutons de Validation Humaine (Accepter le plan, Refuser une branche)*, *Générer les cartes*.

### 🏥 Analyse & Audit IA (`analysis_view.py`)
* **Rôle :** Maintenance et réparation des paquets (Divisée en onglets).
* **Actions/Boutons Clés :**
  * *Audit Wozniak :* `Sélectionner un paquet`, `Analyser`, `Accepter la reformulation`, `Ignorer`.
  * *Diagnostic Sources :* `Analyser tous les documents`, Puces de filtres (PDF, MD, Web).
  * *Fusions & Doublons :* Matrice de similitude, `Auto-fusionner >95%`, `Permuter A ↔ B` (dans l'inspecteur), `Valider la fusion`, `Faux doublon`.

### 📝 Édition & Batch (`edition_view.py` & `batch_view.py`)
* **Rôle :** Éditeur manuel façon Browser Anki pour les retouches chirurgicales ou actions en masse.
* **Actions/Boutons :** *Barre de recherche complexe*, *Éditer (Code/Rendu)*, *Ajouter un tag*, *Changement de paquet par lot*.

### 🎨 Modèles de Cartes & A/B Tests (`card_models_view.py` & `ab_tests_view.py`)
* **Rôle :** L'Atelier de design pour créer les types de notes (Templates).
* **Actions/Boutons :** *Éditeur HTML/CSS*, *Bouton d'Aperçu WebEngine*, *Piocher dans l'inventaire de styles*, *Générer variante (A/B Test)*.

### 🤖 Agents & Consultant (`agents_view.py` & `consultant_view.py`)
* **Rôle :** Configuration des "Personas" et Chatbot d'assistance (Agent autonome).
* **Actions/Boutons :** 
  * Dans Agents : *Créer un Agent*, *Définir le System Prompt*, *Sélectionner les Tools (Cases à cocher)*.
  * Dans Consultant : *Barre de Chat*, *Ouvrir l'outil de validation (lorsque l'agent propose une action)*.
