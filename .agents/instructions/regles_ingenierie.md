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
