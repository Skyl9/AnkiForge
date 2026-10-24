## Catalogue des Compétences Agentiques (`.agents/skills/`)

Le dépôt héberge 48 compétences agentiques autonomes conformes au standard international `agentskills.io` et au principe de divulgation progressive (Progressive Disclosure à 3 niveaux).

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
- `handoff` (`.agents/skills/handoff/SKILL.md`), `prototype` (`.agents/skills/prototype/SKILL.md`), `research` (`.agents/skills/research/SKILL.md`) : Compaction de contexte pour reprise de session, spikes jetables et investigation de sources primaires.
- `doubt-driven-development` (`.agents/skills/doubt-driven-development/SKILL.md`), `source-driven-development` (`.agents/skills/source-driven-development/SKILL.md`) : Contre-revue contradictoire en contexte neutre et ancrage dans les documentations officielles vérifiées.
- `resolving-merge-conflicts` (`.agents/skills/resolving-merge-conflicts/SKILL.md`), `code-simplification` (`.agents/skills/code-simplification/SKILL.md`) : Résolution d'intentions de fusion et simplification de clarté de code.
- `wait-what` (`.agents/skills/wait-what/SKILL.md`), `writing-for-agents` (`.agents/skills/writing-for-agents/SKILL.md`), `to-questionnaire` (`.agents/skills/to-questionnaire/SKILL.md`), `setup-forge-workflow` (`.agents/skills/setup-forge-workflow/SKILL.md`) : Réparation de compréhension, rédaction de compétences, aide au choix éclairé et initialisation de workflow.
