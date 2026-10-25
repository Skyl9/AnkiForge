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
  * `editor_toolbar_widget.py` : Barre d'outils extensible et personnalisable pour le formatage des champs actifs, avec actions regroupées, raccourcis, noms accessibles en français, repli d'icônes Phosphor indisponibles et recoloration au changement de thème.
  * `cloze_manager.py` : Outil de création rapide d'occlusions (Cloze deletion `{{c1::...}}`).
  * `drop_image_text_edit.py` : Zone de texte enrichie avec gestion du drag & drop d'images vers le `MediaManager`.
  * `sorting.py` (dans `models/`) & contrôleur `EditionView` : Moteur et contrôleur de tri multi-critères synchronisé (triple accès : bouton dynamique, en-têtes interactifs et menu contextuel) avec persistance par profil et mode (ADR 0044).
* **Visualisation, Diff & Rendu :**
  * `card_preview_widget.py` & `safe_web_preview.py` : Moteur de rendu WebEngine fidèle au comportement d'Anki officiel.
  * `card_semantic_diff_widget.py` : Comparateur sémantique de cartes champ par champ (diff intra-ligne au mot près, édition directe réactive, onglet Anki Live).
  * `mcp_garde_fou_widget.py` : Sous-onglet Garde-Fou & Validation MCP en disposition Maître-Détail (filtrage, actions de lot, two-phase commit).
  * `donut_chart.py` : Graphiques circulaires pour les statistiques de répartition.
  * `retention_curve.py` : Courbe d'oubli projetée (data-driven, dérivée de l'intervalle, ADR 0020) et charge à l'équilibre, rendue en QPainter.
* **Navigation & Commandes :**
  * `omnibox.py` : Barre de recherche globale et filtres avancés.
  * `command_palette.py` : Palette de commandes JetBrains/VSCode (raccourci clavier universel).
  * `filter_sidebar.py` : Volet latéral de filtrage par tags, paquets et drapeaux.
* **Historique, Profils & Dialogues :**
  * `profile_selector.py` : Gestionnaire et sélecteur de profils isolés (`~/.ankiforge/profiles/`).
  * `time_machine_dialog.py` & `version_history_dialog.py` : Visualiseur d'historique de versions (`NoteVersionModel`).
  * `auto_tag_dialog.py` : Modale de suggestion et d'attribution automatique de tags par IA.
  * `batch_edit_dialog.py` : Dialogue d'édition groupée de notes par l'IA.
  * `group_edit_dialog.py` : Boîte de dialogue d'édition groupée manuelle et atomique de notes (tags, modification/remplacement de champs).
  * `settings_modal/` : Configuration globale modulaire en 9 onglets (10 en dev) : Moteurs IA, Anki & Formats, Audio & TTS, Maintenance, Extensions, Soutien, Clavier, Aide & Guides (`HelpTab`), Paramètres généraux avec sélecteur de dispositions en grille de miniatures `LayoutGridSelector`.
  * `toast.py` : Notifications système éphémères non-bloquantes.
* **Activité & Réindexation :**
  * `reindex_activity_banner.py` : Bandeau d'activité global (`ReindexActivityBanner`) d'une passe de réindexation RAG, hébergé hors des dispositions enfichables (ADR 0021).

---

## 3. Boîtes de Dialogue Métier (`src/ankiforge/ui/dialogs/`)

* **Validation Humaine Copilote (`human_validation_dialog.py`) :** Modale interactive pour les étapes DAG `HUMAN_VALIDATION` (consultation de l'état, ajustement du plan, injection de variables, reprise fluide).
* **Délimitation & Portée Documentaire :**
  * `document_delimitation_dialog.py` : Délimitation interactive des bornes de pagination et filtrage des sections.
  * `document_scope_dialog.py` : Sélection modale de portée documentaire avec persistance fine (`sections`, `selected_headings`, `selected_chunk_indices`) entre runs successifs.
  * `folder_dialog.py` : Boîte de dialogue de création directe de dossiers et sous-dossiers (`FolderCreateDialog`) avec choix du parent et syntaxe hiérarchique Anki `::`.
* **Éditeur d'Outils Python (`tool_editor_dialog.py`) :** IDE intégré pour écrire, sauvegarder et tester des scripts Python déterministes.
* **Simulateurs & Tests IA :**
  * `agent_test_dialog.py` : Simulateur interactif de personas avec injection de variables dynamiques.
  * `prompt_preview_dialog.py` : Prévisualisation du rendu interpolé des templates Jinja2.
  * `rag_test_dialog.py` : Banc de test sémantique vectoriel FAISS/ChromaDB avec scores de similarité.
* **Résolution & Conflits :**
  * `duplicate_resolver_dialog.py` : Modale de comparaison et arbitrage fin des doublons détectés.
  * `css_conflict_dialog.py` : Boîte de résolution des collisions CSS entre types de note.
* **Imports & Extensions :**
  * `url_import_dialog.py` : Ingestion de pages Web et de vidéos YouTube avec parsing JS et sous-titres.
  * `addon_manager_dialog.py` : Gestionnaire des addons et extensions modulaires.
* **Historique & Sélections (`history_modal.py`, `selection_dialog.py`) :** Dialogues réutilisables pour la sélection et l'inspection de journaux d'actions.
* **Lecteur de Documentation Embarqué (`doc_reader_dialog.py`) :** Dialogue autonome `DocReaderDialog` pour la consultation applicative native de guides Markdown avec rendu SVG, recherche textuelle en surbrillance et zoom (ADR 0038).

---
*Règle d'Or :* Avant toute création d'un nouveau widget dans une vue, consulter systématiquement cet inventaire pour réutiliser ou étendre un composant existant.*
