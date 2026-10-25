# AGENTS.md - AnkiForge Quick Reference

## Project Overview
AnkiForge: AI-assisted flashcard creation IDE for Anki ecosystem. Python 3.12+, PySide6/Qt6, SQLite/Peewee ORM, local-first architecture with MCP protocol.

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

<!-- CANONICAL:START:catalogue_skills -->
<!-- ⚠️ BLOC AUTO-GÉNÉRÉ DEPUIS .agents/instructions/catalogue_skills.md - NE PAS MODIFIER MANUELLEMENT -->

## Catalogue des Compétences Agentiques (`.agents/skills/`)

Le dépôt héberge 49 compétences agentiques autonomes conformes au standard international `agentskills.io` et au principe de divulgation progressive (Progressive Disclosure à 3 niveaux).

> [!IMPORTANT]
> **Langue de communication & restitution obligatoire** : Toutes les synthèses, explications, interactions et propositions de commits adressées à l'utilisateur doivent être rédigées en **français**, même pour les compétences dont la spécification ou les déclencheurs emploient l'anglais.

### 1. Méta & Maintenance du Dépôt
- `mise-a-jour-metadonnees` (`.agents/skills/mise-a-jour-metadonnees/SKILL.md`) : Synchronisation des 15 fichiers de documentation et métadonnées post-feature (`GEMINI.md`, `AGENTS.md`, `DESIGN.md`, `docs/Dossier_architecture/`, etc.).
- `gouvernance-skills` (`.agents/skills/gouvernance-skills/SKILL.md`) : Méta-gouverneur du parc de skills, audit statique (`auditer_coherence_skills.py`), détection des collisions Jaccard et grille de maturité 5 axes.
- `session-retrospective` (`.agents/skills/session-retrospective/SKILL.md`) : Rétrospective critique de session et auto-amélioration continue du catalogue de compétences agentiques face aux dérives et erreurs constatées.
- `documentation-zensical` (`.agents/skills/documentation-zensical/SKILL.md`) : Audit proactif, enrichissement et validation de la documentation Zensical (`uv run zensical build`).
- `audit-ankiforge` (`.agents/skills/audit-ankiforge/SKILL.md`) : Orchestration de la batterie complète d'audits et de tests du projet avec consolidation de rapport.
- `obsidian-vault` (`.agents/skills/obsidian-vault/SKILL.md`) : Gestionnaire du vault Obsidian (`ankiforge_obsidian/`), Kanban (`Avancement du projet.md`) et tickets en mode atomique one-shot anti-boucle.
- `proposer-commits` (`.agents/skills/proposer-commits/SKILL.md`) : Formulation de propositions de commits atomiques conformes à Conventional Commits v1.0.0 en français (garde-fou interdisant tout commit autonome).
- `verification-environnement` (`.agents/skills/verification-environnement/SKILL.md`) : Règles d'ingénierie préventives, interdits non négociables et exécution de la porte canonique (`script/verify.py`).
- `revue-adr` (`.agents/skills/revue-adr/SKILL.md`) : Audit du cycle de vie, consolidation des ADRs, élimination de l'obsolescence et mise à jour des redirections dans `docs/adr/`.

### 2. Socle Technique & Piliers d'Architecture
- `peewee-expert` (`.agents/skills/peewee-expert/SKILL.md`) : Modélisation Peewee ORM, intégrité référentielle, migrations SQLite et élimination des requêtes N+1.
- `ui-pyside6-design` (`.agents/skills/ui-pyside6-design/SKILL.md`) : Développement d'interfaces PySide6, dockings JetBrains, respect des tokens `DESIGN.md`, et internationalisation `tr()` (`ADR 0013`).
- `ui-screenshot` (`.agents/skills/ui-screenshot/SKILL.md`) : Capture d'écrans haute résolution en mode headless/offscreen et inspection visuelle des vues.
- `ingestion-multimedia` (`.agents/skills/ingestion-multimedia/SKILL.md`) : Parsing et extraction multimédia de sources brutes (Marker OCR, PDF, YouTube, audio, docx, epub) vers Markdown.
- `rag-smart-coverage` (`.agents/skills/rag-smart-coverage/SKILL.md`) : Découpage sémantique (`ChunkingService`), vecteurs FAISS/ChromaDB et alignement déterministe de couverture (`ADR 0009` et `ADR 0010`).
- `pipeline-dag-ia` (`.agents/skills/pipeline-dag-ia/SKILL.md`) : Moteur de DAG `PipelineOrchestrator`, 6 types d'étapes, budgets de tokens, surcharge locale `persona_override.py` et intégration MCP.
- `modeles-cartes-jinja` (`.agents/skills/modeles-cartes-jinja/SKILL.md`) : Gabarits Jinja2/HTML/CSS de types de notes Anki, directives d'occlusion et linter des 20 règles de Piotr Wozniak.
- `export-synchro-anki` (`.agents/skills/export-synchro-anki/SKILL.md`) : Import `.apkg`/`.colpkg` et export `.apkg`, synchronisation à IDs stables et déduplication des médias.

### 3. Audits Spécialisés Ciblés
- `audit-dependances` (`.agents/skills/audit-dependances/SKILL.md`) : Chaîne d'approvisionnement, vulnérabilités `pip-audit`, paquets obsolètes et licences.
- `audit-design-ui` (`.agents/skills/audit-design-ui/SKILL.md`) : Conformité au design system `DESIGN.md`, accessibilité WCAG et détection de couleurs codées en dur.
- `audit-donnees` (`.agents/skills/audit-donnees/SKILL.md`) : Intégrité référentielle Peewee, clauses CASCADE, données orphelines et couverture des migrations.
- `audit-ia-pipeline` (`.agents/skills/audit-ia-pipeline/SKILL.md`) : Robustesse du moteur DAG, sécurité des outils MCP, parsing JSON et suivi des budgets de tokens.
- `audit-performance` (`.agents/skills/audit-performance/SKILL.md`) : Réactivité de la boucle d'événements Qt, délestage en workers d'arrière-plan et profils de requêtes.
- `audit-qualite-code` (`.agents/skills/audit-qualite-code/SKILL.md`) : Typage strict `mypy`, conformité `ruff`, code mort et interdiction de `print()`.
- `audit-securite` (`.agents/skills/audit-securite/SKILL.md`) : Audit statique Bandit, masquage des secrets et sécurité de la sandbox d'exécution.
- `audit-tests-ci` (`.agents/skills/audit-tests-ci/SKILL.md`) : Discipline de mock des LLM, contraintes headless Qt et fiabilité des pipelines CI/CD.

### 4. Flux d'Ingénierie Agentique (Workflow AnkiForge)
- `ask-forge` (`.agents/skills/ask-forge/SKILL.md`) : Aiguilleur et routeur de tâches d'ingénierie articulé avec le suivi Kanban Obsidian.
- `grill-with-docs` (`.agents/skills/grill-with-docs/SKILL.md`) : Cadrage d'architecture et interview contradictoire méthodique avec exploration de frontière de décision et traçabilité CONTEXT.md / ADRs.
- `to-spec` (`.agents/skills/to-spec/SKILL.md`), `to-tickets` (`.agents/skills/to-tickets/SKILL.md`) : Formalisation de spécifications et découpage en tickets traçables dans le vault Obsidian.
- `implement` (`.agents/skills/implement/SKILL.md`), `tdd` (`.agents/skills/tdd/SKILL.md`) : Réalisation pilotée par les tests (Red-Green-Refactor) liée au cycle de vie des tickets Obsidian.
- `code-review` (`.agents/skills/code-review/SKILL.md`) : Revue de code contradictoire à deux axes (Standards du dépôt + Respect de la spécification) par sous-agents parallèles.
- `diagnosing-bugs` (`.agents/skills/diagnosing-bugs/SKILL.md`), `triage` (`.agents/skills/triage/SKILL.md`) : Diagnostic systématique d'anomalies et qualification des retours sur le Kanban.
- `wayfinder` (`.agents/skills/wayfinder/SKILL.md`) : Cartographie de feuilles de route et d'arbres décisionnels pour chantiers complexes.
- `domain-modeling` (`.agents/skills/domain-modeling/SKILL.md`), `codebase-design` (`.agents/skills/codebase-design/SKILL.md`) : Modélisation du domaine (`CONTEXT.md`, ADRs) et conception de modules profonds.
- `improve-codebase-architecture` (`.agents/skills/improve-codebase-architecture/SKILL.md`) : Analyse structurelle pour approfondir les interfaces et réduire les couplages.
- `handoff` (`.agents/skills/handoff/SKILL.md`), `prototype` (`.agents/skills/prototype/SKILL.md`) : Compaction de contexte pour reprise de session et spikes jetables.
- `research` (`.agents/skills/research/SKILL.md`) : Investigation documentaire et recherche adaptée au besoin (recherche web, sources primaires) sans interview prématurée `grill-with-docs`.
- `doubt-driven-development` (`.agents/skills/doubt-driven-development/SKILL.md`), `source-driven-development` (`.agents/skills/source-driven-development/SKILL.md`) : Contre-revue contradictoire en contexte neutre et ancrage dans les documentations officielles vérifiées.
- `resolving-merge-conflicts` (`.agents/skills/resolving-merge-conflicts/SKILL.md`), `code-simplification` (`.agents/skills/code-simplification/SKILL.md`) : Résolution d'intentions de fusion et simplification de clarté de code.
- `wait-what` (`.agents/skills/wait-what/SKILL.md`), `writing-for-agents` (`.agents/skills/writing-for-agents/SKILL.md`), `to-questionnaire` (`.agents/skills/to-questionnaire/SKILL.md`), `setup-forge-workflow` (`.agents/skills/setup-forge-workflow/SKILL.md`) : Réparation de compréhension, rédaction de compétences, aide au choix éclairé et initialisation de workflow.
<!-- CANONICAL:END:catalogue_skills -->

## Documentation References
- `GEMINI.md` - agentic system prompt, core engineering rules
- `AGENTS.md` - quick reference guide and developer cheat-sheet
- `.github/copilot-instructions.md` - GitHub Copilot rules and reference contracts
- `.agents/skills/` - directory of 50 agent skills with progressive disclosure (agentskills.io compliant)
- `docs/Dossier_architecture/` - 9 architecture docs (data model, UI inventory, DAG engine, quality/deploy)
- `DESIGN.md` - design system, semantic tokens, 12 themes, 4 layouts; all new widgets must be documented here

## Agent skills

### Issue tracker

Les issues/tickets vivent dans le vault Obsidian `ankiforge_obsidian/` (une note par ticket dans `Tickets/`, une ligne référencée sur le kanban `Avancement du projet.md`). Géré via le skill `obsidian-vault` en mode atomique one-shot anti-boucle (Obsidian = todo-list pure, documentation canonique dans Zensical `docs/`). Voir `docs/agents/issue-tracker.md`.

### Triage labels

Neuf rôles de triage : needs-triage / needs-info / ready-for-spec / ready-for-agent / ready-for-human / in-progress / ready-for-review / done / wontfix, portés par l'en-tête bivalent `Statut` (avec `Prérequis` et `Difficulté` en T-shirt sizing) de chaque ticket Obsidian. Voir `docs/agents/triage-labels.md`.

### Domain docs

Mono-contexte : `CONTEXT.md` à la racine + `docs/adr/`. Voir `docs/agents/domain.md`.
