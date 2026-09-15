# AnkiForge Copilot Instructions

## Project shape

AnkiForge is a Python 3.12+ desktop application for forging and auditing Anki
cards. It is a local-first PySide6/Qt application: daily SRS reviews remain in
the official Anki application, while AnkiForge handles document ingestion,
generation, auditing, editing, and `.apkg`/`.colpkg` import and export.

The main runtime path is:

`ankiforge.__main__` → profile selection and environment setup → Peewee/SQLite
initialization and migrations → `MainWindow` and view models → services,
repositories, and Qt workers.

The code is organized around these layers:

- `src/ankiforge/ui/`: PySide6 windows, views, widgets, dialogs, layouts,
  models, and MVVM view models. View models expose Qt signals and coordinate
  UI state; blocking work belongs outside the GUI thread.
- `src/ankiforge/services/`: application use cases and integrations. This
  includes document parsing, card import/export, RAG, AI providers, the DAG
  pipeline orchestrator, the ReAct consultant, MCP tools, plugins, and
  `QThreadPool` workers.
- `src/ankiforge/repositories/`: Peewee data-access boundaries. Use repositories
  and their transaction helpers rather than putting query logic in widgets.
- `src/ankiforge/database/`: Peewee models, migrations, backups, and seed data.
  Schema changes must be represented by a new migration.
- `src/ankiforge/utils/`: paths, environment handling, logging, rendering,
  event bus, and the C-extension bridge.
- `c_ext/` and `src/ankiforge/c_ext/`: native Levenshtein acceleration with a
  transparent Python fallback in `utils/c_bridge.py`.

The AI workflow system has two complementary paths. `PipelineOrchestrator`
executes persisted pipeline steps using a shared `PipelineRunState`; supported
step types are `LLM_PROMPT`, `RAG_RETRIEVAL`, `MAP_REDUCE`,
`HUMAN_VALIDATION`, and `PYTHON_TOOL`, with conditional success/failure
branches. `ConsultantEngine` provides the conversational ReAct path and calls
the in-process MCP registry for safe collection queries, audits, searches, and
proposals requiring human approval.

Documents are parsed and semantically chunked, indexed through FAISS/ChromaDB,
and linked back to generated notes through `DocumentChunkModel` and
`NoteChunkLinkModel`. Notes, cards, decks, note types, media, audit records,
personas, pipelines, and version history are persisted in SQLite through
Peewee.

## Setup and commands

Use `uv`; the supported runtime is Python 3.12+.

```bash
uv sync                         # runtime dependencies
uv sync --group dev             # development, build, and documentation tools
uv run ankiforge                # launch the desktop application
uv run ankiforge --help
uv run ankiforge --smoke-test   # binary/runtime smoke check
```

The test suite is configured in `pytest.ini` to use `tests/`, a 30-second
timeout, and `pytest-xdist` parallelism by default. Qt tests are headless and
the test fixtures replace the application database with a per-worker shared
in-memory SQLite database.

```bash
uv run pytest
uv run pytest tests/services/ai/test_dag_orchestrator.py
uv run pytest tests/ui/test_main_window.py -k profile
uv run pytest -m "not slow"
uv run pytest --cov=ankiforge --cov-report=term-missing
```

For local Qt/WebEngine behavior, use the same environment as CI:

```bash
QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_DISABLE_SANDBOX=1 \
ANKIFORGE_MOCK_WEBENGINE=1 \
uv run pytest tests/ui/test_card_validation_and_rendering.py
```

Quality commands:

```bash
uv run ruff check src/ tests/
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
uv run ruff format --check .
uv run mypy src/ankiforge
uv run bandit -c pyproject.toml -r src/
pre-commit run --all-files
```

Documentation is built with Zensical (with MkDocs as the CI fallback):

```bash
uv run zensical serve
uv run zensical build
```

The native extension is optional during development because the Python bridge
falls back automatically. On macOS/Linux it can be compiled with:

```bash
gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC \
  src/ankiforge/c_ext/levenshtein_distance.c
```

Production builds are driven by the scripts in `build_script/` and use Nuitka;
the GitHub workflows build Linux, macOS, and Windows artifacts.

## Repository-specific conventions

### Database and profiles

- `ProfileManager` switches the active Peewee database before application
  services are used. Profile data is isolated under the application data
  directory, with one SQLite database and media directory per profile.
- Application startup runs `init_db()`, backups, migrations, and seed data.
  Preserve this order when changing startup or profile switching.
- Tests must not use the real user database. Follow the existing `tests/conftest.py`
  pattern and bind all relevant models to the worker-specific in-memory DB.
- Use `BaseRepository.atomic()` or the repository’s transaction boundary for
  multi-write operations.
- Import/sync behavior is content-first: note field content changes can require
  Smart Merge, while deck moves and review metadata are merged silently.

### Qt, workers, and state

- Keep the GUI thread responsive. Parsing, network/LLM calls, vector search,
  expensive SQL, imports/exports, and other work that can exceed roughly 50 ms
  belong in a service worker or `QThreadPool` task.
- Communicate worker results and failures through Qt signals/slots. View models
  are the reactive boundary between services and widgets and should expose
  `busy_changed`, `error_occurred`, and user-facing messages consistently.
- Do not instantiate real external LLMs, Ollama, embeddings, or paid APIs in
  tests. Mock provider responses and retrievers deterministically.
- For new pipeline behavior, preserve `PipelineRunState` serialization and
  explicit pause/resume behavior for `HUMAN_VALIDATION`.

### UI and design system

- Read `DESIGN.md` before adding or substantially changing a widget, view, or
  layout. Register a new component type there and use `DesignTokens`/the
  centralized `StyleEngine`; do not hard-code colors or ad hoc QSS in widgets.
- Read `docs/Dossier_architecture/07_inventaire_composants_ui.md` before
  designing a new UI component, and consult the relevant feature document
  under `docs/features/`.
- Keep HTML mockups and Qt components in parity. HTML components in `maquette/`
  require the project’s Qt-equivalence annotation and should remain translatable
  to native PySide6 widgets.
- Preserve the existing native Qt approach for note editing, KaTeX, Cloze,
  card preview, Smart Merge, and WebEngine previews.

### Logging, errors, and security

- Do not add `print()` to application code. Use
  `logging.getLogger(__name__)` and the asynchronous QueueHandler/QueueListener
  pipeline configured by `ankiforge.utils.logger`.
- Use log levels consistently: `DEBUG` for diagnostics, `INFO` for lifecycle
  and completed jobs, `WARNING` for recoverable fallbacks, `ERROR` for failed
  user operations, and `CRITICAL` for unrecoverable corruption.
- Do not log API keys, bearer tokens, passwords, or PII. The logging filters
  redact secrets, but callers must still avoid placing sensitive values in
  messages.
- Surface user-facing failures through the existing error/event/toast patterns;
  do not swallow exceptions with broad silent fallbacks.

### AI, data ingestion, and native fallbacks

- Keep provider-specific code behind the existing flexible AI service
  abstractions. Record token usage and cost through the existing pricing and
  `TokenUsageModel` path.
- Preserve local-first behavior: Ollama is accessed as an external local
  service, while cloud providers are optional integrations.
- Preserve source traceability from parsed documents through chunks, vector
  retrieval, generated notes, and coverage analysis.
- Any native optimization must have a tested pure-Python fallback and must not
  make the application unusable when a platform-specific shared library is
  unavailable.

### Production stability

AnkiForge is already used as a production application. Treat existing behavior
as a compatibility contract, not as disposable or experimental code.

- Make surgical, backward-compatible changes. Do not remove, rename, or alter
  existing public behavior, persisted data formats, CLI flags, database
  semantics, import/export behavior, UI workflows, or extension fallbacks
  unless the change is explicitly required and its migration path is defined.
- Before editing shared services, models, migrations, startup, profile
  switching, workers, or common widgets, trace their callers and preserve
  behavior for existing features and profiles.
- Do not rewrite stable subsystems merely to simplify a change. Prefer the
  smallest complete change and reuse existing abstractions and patterns.
- Protect existing user data: never bypass backups, migrations, transaction
  boundaries, profile isolation, or Smart Merge rules. New schema changes must
  be additive and migratable.
- Validate the affected behavior with targeted tests, then run the broader
  relevant checks before considering the change complete. A change is not
  complete if it only works for the new path while regressing an existing one.

## Reference documents

Read only the documents relevant to the change, but treat these as the
authoritative project references:

- `GEMINI.md`: agent workflow and repository-wide architecture rules.
- `DESIGN.md`: UI tokens, themes, layouts, and component registration.
- `docs/Dossier_architecture/`: architecture, data model, AI services,
  orchestration, UI inventory, and deployment standards.
- `docs/dev/standards_et_qualite.md` and `docs/dev/tests_et_cicd.md`: quality,
  testing, and CI expectations.
- `docs/features/`: behavior contracts for major product areas.
