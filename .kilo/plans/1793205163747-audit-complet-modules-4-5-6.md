# Plan d'audit combiné — Modules 4 (repositories), 5 (services), 6 (ui)

**Contexte :** Audit combiné (Code Mort + Clean Code + Architecture) de `src/ankiforge/`, continuation après les modules 1 (`utils`), 2 (`security`), 3 (`database`) déjà rédigés dans `ankiforge_obsidian/audit-complet-par-module-2026-10-28.md`. Ordre imposé : `repositories` → `services` → `ui`.

**Méthode par fichier (3 volets obligatoires) :**
1. **Volet 1 — Code mort :** script Python AST pour lister tous les symboles définis (fonctions/classes/constants publiques et privées) avec leurs références dans `src/` (hors le fichier lui-même) et dans `tests/` + `script/`. Classification : Mort confirmé / Mort applicatif (zombie test uniquement) / Vivant. Vérification mécanique des faux-positifs AnkiForge (signaux/slots Qt, `WidgetGalleryWindow`/`registry.py`, `fake_services.py`, outils MCP dans `mcp_tool_registry.py`/`tools_catalog.py`, migrations dynamiques, hooks plugins).
2. **Volet 2 — Architecture :** vérification des dépendances inversées via `grep -rnE "(from|import) ankiforge\.(ui|services|repositories|database)" <module>/`. Lecture réelle du corps de chaque fichier pour détecter inversions de couches, god classes, modules superficiels, duplication, N+1, `db.atomic()` mal utilisé, I/O bloquant GUI, couleurs en dur hors `DesignTokens`, chemins Nuitka hors `paths.py`.
3. **Volet 3 — Redaction :** section structurée dans le rapport selon le format obligatoire (Inventaire du Code Mort / Constats d'Architecture / Constats Clean Code avec priorités P0-P3). Respect des 4 règles strictes : zéro "bruit positif" dans les tableaux, distinction zombie vs test hook d'isolation, tranchage immédiat des cas limites, formatage Markdown strict (pas de `- |` devant les lignes de tableau, pas de retour à l'intérieur d'une cellule).

**Règle de déroulement :** petit bout par petit bout, arrêt et compactage entre chaque module (et entre chaque sous-partie de `services` et `ui` vu leur volume). Pas de modification de code source pendant l'audit.

---

## MODULE 4 : `src/ankiforge/repositories/` (9 fichiers)

Fichiers à lire intégralement, un par un :
1. `__init__.py`
2. `base.py`
3. `audit_repository.py`
4. `deck_repository.py`
5. `document_repository.py`
6. `note_repository.py`
7. `persona_repository.py`
8. `pipeline_repository.py`
9. `setting_repository.py`

Tâches pour chaque fichier :
- Lecture complète du corps (pas de grep uniquement).
- Exécution du script de détection de code mort (AST) sur le paquet `repositories/`.
- Vérification des dépendances inversées (`repositories → ui/services/database` interdit).
- Identification des méthodes publiques sans appelant applicatif (55 déjà identifiées dans la version précédente du rapport, à confirmer/actualiser).
- Rédaction de la section MODULE 4 dans le rapport.
- **Arrêt + compactage** : résumé synthétique à l'utilisateur, attente de validation avant de passer au module 5.

---

## MODULE 5 : `src/ankiforge/services/` (découpé en sous-parties)

### 5.1 Racine `services/` (10 fichiers)
`auto_updater.py`, `crash_reporter_service.py`, `feedback_service.py`, `profile_content_transfer.py`, `profile_lock_service.py`, `profile_manager.py`, `reindex_activity_service.py`, `reindex_service.py`, `settings_service.py`, `update_checker.py`.

### 5.2 `services/ai/` (32 fichiers)
`__init__.py`, `album_transcription_types.py`, `base.py`, `consultant_engine.py`, `context_compactor.py`, `flexible_service.py`, `gemini_service.py`, `linter.py`, `mcp_batch_safeguard.py`, `mcp_cli.py`, `mcp_daemon.py`, `mcp_server.py`, `mcp_tool_registry.py`, `mcp_tracker.py`, `model_catalog.py`, `ocr_service.py`, `orchestrator.py`, `persona_override.py`, `persona_templates.py`, `persona_version_service.py`, `pricing_service.py`, `prompt_interpolator.py`, `rag_service.py`, `retry.py`, `schemas.py`, `staged_patch_registry.py`, `state.py`, `templates/` (à explorer), `tools_catalog.py`, `utils.py`, `vision_category_service.py`.

### 5.3 `services/audit/` (5 fichiers)
`__init__.py`, `coverage_alignment_service.py`, `fsrs_projection_service.py`, `leech_service.py`, `metrics_service.py`.

### 5.4 `services/batch/` (4 fichiers)
`__init__.py`, `models.py`, `provenance.py`, `slicing_service.py`.

### 5.5 `services/cards/` (21 fichiers)
`__init__.py`, `album_service.py`, `bulk_hygiene_service.py`, `card_export_service.py`, `card_model_io.py`, `duplicate_manager.py`, `export_manager.py`, `flag_service.py`, `group_edit_service.py`, `image_occlusion_service.py`, `import_manager.py`, `media_manager.py`, `note_manager.py`, `note_type_roles.py`, `note_type_service.py`, `snippet_library.py`, `store_manager.py`, `taxonomy_service.py`, `tts_service.py`, `visual_resolver.py`.

### 5.6 `services/parsing/` (11 fichiers)
`__init__.py`, `audio_parser.py`, `chunking_service.py`, `document_parser.py`, `epub_parser.py`, `marker_service.py`, `pptx_parser.py`, `web_importer.py`, `web_js_renderer.py`, `youtube_parser.py`, `yt_dlp_service.py`.

### 5.7 `services/rag/` (6 fichiers)
`__init__.py`, `bm25_index.py`, `coverage_alignment_service.py`, `hybrid_retriever.py`, `vector_manager.py`, `visual_rag_service.py`.

### 5.8 `services/search/` (2 fichiers)
`__init__.py`, `fts_service.py`.

### 5.9 `services/system/` (2 fichiers)
`__init__.py`, `notification_service.py`.

### 5.10 `services/tools/` (3 fichiers)
`mcp_tool_service.py`, `tool_sandbox.py`, `tool_service.py`.

### 5.11 `services/workers/` (16 fichiers)
`__pycache__/`, `ab_worker.py`, `album_worker.py`, `batch_edit_worker.py`, `batch_worker.py`, `coverage_worker.py`, `creation_worker.py`, `document_batch_worker.py`, `document_worker.py`, `duplicate_worker.py`, `image_occlusion_worker.py`, `import_cards_worker.py`, `linter_worker.py`, `migration_reindex_worker.py`, `url_import_worker.py`, `vector_worker.py`, `youtube_worker.py`.

### 5.12 `services/plugins/` (5 fichiers)
`__init__.py`, `api.py`, `event_bus.py`, `manifest_schema.py`, `plugin_manager.py`.

### 5.13 `services/documentation/` (2 fichiers)
`__init__.py`, `doc_service.py`.

### 5.14 `services/markdown/` (7 fichiers)
`__init__.py`, `ai_structurer.py`, `formatter.py`, `models.py`, `structurer.py`, `table_of_contents.py`, `text_utils.py`.

Pour chaque sous-partie : lecture intégrale de chaque fichier, script AST code mort, vérification dépendances inversées, rédaction section, **arrêt + compactage**.

---

## MODULE 6 : `src/ankiforge/ui/` (découpé en sous-parties)

### 6.1 Racine `ui/`
`dispatch.py`, `main_window.py`, `preferences_dialog.py`, `theme.py`.

### 6.2 `ui/components/` (35 fichiers)
À explorer fichier par fichier (badges, buttons, code_editor, deck_select_window, etc.).

### 6.3 `ui/dialogs/` (36 fichiers)
À explorer fichier par fichier.

### 6.4 `ui/layouts/` (7 fichiers)
`base_layout.py`, `dashboard_layout.py`, `glass_layout.py`, `ide_layout.py`, `layout_manager.py`, `macos_layout.py`.

### 6.5 `ui/models/`
À explorer (non listé lors de la lecture du répertoire, à vérifier).

### 6.6 `ui/shortcuts/` (4 fichiers)
`catalog.py`, `manager.py`, `models.py`.

### 6.7 `ui/style_engine/` (6 fichiers)
`appearance.py`, `engine.py`, `theme_profile.py`, `theme_storage.py`, `themes.py`.

### 6.8 `ui/viewmodels/` (10 fichiers)
`agents_viewmodel.py`, `analysis_viewmodel.py`, `base.py`, `batch_viewmodel.py`, `creation_viewmodel.py`, `dashboard_viewmodel.py`, `documents_viewmodel.py`, `edition_viewmodel.py`, `pipeline_viewmodel.py`.

### 6.9 `ui/views/` (12 sous-répertoires + fichiers)
`ab_tests_view/`, `agents_view/`, `analysis_view/`, `batch_view/`, `card_models_view/`, `consultant_view/`, `creation_view/`, `dashboard_view.py`, `documents_view/`, `edition_view/`, `merge_view.py`, `pipelines_view/`.

### 6.10 `ui/widgets/` (35 fichiers)
À explorer fichier par fichier.

### 6.11 `ui/widget_gallery/` (6 fichiers)
`families/`, `preview_container.py`, `previews.py`, `registry.py`, `widget_gallery_window.py`.

Pour chaque sous-partie : lecture intégrale, script AST, dépendances inversées, rédaction, **arrêt + compactage**.

---

## Vérifications mécaniques obligatoires (à exécuter avant chaque rédaction de module)

1. **Script AST code mort :** extraire toutes définitions (fonctions/classes/constants) du module, compter références dans `src/` (hors le module) et `tests/` + `script/`. Lister les symboles à 0 référence `src/`. Classer chacun : Mort confirmé / Mort applicatif (test uniquement) / Vivant.
2. **Dépendances inversées :** `grep -rnE "(from|import) ankiforge\.(ui|services|repositories|database)" <module>/`. Résultat réel exigé, pas de « à vérifier ».
3. **Faux-positifs AnkiForge :** vérifier signaux/slots Qt dynamiques, `WidgetGalleryWindow`/`registry.py`, `fake_services.py`, outils MCP (`mcp_tool_registry.py`/`tools_catalog.py`), migrations dynamiques (`database/migration.py`), hooks plugins (`services/plugins/`).

---

## Risques

- **Volume important** : plusieurs centaines de fichiers à lire en profondeur. Le plan doit être itératif avec arrêts fréquents pour éviter la perte de contexte.
- **Perte de données du rapport** : ne jamais utiliser `write` complet sur `ankiforge_obsidian/audit-complet-par-module-2026-10-28.md` (écrasement déjà subi). Utiliser uniquement des `edit` ciblés pour ajouter les sections module par module.
- **Tentation de ne faire que du grep** : l'utilisateur a explicitement interdit. Chaque fichier doit être lu en entier (outil `read`) avant tout constat.
- **Règles de rédaction strictes** : zéro bruit positif dans les tableaux, distinction zombie/test-hook, tranchage immédiat des cas limites, formatage Markdown strict.

---

## Points d'arrêt et compactage

Après chaque module (et chaque sous-partie de `services` et `ui`) :
1. Résumé synthétique des trouvailles (code mort, inversions de dépendance, constats P0/P1/P2).
2. Attendre la validation de l'utilisateur avant de continuer.
3. L'utilisateur compacte le contexte si nécessaire.

---

## Livrable final attendu

Sections MODULE 4, MODULE 5 (sous-parties 5.1 à 5.14), MODULE 6 (sous-parties 6.1 à 6.11) ajoutées dans `ankiforge_obsidian/audit-complet-par-module-2026-10-28.md`, rédigées selon le format obligatoire des 3 volets, sans aucune modification de code source.
