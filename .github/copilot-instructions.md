# AnkiForge Copilot Instructions

## Project shape

AnkiForge is a Python 3.12+ desktop application for forging and auditing Anki
cards. It is a local-first PySide6/Qt application: daily SRS reviews remain in
the official Anki application, while AnkiForge handles document ingestion,
generation, auditing, editing, and `.apkg`/`.colpkg` import with `.apkg` export.

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

<!-- CANONICAL:START:commandes -->
<!-- ⚠️ BLOC AUTO-GÉNÉRÉ DEPUIS .agents/instructions/commandes.md - NE PAS MODIFIER MANUELLEMENT -->

## Commandes Canoniques & Cycle de Vie

Toutes les opérations d'ingénierie s'exécutent via l'environnement virtuel géré par `uv` (Python 3.12+).

### Installation des Dépendances
```bash
uv sync                         # dépendances d'exécution standard
uv sync --group dev             # dépendances de développement, tests, linters et documentation
```

### Lancement de l'Application
```bash
uv run ankiforge                # environnement de profil par défaut
uv run ankiforge --dev          # environnement isolé de développement (~/.ankiforge-dev)
uv run ankiforge --prod         # forcer l'environnement de production (~/.ankiforge)
uv run ankiforge --smoke-test   # vérification d'intégrité binaire et de démarrage sans interface
uv run ankiforge --clone-prod-to-dev # synchroniser la base prod vers dev pour investigation
```

### Exécution des Tests
```bash
uv run pytest                   # suite complète de tests (headless Qt via pytest-qt)
uv run pytest -m "not slow"     # suite rapide pré-push (< 15s)
uv run pytest -m unit           # tests unitaires purs et algorithmiques (< 2s, sans base ni Qt)
uv run pytest -m integration    # tests d'intégration base de données Peewee et services
uv run pytest -m ui             # tests headless PySide6 (widgets, signaux, formulaires)
uv run pytest tests/path/test_file.py::TestClass::test_method
```

### Porte de Vérification Canonique Unique (Verification Gate)
La commande canonique unique `script/verify.py` applique séquentiellement l'ensemble des garde-fous de qualité avant tout push :
```bash
uv run python script/verify.py              # chaîne canonique : drift, ruff, format, mypy, bandit, pytest fast
uv run python script/verify.py --fix        # auto-correction (instructions, formatage et fix ruff) avant contrôle
uv run python script/verify.py --all-tests  # exécution avec la totalité des tests (sans filtre slow)
uv run python script/verify.py --install-hook # installe et active le hook natif versionné .githooks/pre-push
```

### Gouvernance des Compétences Agentiques & Métadonnées
```bash
uv run python .agents/skills/gouvernance-skills/scripts/auditer_coherence_skills.py # audit statique des 50 skills
```

### Documentation Zensical
```bash
uv run zensical serve           # serveur de documentation local live (http://127.0.0.1:8000)
uv run zensical build           # compilation statique du site documentaire dans site/
```

### Extension C Native (Levenshtein)
```bash
gcc -shared -o c_ext/levenshtein_distance.so -fPIC c_ext/levenshtein_distance.c  # Linux/macOS
```

### Captures & Miniatures de Layouts
```bash
uv run python script/capture_view.py --layout-thumbnails # régénère les miniatures haute résolution
```
<!-- CANONICAL:END:commandes -->

<!-- CANONICAL:START:regles_ingenierie -->
<!-- ⚠️ BLOC AUTO-GÉNÉRÉ DEPUIS .agents/instructions/regles_ingenierie.md - NE PAS MODIFIER MANUELLEMENT -->

## Règles d'Ingénierie & Conventions Non Négociables

### 1. Langue de Communication & Restitution Obligatoire
Toutes les synthèses, explications, interactions, documentations et propositions de commits adressées à l'utilisateur doivent être rédigées en **français**, y compris lors de l'exécution de compétences dont la spécification ou les déclencheurs emploient l'anglais.

### 2. Typage Statique Strict 100% (`mypy`)
- Tout le code du projet sous `src/ankiforge/` respecte le typage strict (`disallow_untyped_defs = true`).
- Interdiction formelle d'ajouter des règles globales `disable_error_code` masquant les erreurs de typage.
- Utiliser systématiquement les types stubs (`types-peewee`, `types-requests`, `types-markdown`) et la syntaxe moderne Python 3.12+ (unions `X | Y`, génériques PEP 695).

### 3. Logging Asynchrone & Interdiction Absolue de `print()`
- **Zéro `print()`** : application stricte de la règle Ruff `T20`. Utiliser systématiquement `logger = logging.getLogger(__name__)` avec le niveau sémantique approprié (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- **Haute performance non bloquante** : tous les logs transitent par le pipeline asynchrone `QueueHandler` / `QueueListener` défini dans `ankiforge.utils.logger`.
- **Sanitisation des secrets** : le filtre `SecretRedactionFilter` masque automatiquement les clés d'API (`sk-*`, `AIza*`), en-têtes `Bearer` et jetons avant toute écriture sur disque.

### 4. Tests Headless Qt & Isolation
- **Headless obligatoire** : les tests s'exécutent avec `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1` et `ANKIFORGE_MOCK_WEBENGINE=1`.
- **Zéro snapshot visuel** : tester la logique métier, les signaux, les slots et le cycle de vie des formulaires via `pytest-qt` (`qtbot`), jamais de capture d'image en assertion.
- **Isolation mémoire** : la base de données de test est une SQLite en mémoire partagée (`file:memdb_test_<worker>?mode=memory&cache=shared`).
- **Nettoyage strict** : chaque widget Qt créé dans un test doit être nettoyé via la fixture `cleanup_qt_widgets`.

### 5. Mocks LLM & RAG Obligatoires
Tous les appels aux fournisseurs d'IA (OpenAI, Gemini, Anthropic, Ollama), embeddings et retriéveurs vectoriels doivent être **intégralement mockés de manière déterministe** durant les tests. Zéro appel réseau payant ou dépendance à un démon local en CI.

### 6. Discipline Git & Interdiction de Commit Autonome
L'agent ne doit **JAMAIS** exécuter de `git commit` ou `git push` de manière autonome sans l'accord explicite préalable de l'utilisateur. À l'achèvement d'une tâche modifiant l'arbre de travail, invoquer la compétence `proposer-commits` pour formuler des propositions atomiques conformes à Conventional Commits v1.0.0 en français.

### 7. Internationalisation Qt Linguist (`ADR 0013`)
- Toute chaîne affichée à l'utilisateur passe par `self.tr("…")` (sous-classe de `QObject`) ou `tr("…")` (ailleurs).
- Langue source et repli : **français** (`SOURCE_LANGUAGE = "fr"`). Un catalogue absent ou vide ne doit jamais empêcher le démarrage de l'application.
- **`tr(f"…")` est strictement interdit** : la f-chaîne étant évaluée avant l'appel, le message n'entre pas au catalogue.
- Marqueurs de position Qt Linguist : utiliser `tr("Enregistré : %1/%2", faits, total)`. `self.tr()` ne réalisant pas de substitution (son second paramètre étant réservé à la désambiguïsation), tout message paramétré emploie `tr()`.
- Zéro `tr()` au chargement de module : les libellés traduits ne doivent pas être figés dans des constantes globales avant l'appel d'`install_translator()`.

### 8. Respect du Design System (`DESIGN.md`)
- `DESIGN.md` est la source unique de vérité pour les 12 familles de thèmes et les 4 dispositions d'interface (layouts).
- Zéro couleur en dur dans le code : toutes les teintes et métriques dérivent des jetons sémantiques `DesignTokens` / `ThemeProfile` injectés par `StyleEngine.generate_stylesheet()`.

### 9. Prise en Charge des Tickets de Recherche (Interdiction de `/grill-with-docs` Prématuré)
- **Interdiction formelle** : Lorsqu'un ticket ou une tâche affiche « rechercher » (ou relève d'une investigation, d'un état de l'art ou d'un benchmark), il est formellement interdit de déclencher un `/grill-with-docs` d'emblée. Une interview d'architecture ou un interrogatoire de cadrage est inutile et contre-productif tant que la matière documentaire n'a pas été rassemblée.
- **Clarification préalable** : L'agent doit d'abord demander explicitement à l'utilisateur le sujet précis de la recherche, ses attentes et le périmètre d'investigation souhaité.
- **Recherche web & apport documentaire** : Effectuer les recherches documentaires nécessaires (notamment via la recherche sur le web et l'exploration des documentations officielles et sources primaires), puis adapter et structurer la documentation existante directement en réponse ciblée aux besoins de l'utilisateur et aux contraintes d'AnkiForge.
- **Orientation aval conditionnelle** : Ce n'est qu'une fois la documentation existante amenée, synthétisée et validée avec l'utilisateur qu'il convient d'orienter la suite (ex. arbitrage d'architecture via `/grill-with-docs`, spécification via `/to-spec`, ou spike via `/prototype`).
<!-- CANONICAL:END:regles_ingenierie -->

<!-- CANONICAL:START:architecture_points_cles -->
<!-- ⚠️ BLOC AUTO-GÉNÉRÉ DEPUIS .agents/instructions/architecture_points_cles.md - NE PAS MODIFIER MANUELLEMENT -->

## Points Clés d'Architecture Technique

- **Multi-profils & Isolation stricte** : Chaque profil utilisateur possède sa propre base SQLite (`~/.ankiforge/profiles/<nom>/ankiforge.db`) et son dossier de médias dédié. Le verrou de profil (`ProfileManager`) garantit l'exclusivité d'accès mono-instance par profil tout en autorisant le multi-processus sur des profils disjoints.
- **Dispositions d'interface (4 Layouts) & Miniatures** : 4 architectures interchangeables à chaud (`ide`, `macos`, `dashboard`, `glassmorphism`) sélectionnables via une grille 2x2 de miniatures d'aperçu haute résolution (`LayoutGridSelector` / `LayoutThumbnailCard`).
- **Délimitation & Modes de portée exclusifs** : `ScopeModeExclusivityMixin` (`src/ankiforge/ui/dialogs/scope_mode_exclusivity.py`) constitue la couture unique gouvernant les modes de sélection documentaire (`sections`, `pages`, `chapitres`). `activate_scope_mode()` et `restore_scope_mode()` préservent fidèlement les sélections et délimitations utilisateur.
- **Composition de lots (Batch Slice Composer)** : Dialogue modal unique `BatchSliceComposerDialog` permettant le découpage documentaire en mode Direct (`DocumentScopeWidget`, 1 partie cochée = 1 tâche) ou Auto (`AutoSliceWidget` avec règles de découpage paramétrables).
- **Adresses de région & Exclusion non destructive (`ADR 0010`)** : Une exclusion est une règle de périmètre (`utils/region_address.py` : `node:`, `heading:`, `page:`), jamais une suppression physique. `DocumentRepository` est l'unique décideur (`is_region_excluded`, `set_region_excluded`, `set_region_neutralized`). Écarter sort du périmètre de calcul et de génération ; neutraliser retire un conteneur du dénominateur de couverture (`ContainerOrigin.DECLARED`).
- **Provenance par section & Paliers de résolution (`ADR 0009`)** : L'identité durable d'une source est le couple (document, fil d'Ariane `heading_path`), jamais l'identifiant éphémère d'un fragment textuel. `CoverageAlignmentService.resolve_attachment()` applique la résolution déterministe à 4 paliers (`exact → section → page → lexical`). Le palier gagnant est persisté sur `NoteChunkLinkModel.resolution`.
- **Moteur d'Orchestration DAG IA** : `PipelineOrchestrator` exécute des graphes dirigés acycliques supportant 6 types d'étapes (`LLM_PROMPT`, `RAG_RETRIEVAL`, `MAP_REDUCE`, `HUMAN_VALIDATION`, `PYTHON_TOOL`, `AUDIO_TTS`), des branchements conditionnels (`on_success_step`, `on_failure_step`), des budgets de tokens stricts et la persistance SQLite (`PipelineRunModel`) avec reprise interactive sur incident.
- **Surcharge locale de persona par étape (`persona_override.py`)** : Couture unique de surcharge de prompt au profit d'un pipeline sans altérer la persona globale. Résolution selon l'ordre strict `surcharge figée → agent de l'étape → défaut du fournisseur`, avec empreinte SHA-256 et horodatage de dérive.
- **Serveur MCP Persistant In-Process & Priorité Externe (`ADR 0034`)** : Serveur MCP autonome intégré (`mcp_server.py`) exposant l'outillage de consultation, d'audit et de mutation à des agents externes via le protocole standardisé, avec validation humaine systématique en deux phases (Two-Phase Commit / patches intermédiaires).
- **RAG Local & Indexation Vectorielle** : Recherche sémantique déterministe FAISS/ChromaDB couplée à un suivi de couverture granulaire sans dépendance cloud obligatoire.
- **Extension C Native & Repli Transparent** : Calcul de distance de Levenshtein accéléré par bibliothèque C compilée (`c_ext/levenshtein_distance.so` / `.dll`), avec repli Python transparent et notification dans `utils/c_bridge.py`.
- **Adaptateurs d'instructions unifiés (`ADR 0016`)** : Source unique de vérité sous `.agents/instructions/` injectée dans les adaptateurs agents (`GEMINI.md`, `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`) avec vérification déterministe fail-fast dans la porte `script/verify.py`.
<!-- CANONICAL:END:architecture_points_cles -->

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
- `AGENTS.md`: developer and AI agent quick reference guide, CLI commands, and test conventions.
- `.agents/skills/`: project agent skills catalog (audits, Peewee, UI inspection, metadata sync, and skill optimization).
- `DESIGN.md`: UI tokens, themes, layouts, and component registration.
- `docs/Dossier_architecture/`: architecture, data model, AI services,
  orchestration, UI inventory, and deployment standards.
- `docs/dev/standards_et_qualite.md` and `docs/dev/tests_et_cicd.md`: quality,
  testing, and CI expectations.
- `docs/features/`: behavior contracts for major product areas.
