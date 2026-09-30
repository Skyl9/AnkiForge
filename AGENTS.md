# AGENTS.md - AnkiForge Quick Reference

## Project Overview
AnkiForge: AI-assisted flashcard creation IDE for Anki ecosystem. Python 3.12+, PySide6/Qt6, SQLite/Peewee ORM, local-first architecture with MCP protocol.

## Key Commands
```bash
# Install deps (standard / dev+docs)
uv sync
uv sync --group dev

# Run application
uv run ankiforge
uv run ankiforge --dev          # dev environment (~/.ankiforge-dev)
uv run ankiforge --prod         # force production (~/.ankiforge)
uv run ankiforge --smoke-test   # binary integrity check
uv run ankiforge --clone-prod-to-dev

# Tests
uv run pytest                   # all 1700+ tests (headless Qt via pytest-qt)
uv run pytest -m "not slow"     # fast tests suite (pre-push hook, < 15s)
uv run pytest -m unit           # pure unit & algorithmic tests only (< 2s)
uv run pytest -m integration    # database & service integration tests
uv run pytest -m ui             # PySide6 headless UI tests
uv run pytest tests/path/test_file.py::TestClass::test_method

# Quality checks (run in order before push)
uv run ruff check --fix .
uv run ruff format --check .
uv run mypy src/ankiforge       # strict 100% typing required
uv run bandit -c pyproject.toml -r src/

# Skills audit & consistency check
uv run python .agents/skills/mise-a-jour-metadonnees/scripts/auditer_coherence_skills.py

# Documentation
uv run zensical serve           # live at http://127.0.0.1:8000
uv run zensical build

# C Extension (Levenshtein distance - optional, auto-fallback to Python)
gcc -shared -o c_ext/levenshtein_distance.so -fPIC c_ext/levenshtein_distance.c  # Linux/macOS

# Screenshots & layout thumbnails
uv run python script/capture_view.py --layout-thumbnails
```

## Architecture Highlights
- **Multi-profile isolation**: Each profile = separate SQLite DB + media dir under `~/.ankiforge/profiles/<name>/`
- **Layouts & Miniatures Statiques**: 4 architectures d'interface (`ide`, `macos`, `dashboard`, `glassmorphism`) sélectionnables via une grille 2x2 de miniatures d'aperçu (`LayoutGridSelector` / `LayoutThumbnailCard`) dans `GeneralTab` avec repli gracieux, navigation clavier et accessibilité WCAG. Chaque layout dispose d'une icône Phosphor distinctive et d'une capture haute résolution régénérable via `script/capture_view.py --layout-thumbnails`
- **Document Scope & Selection Persistence**: `DocumentScopeWidget` (+ wrapper `DocumentScopeDialog`) preserves fine-grained selections (`selection_mode="sections"`, `selected_headings`, `selected_chunk_indices`) across successive generation runs in `CreationView`/`BatchView`. Its live `scope_result` also exposes an aggregated `parts` list (1 part = 1 selected branch: whole subtrees merged, parent intro fused into the first active sub-section, 1 chapter per chapter-mode selection) used by the batch composer's Direct mode
- **Exclusive Scope Modes**: `ScopeModeExclusivityMixin` (`src/ankiforge/ui/dialogs/scope_mode_exclusivity.py`) is the single activation seam shared by `DocumentScopeWidget` and `DocumentDelimitationDialog`: `activate_scope_mode()` / `ensure_scope_mode()` are the only writers of `selection_mode` once the interface is built (`__init__` fixes the initial mode from pagination detection), and the mode bar is resynced from the governing mode. Any selection-mutating interaction auto-activates its category (chapter cards, chapter range combos, section checkboxes, page sliders/spins/pills/preview) while row navigation stays navigation. `pages_card` is visible only in `pages` mode, and activating a mode re-initialises its own panel (`_reset_page_controls_to_full_span`, `_reset_sections_to_full_scope`, chapter range sync) so no other category's derived state can filter the result. Persisted `page:N` holes are page delimitations, not cross-filters, and survive reactivation. `restore_scope_mode()` is the opening seam (`_restoring_scope_mode` guard): it keeps the state persisted on `DocumentModel` (page bounds, `page:N` holes, heading exclusions) so reopening `DocumentDelimitationDialog` restores a sections delimitation instead of silently erasing it; `DocumentScopeWidget` replays its `initial_scope_result` after population and therefore keeps `activate_scope_mode()`
- **Batch Slice Composer**: single modal `BatchSliceComposerDialog` (document → mode de découpage → parties → insertion) with live updates: step 1 shows a rich document info card (fiche `doc_info_card` : type, pages, sections, ~mots/~tokens, délimitation active) + two selectable mode cards (Direct / Auto, style page d'accueil) ; step 2 = Direct → `DocumentScopeWidget` (1 partie cochée = 1 tâche, branches agrégées via `scope_result["parts"]` with backward-compatible chunk fallback) or Auto → collapsible panel `_CollapsiblePanel` « Règle de découpage » hosting the `AutoSliceWidget` above the checkbox list of generated slices (`SliceUnit`), auto-expanded on entering step 2, chunk→task fallback via `resolve_chunks`, and scope-memory prefill that never overrides live selection. `DocumentSelectWindow` / `DocumentPickerButton` share `document_meta_line(doc)` (type • pages • ~mots • ~tokens) for informed document choice
- **Provenance Multi-Blocs des Cartes Batch**: `ankiforge.services.batch.provenance` (`scope_provenance()` / `stamp_scope_provenance()`) est la **seule** écriture de la provenance de portée d'une partie : une partie mono-bloc est estampée avec sa provenance exacte (`_source_chunk_id` / `_source_heading_path` / `_source_page_number` de `BatchSourceBlock.chunk_id`), une partie à N blocs reçoit `_source_blocks` (N routes `{chunk_id, heading_path, page_number}`) et **aucun scalaire agrégé** — ni fil d'Ariane concaténé, ni page du premier bloc. `CoverageAlignmentService.resolve_finest_chunk_for_card(source_blocks=…)` possède alors trois régimes : mono-bloc exact (gagne), multi-blocs (aucun court-circuit `page_number`/`llm_section` ; recherche confinée aux fragments de la partie par `_chunks_for_routes()` puis départagée au recouvrement lexical `_best_chunk_by_lexical_overlap` — une route par page ramène *tous* les fragments de la page, jamais le premier ; une carte dont le texte n'échoque aucun fragment de sa partie reste **non rattachée** plutôt que rattachée hors partie, un faux lien de couverture étant plus trompeur que son absence), et provenance absente (délégation à `resolve_attachment`). `sync_coverage_from_tags()` remonte désormais `unlinked_notes` + `stale_documents` + `stale_skipped_notes` et journalise en `WARNING` toute note non rattachée et tout document stale (au lieu d'un `debug` silencieux) ; `BatchView._save_extracted_notes_to_db()` recompte en querying les liens des **notes qu'il vient de créer** (le rapport de sync est à l'échelle du document et compterait les orphelines d'un lot antérieur une fois par partie) dans `_batch_unlinked_cards`, affiché au récapitulatif de fin de lot (toast `warning` « N hors couverture », remis à zéro à `_on_start_batch`). `BatchView._blocks_for_direct_part()` fige une partie Direct en **un `BatchSourceBlock` par fragment source** (chunks enrichis d'un `chunk_id` par `DocumentScopeWidget._load_filtered_chunks`), avec repli sur un bloc unique pour les portées antérieures à la notion de parties
- **Multi-Document Batch Import**: `DocumentsView` accepts a multi-selection (native `QFileDialog.getOpenFileNames`) or a multi-file drag & drop (view *and* `DocumentTreeWidget.filesDropped`, extracted by the shared `local_file_paths()`), then drains the queue in a dedicated `DocumentBatchWorker` (`QThread`, extraction only — no DB write, mirroring `UrlImportWorker`). `plan_batch_tasks()` dedupes and drops missing paths while preserving the selection order; a per-document failure is logged and the queue continues (`document_failed`); a batch progress container (`batch_progress_container`: label « Importation X sur N », badge « X / N », progress bar and cancel button) provides live feedback in the left panel. Incremental tree refresh is executed at each `document_finished` (keeping selection anchored on `_batch_first_doc_id`), and any PDF in the queue immediately gets a provisional `DocumentModel` at `document_started` displaying `(analyse en cours)` during Marker OCR, before being updated upon extraction completion. Both unit and batch paths share `_persist_imported_document()` as the single write seam and `derive_document_title()` as the title-derivation seam
- **Adresses de région & exclusion non destructive (ADR 0010)**: une exclusion est une **règle de périmètre**, jamais une suppression de matière. L'identité est l'adresse (`utils/region_address.py` : `node:` contenu propre d'un titre, `heading:` le titre et sa lignée, `page:` la page exacte, sans préfixe = `heading:` par compatibilité), jamais l'`id` d'un fragment. `DocumentRepository` est l'unique décideur (`is_region_excluded`, `set_region_excluded`, `set_region_neutralized`, `is_page_outside_span`) ; les consommateurs — dialogues de délimitation et de portée, vues Documents et Batch, `CoverageAlignmentService`, réindexation, RAG — l'interrogent au lieu de rejouer des heuristiques de sous-chaîne, et les bornes de pages `start_page`/`end_page` font partie de la règle. L'écriture passe par une seule couture, `sync_extracted_chunks()`, qui apparie les fragments (empreinte puis `(titre, page)`) : ce qui n'a pas changé garde son `id` et donc ses rattachements de cartes. « Écarter » sort du périmètre, de la couverture et de la récupération ; « neutraliser » retire un conteneur du dénominateur de couverture en déclarant son origine (`ContainerOrigin.DECLARED` sur `DocumentChunkModel.container_origin`) sans rien perdre. Le RAG filtre à l'indexation **et** au moment de répondre (`VectorManager._drop_excluded_results`), et un périmètre entièrement écarté retire l'index périmé au lieu de le laisser répondre
- **Provenance par section (ADR 0009)**: l'identité durable d'une provenance est le couple (document, fil d'Ariane), jamais l'`id` d'un fragment — cet id est un artefact de découpage, détruit à chaque réingestion (24/24 tags `chunk:` pendants sur le profil dev). `build_document_tags()` n'écrit plus `chunk:` et n'écrit `page:` que si une page est un fait avéré (les PDFs/Markdown continus ne produisent donc plus de `page:1` ; les clés de section horodatées `[00:01]` sont tolérées à la lecture, retirées à l'écriture). `CoverageAlignmentService.resolve_attachment()` est l'**unique** politique de résolution, à 4 paliers `exact → section → page → lexical`, abandon sur échec seulement et jamais sur simple présence d'une autre route (un `if`/`elif` faisait d'un tag périmé une preuve de présence) ; `resolve_finest_chunk_for_card()` n'en est qu'un wrapper. Le palier gagnant est persisté sur `NoteChunkLinkModel.resolution` (colonne nullable — `NULL = lexique` serait une affirmation fausse ; cf. migration `042`) pour rendre un lien prouvé indiscernable d'un lien présumé. `sync_coverage_from_tags()` est **réparatrice** (`_canonicalize_note_provenance` + `replace_provenance_tags`) : elle corrige les profils existants sans migration de données, et remonte `repaired_notes` + `resolution_breakdown`. Une carte dont le texte n'échoe aucun fragment de sa partie reste non rattachée plutôt que rattachée hors partie. Une partie multi-blocs reste confinée à ses fragments par `_chunks_for_routes()`
- **DAG Orchestration**: 6 step types (`LLM_PROMPT`, `RAG_RETRIEVAL`, `MAP_REDUCE`, `HUMAN_VALIDATION`, `PYTHON_TOOL`, `AUDIO_TTS`), branching (`on_success_step`, `on_failure_step`), cycle/budget guards (`max_tokens_budget`, `max_step_executions`), persistent state in SQLite (`PipelineRunModel`), and resumption
- **MCP Server**: In-process, exposes tools (`query_peewee`, `get_deck_stats`, `propose_css_tune`, etc.)
- **Local RAG**: FAISS/ChromaDB vector search, semantic chunking, coverage tracking
- **Deterministic Coverage Refinement**: `CoverageAlignmentService.refine_links_to_subsections()` narrows cards attached to broad titles (H1/H2) down to the most specific descendant (H3+) they actually treat, with no LLM call: a unique literal citation of a subsection title wins outright, a card citing several subsections stays on its container, otherwise the shared idf lexical scorer (`_best_chunk_by_lexical_overlap`) elects the candidate that explains the card better than the container, and the last card of a substantive parent (>= `MIN_PARENT_CONTENT_WORDS`) is never moved. Links *and* provenance tags are rewritten in one `db.atomic()` transaction (`replace_provenance_tags` for `section:` + `chunk:`, so `sync_coverage_from_tags` cannot undo the refinement), `TableOfContentsDetector` announcements are excluded as targets, and a `CoverageSyncedEvent(scope="document")` is published only when links changed. Surfaced by the `DocumentInspectorPanel` "Affiner les liens" action, which refreshes its per-row card counts in place (single `GROUP BY`) so the selected section stays selected
- **C Extension**: `c_ext/levenshtein_distance.c` → `.so`/`.dll` for fast diff; transparent Python fallback with warning notification in `utils/c_bridge.py`
- **Navigation Coverage ➔ Éditeur**: `LinkedNoteCard` (`DocumentInspectorPanel`) rend chaque carte Anki liée cliquable (curseur pointeur, `:hover`/`:focus`, activation clic gauche ou Entrée/Espace). L'activation émet `DocumentInspectorPanel.request_navigation("edition", {"note_id": ...})`, relayé par `AISourcesDiagnosticTab` ➔ `AnalysisView` jusqu'à `MainWindow._on_view_selected()`, qui bascule sur `EditionView` et appelle `select_note_by_id(note_id)`
- **Async Logging**: `QueueHandler`/`QueueListener` pipeline, `SecretRedactionFilter` masks API keys, crash dumps to `~/.ankiforge/logs/crash.log`

## Testing Constraints (Critical)
- **All LLM calls MUST be mocked** - CI never calls real APIs (OpenAI/Ollama/Gemini)
- SQLite in-memory shared cache: `file:memdb_test_<worker>?mode=memory&cache=shared`
- `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1`, `ANKIFORGE_MOCK_WEBENGINE=1` set in conftest
- Qt widgets cleaned up after each test via `cleanup_qt_widgets` fixture
- UI tests use `pytest-qt` headless; no visual snapshots

## Code Conventions (Enforced)
- **No `print()`** - use `logging.getLogger(__name__)` with proper levels
- **Strict mypy**: `disallow_untyped_defs = true` for `ankiforge.*`; UI and migrations have relaxed overrides
- **Ruff rules**: E, F, B, I, UP, T20 (no print), PT, SIM; line-length=200
- **Pre-commit**: ruff fix/format, trailing-whitespace, yaml, large files; mypy + fast tests on pre-push
- **Type stubs**: `types-peewee`, `types-requests`, `types-markdown` in dev deps

## Key Files / Entry Points
- `src/ankiforge/__main__.py` - app entry, env setup, profile selection, migrations, plugin loading
- `src/ankiforge/database/models/` - modular Peewee models package (30 tables across ai, audit, cards, pipelines, rag, system)
- `src/ankiforge/services/ai/orchestrator.py` - `PipelineOrchestrator` DAG engine
- `src/ankiforge/services/ai/mcp_server.py` - in-process MCP server
- `src/ankiforge/ui/main_window.py` - `MainWindow` (JetBrains-style detachable panels)
- `src/ankiforge/utils/logger.py` - async logging, crash handlers, secret redaction
- `src/ankiforge/utils/paths.py` - resource paths (handles Nuitka bundles)

## CI/CD Pipeline (GitHub Actions)
- **Smart path filter** - only runs relevant jobs
- **Parallel quality**: ruff, mypy, bandit, pip-audit
- **Multi-OS test matrix**: Ubuntu/macOS/Windows with C extension compilation
- **Coverage**: serial (`-n 0`) due to Qt/WebEngine; `--cov-fail-under=70` on Linux
- **Release**: Nuitka compilation → native binaries (`.exe`, `.app`, `.AppImage`) to GitHub Releases

## Environment Variables
- `.env` (dev) or `~/.ankiforge/.env` (prod): `AI_PROVIDER`, `AI_MODEL`
- `ANKIFORGE_ENV=testing` set during pytest
- `--dev`/`--prod` CLI flags override environment

## Agent Skills Catalog (`.agents/skills/`)
Autonomous specialized skills conforming to Antigravity Progressive Disclosure:
- **Meta & Maintenance**:
  - `mise-a-jour-metadonnees`: Meta-skill: syncs the 15 metadata/doc files and audits/improves the skills catalog (maturity grid, triggers, progressive disclosure)
  - `documentation-zensical`: Proactive Zensical documentation auditor, enhancer, and build validator
  - `audit-ankiforge`: Global architecture and compliance auditor against `GEMINI.md` rules
  - `obsidian-vault`: Gestionnaire du vault Obsidian (`ankiforge_obsidian/`), Kanban (`Avancement du projet.md`) et tickets en mode atomique one-shot anti-boucle (Obsidian = todo list pure, documentation canonique dans Zensical `docs/`)
  - `proposer-commits`: Formulation de propositions de commits atomiques conformes à Conventional Commits v1.0.0 (garde-fou interdisant tout commit autonome sans accord utilisateur)
- **Architecture & Foundation**:
  - `peewee-expert`: Database schema design, migrations, atomic transactions, and N+1 query elimination
  - `ui-screenshot`: Offscreen/headless Qt view capture and visual inspection
- **Domain Pipelines**:
  - `ingestion-multimedia`: Parses PDF/DOCX/PPTX/EPUB/audio/YouTube/web into Markdown + RAG chunks (Marker OCR, media handling, chunking)
  - `export-synchro-anki`: Import/merge/export of `.apkg`/`.colpkg`, stable IDs, media dedup (MD5, zstd) and duplicate detection
- **Specialized Audits** (targeted, non-blocking):
  - `audit-dependances`: Supply chain, licenses, outdated packages, `pip-audit`
  - `audit-design-ui`: Design system token adherence, WCAG accessibility, hardcoded colors
  - `audit-donnees`: Referential integrity, cascade deletes, orphaned records
  - `audit-ia-pipeline`: DAG engine, MCP tool safety, JSON parsing robustness, token costs
  - `audit-performance`: Qt GUI responsiveness, background worker offloading, query benchmarks
  - `audit-qualite-code`: Strict typing (`mypy`), linting (`ruff`), dead code, no `print()`
  - `audit-securite`: Bandit scans, secret redaction, SSRF, sandbox safety
  - `audit-tests-ci`: Test mocking discipline, headless constraints, CI workflows
- **Agentic Engineering Flows (Matt Pocock Framework)**:
  - `ask-matt`: Interactive router and navigator for agentic engineering workflows
  - `grill-with-docs` / `grill-me` / `grilling`: Relentless interview and design tree frontier exploration
  - `to-spec` / `to-tickets`: Transformation of conversational decisions into specs and tracer-bullet tickets
  - `implement` / `tdd`: Test-driven implementation loop (red-green-refactor)
  - `code-review`: Two-axis diff review (Standards + Spec) in parallel subagents
  - `diagnosing-bugs` / `triage`: Bug isolation with tight feedback loops and Obsidian triage state machine
  - `wayfinder`: Multi-session roadmap and decision mapping for large-scale efforts
  - `domain-modeling` / `codebase-design`: Shared domain terminology (`CONTEXT.md`, ADRs) and deep module architecture
  - `improve-codebase-architecture`: Automated code scan to uncover deepening opportunities
  - `handoff` / `prototype` / `research`: Portable context compaction, throwaway code spikes, and primary source research
  - `doubt-driven-development` / `source-driven-development`: Adversarial fresh-context review and documentation-grounded decisions
  - `resolving-merge-conflicts` / `code-simplification`: Intent-based merge conflict resolution and clarity refactoring
  - `wizard` / `wait-what` / `writing-for-agents` / `to-questionnaire` / `setup-matt-pocock-skills`: Human interaction bash wizards, communication repair, agent doc standards, and questionnaire generation

## Documentation References
- `GEMINI.md` - agentic system prompt, core engineering rules
- `AGENTS.md` - quick reference guide and developer cheat-sheet
- `.github/copilot-instructions.md` - GitHub Copilot rules and reference contracts
- `.agents/skills/` - directory of 44 agent skills with progressive disclosure
- `docs/Dossier_architecture/` - 9 architecture docs (data model, UI inventory, DAG engine, quality/deploy)
- `DESIGN.md` - design system, semantic tokens, 12 themes, 4 layouts; all new widgets must be documented here

## Agent skills

### Issue tracker

Les issues/tickets vivent dans le vault Obsidian `ankiforge_obsidian/` (une note par ticket dans `Tickets/`, une ligne référencée sur le kanban `Avancement du projet.md`). Géré via le skill `obsidian-vault` en mode atomique one-shot anti-boucle (Obsidian = todo-list pure, documentation canonique dans Zensical `docs/`). Voir `docs/agents/issue-tracker.md`.

### Triage labels

Cinq rôles de triage : needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix, portés par l'en-tête `Statut` du ticket Obsidian. Voir `docs/agents/triage-labels.md`.

### Domain docs

Mono-contexte : `CONTEXT.md` à la racine + `docs/adr/`. Voir `docs/agents/domain.md`.
