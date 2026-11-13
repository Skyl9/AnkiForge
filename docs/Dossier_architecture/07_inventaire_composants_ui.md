# Inventaire des Composants UI (Audit & Design System)

Ce document maintient la liste détaillée des widgets, composants et dialogues réutilisables PySide6 développés pour AnkiDraft. Il sert de référence pour le respect du Design System (`DesignTokens`), les audits d'interface (WCAG, consistance visuelle) et le développement de nouvelles fonctionnalités.

---

## 1. Composants Fondamentaux (`src/ankidraft/ui/components/`)

### A. Fondations Atomiques
* **Boutons (`buttons.py`) :** Boutons primaires, secondaires, Ghost, Danger, boutons avec icônes (Phosphor Icons). Tous conformes aux tokens d'accessibilité (hover, focus ring).
* **Badges & Pills (`badges.py`, `nav_badge.py`) :** Étiquettes visuelles ultra-arrondies (`border-radius: 9999px`), badges de statut (`🟢 Indexé FAISS`, `⏳ En attente`), compteurs de tags, badges de navigation interactifs et indicateurs de portée (`⚡ Pipeline`, `🤝 MCP`, `🌐 Universel`).
* **Inputs (`inputs.py`, `modal_field.py`) :** Champs de texte stylisés (`GlowLineEdit`), zones de recherche, textareas avec focus ring WCAG et champs à sélection modale.
* **Labels & Capacités (`elided_label.py`, `vision_capability.py`) :** Labels textuels avec élision dynamique responsive (middle/end) et indicateurs de capacités multimodales IA (OCR / Vision).
* **Listes (`lists.py`) :** Widgets de liste personnalisés avec sélection et hover synchronisés.
* **Tables (`tables.py`) :** Vues tabulaires stylisées `QTableView`.
* **Éléments Divers (`misc.py`, `components.py`) :** Séparateurs horizontaux/verticaux, spinners de chargement, conteneurs génériques et export unifié.

### B. Structure & Layout
* **Onglets (`tabs.py`, `segmented_tab_bar.py`) :** Gestion de la navigation principale et secondaire par onglets avec barre d'état et barre d'onglets segmentée (`SegmentedTabBar`).
* **Panneaux (`panels.py`, `flow_layout.py`, `snippet_drawer.py`) :** `IdePanel`, conteneurs de fenêtrage JetBrains-style, `StepInspectorPanel` dans une `QScrollArea`, disposition adaptative en flux (`FlowLayout`) et tiroir coulissant de snippets Jinja2 (`SnippetDrawer`).
* **Barres Supérieures (`title_bar.py`, `topbar.py`) :** Barre de titre personnalisée et barre supérieure d'actions, profil et statut.
* **Navigation Hiérarchique (`hierarchy_breadcrumb_bar.py`, `hierarchy_completer.py`, `tag_completer.py`) :** Bandeau de fil d'Ariane prévisionnel interactif (`::`), autocompléteur hiérarchique en cascade et autocompléteur de tags.

### C. Sélecteurs Modaux & Métier
* **Sélecteur de Deck (`deck_select_window.py`) :** Boîte modale arborescente pour la navigation et la sélection des paquets Anki.
* **Sélecteur de Tags (`tag_select_window.py`) :** Fenêtre de recherche et sélection multiple de tags.
* **Sélecteurs Document, Modèle, Persona & Pipeline (`document_picker_button.py`, `document_select_window.py`, `model_select_window.py`, `persona_select_window.py`, `pipeline_select_window.py`) :** Sélecteurs modaux filtrables pour documents sources, types de notes Anki, agents IA et pipelines DAG.
* **Gestionnaire de Règles Linter (`linter_rules_dialog.py`) :** Interface modale pour l'ajout, la modification et l'organisation par catégories des règles d'audit.
* **Widgets Linter (`linter_widgets.py`) :** Inspecteurs comparatifs 5 champs SQLite vs proposition IA, cartes de rapport d'audit et bannières de catégories.
* **Widgets Doublons (`duplicate_widgets.py`) :** Matrice de similitude hybride (C-Levenshtein + FAISS) et inspecteur de fusion 3 colonnes.

---

## 2. Smart Widgets Métier (`src/ankidraft/ui/widgets/`)

* **Édition & Mathématiques :**
  * `katex_editor.py` : Éditeur mathématique LaTeX avec rendu live KaTeX et autocomplétion.
  * `note_editor_widget.py` & `card_create_view_widget.py` : Éditeur complet de notes multi-champs dynamique et volet unifié de création de carte.
  * `note_table_widget.py` : Tableau virtuel haute performance de visualisation et sélection multiple de notes (`VirtualTableView`).
  * `editor_toolbar_widget.py` : Barre d'outils extensible et personnalisable pour le formatage des champs actifs, avec actions regroupées, raccourcis, noms accessibles en français, repli d'icônes Phosphor indisponibles et recoloration au changement de thème.
  * `cloze_manager.py` : Outil de création rapide d'occlusions (Cloze deletion `{{c1::...}}`).
  * `image_occlusion_editor.py` : Éditeur interactif de masques d'occlusion d'images vectoriels.
  * `drop_image_text_edit.py` : Zone de texte enrichie avec gestion du drag & drop d'images vers le `MediaManager`.
  * `highlighters.py` : Colorateurs syntaxiques pour éditeurs de code (LaTeX, HTML, Jinja2, JSON, Python).
  * `sorting.py` (dans `models/`) & contrôleur `EditionView` : Moteur et contrôleur de tri multi-critères synchronisé (triple accès : bouton dynamique, en-têtes interactifs et menu contextuel) avec persistance par profil et mode (ADR 0044).
* **Visualisation, Diff & Rendu :**
  * `card_preview_widget.py` & `safe_web_preview.py` : Moteur de rendu WebEngine fidèle au comportement d'Anki officiel.
  * `card_semantic_diff_widget.py` : Comparateur sémantique de cartes champ par champ (diff intra-ligne au mot près, édition directe réactive, onglet Anki Live).
  * `mcp_garde_fou_widget.py` & `mcp_status_widget.py` : Sous-onglet Garde-Fou & Validation MCP en disposition Maître-Détail (filtrage, actions de lot, two-phase commit) et cockpit de statut/télémétrie du serveur MCP.
  * `document_outline.py` & `segment_inspector_widget.py` : Sommaire hiérarchique du document source avec statut de couverture et inspecteur détaillé de segment documentaire.
  * `duplicate_resolver.py` : Résolveur interactif de doublons avec fusion champ à champ.
  * `donut_chart.py` & `activity_chart.py` : Graphiques circulaires et chronologiques pour les statistiques de répartition et d'activité.
  * `retention_curve.py` : Courbe d'oubli projetée (data-driven, dérivée de l'intervalle, ADR 0020) et charge à l'équilibre, rendue en QPainter.
* **Navigation & Commandes :**
  * `omnibox.py` : Barre de recherche globale et filtres avancés.
  * `command_palette.py` : Palette de commandes JetBrains/VSCode (raccourci clavier universel).
  * `filter_sidebar.py` : Volet latéral de filtrage par tags, paquets et drapeaux.
  * `notification_menu.py` & `tour_guide.py` : Menu déroulant de notifications système et guide interactif d'onboarding.
* **Historique, Profils & Dialogues :**
  * `profile_selector.py` & `profile_switch_overlay.py` : Gestionnaire et sélecteur de profils isolés (`~/.ankidraft/profiles/`) avec volet de transition visuelle.
  * `theme_transition_overlay.py` : Animation de transition fluide lors du changement de thème sombre/clair.
  * `time_machine_dialog.py` & `version_history_dialog.py` : Visualiseur d'historique de versions (`NoteVersionModel`).
  * `auto_tag_dialog.py` : Modale de suggestion et d'attribution automatique de tags par IA.
  * `batch_edit_dialog.py` : Dialogue d'édition groupée de notes par l'IA.
  * `group_edit_dialog.py` : Boîte de dialogue d'édition groupée manuelle et atomique de notes (tags, modification/remplacement de champs).
  * `linter_dialog.py` : Modale de configuration et lancement d'audit Wozniak.
  * `settings_modal/` : Configuration globale modulaire en 9 onglets (10 en dev) : Moteurs IA, Anki & Formats, Audio & TTS, Maintenance, Extensions, Soutien, Clavier, Aide & Guides (`HelpTab`), Paramètres généraux avec sélecteur de dispositions en grille de miniatures `LayoutGridSelector`.
  * `toast.py` : Notifications système éphémères non-bloquantes.
* **Activité & Réindexation :**
  * `reindex_activity_banner.py` : Bandeau d'activité global (`ReindexActivityBanner`) d'une passe de réindexation RAG, hébergé hors des dispositions enfichables (ADR 0021).

---

## 3. Boîtes de Dialogue Métier (`src/ankidraft/ui/dialogs/`)

* **Validation Humaine Copilote (`human_validation_dialog.py`) :** Modale interactive pour les étapes DAG `HUMAN_VALIDATION` (consultation de l'état, ajustement du plan, injection de variables, reprise fluide).
* **Délimitation & Portée Documentaire :**
  * `document_delimitation_dialog.py` : Délimitation interactive des bornes de pagination et filtrage des sections.
  * `document_scope_dialog.py` & `scope_mode_exclusivity.py` : Sélection modale de portée documentaire avec persistance fine (`sections`, `selected_headings`, `selected_chunk_indices`) et couture d'exclusivité des modes de portée.
  * `repair_headings_dialog.py` : Outil de détection et réparation des incohérences de titres dans les documents.
  * `folder_dialog.py` & `create_deck_dialog.py` : Boîtes de dialogue de création directe de dossiers, sous-dossiers et paquets Anki avec syntaxe hiérarchique `::`.
* **Éditeur d'Outils Python (`tool_editor_dialog.py`) :** IDE intégré pour écrire, sauvegarder et tester des scripts Python déterministes.
* **Simulateurs, Personas & Tests IA :**
  * `agent_test_dialog.py` : Simulateur interactif de personas avec injection de variables dynamiques.
  * `persona_history_dialog.py` & `persona_prompt_override_dialog.py` : Historique des versions de personas et surcharge locale de prompt par étape de pipeline (`persona_override.py`).
  * `prompt_preview_dialog.py` : Prévisualisation du rendu interpolé des templates Jinja2.
  * `rag_test_dialog.py` : Banc de test sémantique vectoriel FAISS/ChromaDB avec scores de similarité.
* **Résolution, Taxonomie & Conflits :**
  * `duplicate_resolver_dialog.py` & `smart_merge_dialog.py` : Modale d'arbitrage fin des doublons détectés et dialogue 3-panneaux de fusion intelligente lors d'imports `.apkg`.
  * `leech_wozniak_split_dialog.py` : Dialogue d'audit et scission automatique de cartes sangsues selon Wozniak.
  * `tag_hygiene_dialog.py` & `taxonomy_audit_dialog.py` : Nettoyage, déduplication, normalisation et audit de la taxonomie des paquets et tags.
  * `css_conflict_dialog.py` : Boîte de résolution des collisions CSS entre types de note.
* **Cartes, Modèles & Exports :**
  * `card_export_dialog.py` & `export_dialog.py` : Dialogues d'exportation ciblée `.apkg` avec sélection de paquets et médias.
  * `change_note_type_dialog.py` & `note_type_role_guide_dialog.py` : Assistant de conversion de type de note avec mappage de champs et guide des rôles de modèles.
  * `model_export_dialog.py` & `model_import_dialog.py` : Import/export de gabarits de types de notes au format JSON.
  * `image_occlusion_dialog.py` : Création de cartes d'occlusion d'image depuis une figure documentaire.
  * `toolbar_customize_dialog.py` : Personnalisation de la barre d'outils de l'éditeur de notes.
* **Imports, Multimédia & Extensions :**
  * `url_import_dialog.py` & `album_transcription_dialog.py` : Ingestion de pages Web / vidéos YouTube et transcription audio par lots.
  * `marker_install_dialog.py` & `starter_pack_dialog.py` : Installation déportée de Marker OCR et pack de démarrage initial.
  * `addon_manager_dialog.py` : Gestionnaire des addons et extensions modulaires.
* **Système, Profils & Support (`history_modal.py`, `selection_dialog.py`, `profile_transfer_dialog.py`, `crash_report_dialog.py`, `feedback_dialog.py`, `support_dialog.py`, `update_dialog.py`, `dialog_gallery_dialog.py`) :** Dialogues transversaux de transfert de profil, rapports de crash, feedback, support, mise à jour et galerie de dialogues.
* **Lecteur de Documentation Embarqué (`doc_reader_dialog.py`) :** Dialogue autonome `DocReaderDialog` pour la consultation applicative native de guides Markdown avec rendu SVG, recherche textuelle en surbrillance et zoom (ADR 0038).

---

## 4. Outils Développeur (`src/ankidraft/ui/widget_gallery/`)

La galerie de widgets est un banc d'observation visuel réservé au mode développement (`ANKIFORGE_ENV=development`), accessible depuis **Paramètres → onglet Développeur → Galerie de widgets**.

* **`widget_gallery_window.py` :** `WidgetGalleryWindow`, dialogue 1000×700px (recherche plein texte, arbre des familles, volet d'aperçu, sélecteur de thème, sélecteur de disposition et bouton « Ouvrir en modal »).
* **`registry.py` :** registre déclaratif des entrées (`GalleryEntry`, décorateur `gallery_widget`, `WidgetGalleryRegistry`), avec le drapeau `modal`.
* **`preview_container.py` :** `PreviewContainer`, héberge l'aperçu courant et le libère explicitement à la fermeture de la galerie.
* **`previews.py` :** conteneurs d'aperçu génériques pour les objets non visuels — `ObjectPreview` (signaux et états d'un `QObject`, appel de `dispose()` à la fermeture), `ItemModelPreview` (modèle Qt lié à une liste ou un tableau), `DelegatePreview` (délégué appliqué à des lignes porteuses de rôles) et `ShellPreviewWindow` (coquille de `MainWindow` recomposée avec les vrais layouts et le vrai registre de vues).
* **`families/` :** une famille par module (`components`, `dialogs`, `layouts`, `models`, `shell`, `viewmodels`), chargée automatiquement et de façon tolérante aux pannes. Chaque famille expose `XXX_FACTORIES`, `xxx_labels()` et `register()`.

Les charges factices proviennent de `src/ankidraft/dev/fake_data.py`, `src/ankidraft/dev/fake_services.py` et `src/ankidraft/dev/fake_qt_models.py` : aucune écriture en base, aucun appel réseau, aucun worker de production. Les familles `views` et `widgets` restent hors périmètre et la **vraie** `MainWindow` n'est jamais instanciée.

Documentation détaillée : [`docs/dev/galerie_widgets.md`](../dev/galerie_widgets.md). Contrats verrouillés par `tests/ui/test_widget_gallery.py`.

---
*Règle d'Or :* Avant toute création d'un nouveau widget dans une vue, consulter systématiquement cet inventaire pour réutiliser ou étendre un composant existant.*
