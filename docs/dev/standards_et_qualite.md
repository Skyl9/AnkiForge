# Standards de Code & Typage Strict 🛡️

Le développement d'AnkiForge obéit à des standards de qualité logicielle de niveau industriel, formalisés dans `GEMINI.md`. Tout contributeur ou agent intervenant sur le projet est tenu de respecter scrupuleusement ces règles.

---

## 🎯 1. Typage Statique Strict 100% (`mypy`)

Le projet impose le typage statique strict sur l'intégralité du code source (`src/ankiforge`) :
- **Configuration** : `disallow_untyped_defs = true`, `disallow_incomplete_defs = true`, `check_untyped_defs = true`.
- **Zéro exception globale** : Il est strictement interdit d'ajouter des règles `disable_error_code` globales masquant les erreurs de typage.
- **Python 3.12+ Moderne** : Utilisation des syntaxes modernes, notamment les unions natives `X | Y` (au lieu de `Optional[X]` ou `Union[X, Y]`) et les génériques PEP 695.
- **Stubs de Types** : Utilisation des packages de stubs officiels (`types-peewee`, `types-requests`, `types-markdown`).

Pour vérifier la conformité du typage :
```bash
uv run mypy src/ankiforge
```

---

## 🧹 2. Linting & Formatage Automatisé (`ruff`)

L'outillage de linting s'appuie sur **Ruff** pour une rapidité et une rigueur maximales. Le jeu de règles actif comprend :
- `E`, `F` : Erreurs et avertissements standards flake8.
- `B` (Bugbear) : Détection proactive des pièges courants et bugs subtils.
- `I` (isort) : Tri automatique et déterministe des imports.
- `UP` (pyupgrade) : Modernisation automatique du code vers les idiomes Python 3.12+.
- `T20` : **Interdiction absolue de l'instruction `print()`**.
- `PT` (flake8-pytest-style) : Bonnes pratiques d'écriture de tests.
- `SIM` (flake8-simplify) : Simplification du code et refactorisation idiomatique.

Pour lancer le linter et formater le code :
```bash
# Vérification
uv run ruff check src/ tests/

# Correction automatique
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

---

## 🪵 3. Politique de Logging Asynchrone & Sécurisé

Conformément à la règle 19 de `GEMINI.md`, aucun appel à `print()` n'est toléré dans l'application.

### Pipeline Non-Bloquant (`QueueHandler` / `QueueListener`)
Tous les logs émis via `logger = logging.getLogger(__name__)` transitent par une file d'attente mémoire en arrière-plan (`QueueHandler`). Le thread d'interface graphique (Main Thread) n'effectue ainsi **aucun I/O disque bloquant**, garantissant une fluidité absolue à 60+ images par seconde.

### Masquage Strict des Secrets (`SecretRedactionFilter`)
Le filtre de sanitisation intercepte tous les messages avant écriture disque et masque automatiquement :
- Les clés d'API OpenAI (`sk-proj-...`, `sk-...`)
- Les clés d'API Google Gemini (`AIzaSy...`)
- Les clés Anthropic (`sk-ant-...`)
- Les en-têtes d'autorisation HTTP (`Bearer ...`) et mots de passe.

### Rétention et Gestion des Crashes
- **Rotation** : Les fichiers journaux sont stockés dans `~/.ankiforge/logs/ankiforge.log` avec une limite stricte de 50 Mo (5 fichiers de 10 Mo en roulement).
- **Crash Dumps** : `install_crash_handlers()` capture les exceptions non interceptées (`sys.excepthook` et `threading.excepthook`) et génère un rapport technique anonymisé dans `~/.ankiforge/logs/crash.log`.
