# Inventaire des Composants UI (Audit & Design System)

Ce document maintient la liste détaillée des widgets, composants et dialogues réutilisables PySide6 développés pour AnkiForge. Il sert de référence pour le respect du Design System (`DesignTokens`), les audits d'interface (WCAG, consistance visuelle) et le développement de nouvelles fonctionnalités.

---

## 1. Composants Fondamentaux (`src/ankiforge/ui/components/`)

### A. Fondations Atomiques
* **Boutons (`buttons.py`) :** Boutons primaires, secondaires, Ghost, Danger, boutons avec icônes (Phosphor Icons). Tous conformes aux tokens d'accessibilité (hover, focus ring).
* **Badges & Pills (`badges.py`) :** Étiquettes visuelles ultra-arrondies (`border-radius: 9999px`), badges de statut (`🟢 Indexé FAISS`, `⏳ En attente`), compteurs de tags et indicateurs de portée (`⚡ Pipeline`, `🤝 MCP`, `🌐 Universel`).
* **Inputs (`inputs.py`) :** Champs de texte stylisés (`GlowLineEdit`), zones de recherche, textareas avec focus ring WCAG.
* **Listes (`lists.py`) :** Widgets de liste personnalisés avec sélection et hover synchronisés.
* **Tables (`tables.py`) :** Vues tabulaires stylisées `QTableView`.
* **Éléments Divers (`misc.py`) :** Séparateurs horizontaux/verticaux, spinners de chargement, conteneurs génériques.

### B. Structure & Layout
* **Onglets (`tabs.py`) :** Gestion de la navigation principale et secondaire par onglets avec barre d'état.
* **Panneaux (`panels.py`) :** `IdePanel`, conteneurs de fenêtrage JetBrains-style et `StepInspectorPanel` dans une `QScrollArea`.

### C. Sélecteurs Modaux & Métier
* **Sélecteur de Deck (`deck_select_window.py`) :** Boîte modale arborescente pour la navigation et la sélection des paquets Anki.
* **Sélecteur de Tags (`tag_select_window.py`) :** Fenêtre de recherche et sélection multiple de tags.
* **Gestionnaire de Règles Linter (`linter_rules_dialog.py`) :** Interface modale pour l'ajout, la modification et l'organisation par catégories des règles d'audit.
* **Widgets Linter (`linter_widgets.py`) :** Inspecteurs comparatifs 5 champs SQLite vs proposition IA, cartes de rapport d'audit et bannières de catégories.
* **Widgets Doublons (`duplicate_widgets.py`) :** Matrice de similitude hybride (C-Levenshtein + FAISS) et inspecteur de fusion 3 colonnes.

---

## 2. Smart Widgets Métier (`src/ankiforge/ui/widgets/`)

* **Édition & Mathématiques :**
  * `katex_editor.py` : Éditeur mathématique LaTeX avec rendu live KaTeX et autocomplétion.
  * `note_editor_widget.py` : Éditeur complet de notes avec gestion multi-champs dynamique.
  * `cloze_manager.py` : Outil de création rapide d'occlusions (Cloze deletion `{{c1::...}}`).
  * `drop_image_text_edit.py` : Zone de texte enrichie avec gestion du drag & drop d'images vers le `MediaManager`.
* **Visualisation & Rendu :**
  * `card_preview_widget.py` & `safe_web_preview.py` : Moteur de rendu WebEngine fidèle au comportement d'Anki officiel.
  * `donut_chart.py` : Graphiques circulaires pour les statistiques de répartition.
* **Navigation & Commandes :**
  * `omnibox.py` : Barre de recherche globale et filtres avancés.
  * `command_palette.py` : Palette de commandes JetBrains/VSCode (raccourci clavier universel).
  * `filter_sidebar.py` : Volet latéral de filtrage par tags, paquets et drapeaux.
* **Historique, Profils & Dialogues :**
  * `profile_selector.py` : Gestionnaire et sélecteur de profils isolés (`~/.ankiforge/profiles/`).
  * `time_machine_dialog.py` & `version_history_dialog.py` : Visualiseur d'historique de versions (`NoteVersionModel`).
  * `auto_tag_dialog.py` : Modale de suggestion et d'attribution automatique de tags par IA.
  * `batch_edit_dialog.py` : Dialogue d'édition groupée de notes.
  * `settings_modal.py` : Configuration globale (fournisseurs LLM, paramètres généraux, chemins).
  * `toast.py` : Notifications système éphémères non-bloquantes.

---

## 3. Boîtes de Dialogue Métier (`src/ankiforge/ui/dialogs/`)

* **Validation Humaine Copilote (`human_validation_dialog.py`) :** Modale interactive pour les étapes DAG `HUMAN_VALIDATION` (consultation de l'état, ajustement du plan, injection de variables, reprise fluide).
* **Éditeur d'Outils Python (`tool_editor_dialog.py`) :** IDE intégré pour écrire, sauvegarder et tester des scripts Python déterministes.
* **Historique & Sélections (`history_modal.py`, `selection_dialog.py`) :** Dialogues réutilisables pour la sélection et l'inspection de journaux d'actions.

---
*Règle d'Or :* Avant toute création d'un nouveau widget dans une vue, consulter systématiquement cet inventaire pour réutiliser ou étendre un composant existant.*
