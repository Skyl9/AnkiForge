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
uv run pytest                   # all 146+ tests (headless Qt via pytest-qt)
uv run pytest -k "not slow"     # fast unit tests only (pre-push)
uv run pytest tests/path/test_file.py::TestClass::test_method

# Quality checks (run in order before push)
uv run ruff check --fix .
uv run ruff format --check .
uv run mypy src/ankiforge       # strict 100% typing required
uv run bandit -c pyproject.toml -r src/

# Documentation
uv run zensical serve           # live at http://127.0.0.1:8000
uv run zensical build

# C Extension (Levenshtein distance - optional, auto-fallback to Python)
gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC src/ankiforge/c_ext/levenshtein_distance.c  # Linux/macOS
```

## Architecture Highlights
- **Multi-profile isolation**: Each profile = separate SQLite DB + media dir under `~/.ankiforge/profiles/<name>/`
- **DAG Orchestration**: 5 step types (`LLM_PROMPT`, `RAG_RETRIEVAL`, `MAP_REDUCE`, `HUMAN_VALIDATION`, `PYTHON_TOOL`) with conditional jumps
- **MCP Server**: In-process, exposes tools (`query_peewee`, `get_deck_stats`, `update_card_model_css`, etc.)
- **Local RAG**: FAISS/ChromaDB vector search, semantic chunking, coverage tracking
- **C Extension**: `src/ankiforge/c_ext/levenshtein_distance.c` → `.so`/`.dll` for fast diff; transparent Python fallback in `utils/c_bridge.py`
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
- `src/ankiforge/database/models.py` - all Peewee models (30+ tables)
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

## Documentation References
- `GEMINI.md` - agentic system prompt, core engineering rules
- `docs/Dossier_architecture/` - 9 architecture docs (data model, UI inventory, DAG engine, quality/deploy)
- `DESIGN.md` - design system, semantic tokens, 12 themes, 4 layouts; all new widgets must be documented here
