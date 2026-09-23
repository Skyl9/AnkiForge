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
uv run pytest                   # all 1245+ tests (headless Qt via pytest-qt)
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
```

## Architecture Highlights
- **Multi-profile isolation**: Each profile = separate SQLite DB + media dir under `~/.ankiforge/profiles/<name>/`
- **Document Scope & Selection Persistence**: `DocumentScopeWidget` (+ wrapper `DocumentScopeDialog`) preserves fine-grained selections (`selection_mode="sections"`, `selected_headings`, `selected_chunk_indices`) across successive generation runs in `CreationView`/`BatchView`. Its live `scope_result` also exposes an aggregated `parts` list (1 part = 1 selected branch: whole subtrees merged, parent intro fused into the first active sub-section, 1 chapter per chapter-mode selection) used by the batch composer's Direct mode
- **Batch Slice Composer**: single modal `BatchSliceComposerDialog` (document → mode de découpage → parties → insertion) with live updates: step 1 shows a rich document info card (fiche `doc_info_card` : type, pages, sections, ~mots/~tokens, délimitation active) + two selectable mode cards (Direct / Auto, style page d'accueil) ; step 2 = Direct → `DocumentScopeWidget` (1 partie cochée = 1 tâche, branches agrégées via `scope_result["parts"]` with backward-compatible chunk fallback) or Auto → collapsible panel `_CollapsiblePanel` « Règle de découpage » hosting the `AutoSliceWidget` above the checkbox list of generated slices (`SliceUnit`), auto-expanded on entering step 2, chunk→task fallback via `resolve_chunks`, and scope-memory prefill that never overrides live selection. `DocumentSelectWindow` / `DocumentPickerButton` share `document_meta_line(doc)` (type • pages • ~mots • ~tokens) for informed document choice
- **DAG Orchestration**: 6 step types (`LLM_PROMPT`, `RAG_RETRIEVAL`, `MAP_REDUCE`, `HUMAN_VALIDATION`, `PYTHON_TOOL`, `AUDIO_TTS`), branching (`on_success_step`, `on_failure_step`), cycle/budget guards (`max_tokens_budget`, `max_step_executions`), persistent state in SQLite (`PipelineRunModel`), and resumption
- **MCP Server**: In-process, exposes tools (`query_peewee`, `get_deck_stats`, `propose_css_tune`, etc.)
- **Local RAG**: FAISS/ChromaDB vector search, semantic chunking, coverage tracking
- **C Extension**: `c_ext/levenshtein_distance.c` → `.so`/`.dll` for fast diff; transparent Python fallback in `utils/c_bridge.py`
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

## Documentation References
- `GEMINI.md` - agentic system prompt, core engineering rules
- `AGENTS.md` - quick reference guide and developer cheat-sheet
- `.github/copilot-instructions.md` - GitHub Copilot rules and reference contracts
- `.agents/skills/` - directory of 15 agent skills with progressive disclosure
- `docs/Dossier_architecture/` - 9 architecture docs (data model, UI inventory, DAG engine, quality/deploy)
- `DESIGN.md` - design system, semantic tokens, 12 themes, 4 layouts; all new widgets must be documented here

## Agent skills

### Issue tracker

Les issues/tickets vivent dans le vault Obsidian `ankiforge_obsidian/` (une note par ticket dans `Tickets/`, une ligne référencée sur le kanban `Avancement du projet.md`). Voir `docs/agents/issue-tracker.md`.

### Triage labels

Cinq rôles de triage : needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix, portés par l'en-tête `Statut` du ticket Obsidian. Voir `docs/agents/triage-labels.md`.

### Domain docs

Mono-contexte : `CONTEXT.md` à la racine + `docs/adr/`. Voir `docs/agents/domain.md`.
