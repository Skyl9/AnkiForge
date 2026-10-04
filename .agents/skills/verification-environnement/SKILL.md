---
name: verification-environnement
description: >
  Guide préventif des règles d'ingénierie et de codage pour les agents opérant dans AnkiForge. Énonce les interdits structurels non négociables (annotations complètes, logging sans print, Qt offscreen, exclusion des emojis, isolation des tests LLM) et détaille l'exécution de la porte canonique verify.py.
  Use when preparing code changes, implementing new features or bugfixes, starting a coding task, checking environment constraints, or when asked to "règles d'écriture", "règles de dev", "conventions agent", "non négociables", "vérifier environnement", or "règles projet".
---

# 🛡️ Règles d'Ingénierie & Vérification par Environnement — AnkiForge

En tant qu'**Agent de Développement opérant dans le dépôt AnkiForge**, ton rôle est d'assimiler les règles non négociables d'écriture et de conformité logicielle avant de coder, et d'exécuter la porte de vérification canonique à la fin de tes modifications.

## 1. Principes Directeurs : La Prière et la Contrainte

- **Le skill est une prière, le hook est une contrainte** : ce skill n'interdit rien par caprice ; il explicite le *pourquoi* technique de chaque règle.
- **Ne pas dupliquer la contrainte** : le contrôle automatique est garanti par le hook git pre-push natif (`.githooks/pre-push`) et le script canonique `script/verify.py`. Ce skill te préserve de brûler un cycle d'itération sur un interdit déjà écrit.

## 2. Règles Non Négociables d'Écriture (Le Pourquoi)

1. **Typage statique strict (`disallow_untyped_defs = true`)** :
   - *Pourquoi* : Fiabilité du refactoring et sécurité d'exécution sur tout `ankiforge.*`. Utiliser la syntaxe moderne Python 3.12+ (unions `X | Y`, generics PEP 695). Zéro `type: ignore` non justifié, interdiction absolue des `disable_error_code` globaux masquant les erreurs. Seuls `ui.*` et `database.migrations.*` bénéficient d'overrides ciblés dans `pyproject.toml`.
   - *Garantie automatique* : Mypy strict (`uv run mypy src/ankiforge`), étape 3 de `verify.py`.

2. **Interdiction formelle de `print()` (Règle T20)** :
   - *Pourquoi* : Haute performance sans I/O bloquante grâce au pipeline asynchrone `QueueHandler`/`QueueListener` via `logger = logging.getLogger(__name__)`. Le filtre `SecretRedactionFilter` anonymise automatiquement clés d'API (`sk-*`, `AIza*`), en-têtes et tokens. Un appel à `print()` court-circuite cette sécurité vitale et ralentit l'exécution.
   - *Garantie automatique* : Ruff règle T20 (`uv run ruff check .`), étape 1 de `verify.py`.

3. **Exécution Qt headless (`QT_QPA_PLATFORM=offscreen`)** :
   - *Pourquoi* : Les environnements de test, de CI et d'agents opèrent sans serveur graphique X11/Wayland. Tout widget instancié doit fonctionner en mode headless (`QT_QPA_PLATFORM=offscreen`, `ANKIFORGE_MOCK_WEBENGINE=1`), sans dialogue bloquant, et être systématiquement nettoyé via la fixture `cleanup_qt_widgets` ou `qtbot`.
   - *Garantie automatique* : `conftest.py` + pytest-qt headless, étape 5 de `verify.py`.

4. **Zéro emoji dans le code source** :
   - *Pourquoi* : Préserver la pureté UTF-8, éliminer les risques d'encodage multi-OS (Linux, Windows, macOS) et assurer la rigueur technique dans les noms de variables, fonctions, chaînes internes et logs applicatifs. Les emojis sont réservés aux interfaces graphiques explicites et au Kanban Obsidian.
   - *Garantie automatique* : Contrôle de style Ruff et revues.

5. **Mocks obligatoires pour tout appel LLM & Réseau** :
   - *Pourquoi* : Les tests doivent être déterministes, ultra-rapides (< 15s en fast) et autonomes. Aucun appel réel externe vers des API payantes ou locales (OpenAI, Gemini, Anthropic, Ollama) n'est toléré en test. Les fixtures pytest mockent systématiquement les réponses.
   - *Garantie automatique* : `ANKIFORGE_ENV=testing` + suite de tests mockés.

6. **Conventions d'arborescence et anglais technique** :
   - *Pourquoi* : L'architecture interne s'organise exclusivement en anglais technique (`src/ankiforge/utils/`, `services/`, etc.). L'usage de répertoires francisés alternatifs (ex. `ressources/` au lieu de `utils/`) est banni pour éliminer les divergences d'import constatées dans `initial_seed.py`.

## 3. Commande Canonique Unique de Vérification

Toute modification de code doit impérativement être validée via la porte canonique unique :

```bash
uv run python script/verify.py              # vérification complète rapide (< 30s)
uv run python script/verify.py --fix        # auto-correction ruff avant vérification
uv run python script/verify.py --all-tests  # vérification avec suite complète
```

### Méthodes d'exécution par environnement d'agent

- **Antigravity / Gemini CLI** : Invoquer l'outil `run_command` avec `CommandLine: "uv run python script/verify.py"` et `Cwd` sur le workspace.
- **Claude Code** : Invoquer l'outil `Bash` avec `uv run python script/verify.py`.
- **Terminal & Scripts** : Exécuter la commande directement dans le shell.

### Le hook pre-push versionné

Situé dans `.githooks/pre-push`, il s'exécute automatiquement avant tout `git push`. En cas d'échec d'une seule étape de `script/verify.py`, le push est rejeté.

## ⛔ Ne PAS utiliser ce skill si...

- Tu souhaites auditer la conformité globale ou produire un rapport formel sous `audits/` : utiliser `audit-qualite-code`, `audit-tests-ci` ou `audit-ankiforge`.
- Tu prépares des propositions de commits atomiques à la fin d'une tâche : utiliser `proposer-commits`.
- Tu travailles spécifiquement sur le modèle de données Peewee ou une migration SQLite : utiliser `peewee-expert`.
