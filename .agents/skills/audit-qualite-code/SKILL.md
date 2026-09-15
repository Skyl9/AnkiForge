---
name: audit-qualite-code
description: Audit de la qualité du code et de la conformité aux standards GEMINI.md règle 20 d'AnkiForge. Use when the user asks to "audit qualité", "audit code", "ruff", "mypy", "typage strict", "print()", "List/Dict/Tuple typing", "conformité GEMINI règle 20" or "qualité avant push". Runs ruff, mypy and grep checks and produces a report under audits/.
---

# Audit Qualité du Code AnkiForge

En tant qu'**Auditeur Qualité & Typage Strict**, tu vérifies que le code respecte la règle 20 de `GEMINI.md` (typage strict, linting, interdiction de `print()`), puis tu produis un rapport de conformité priorisé.

## 1. Périmètre & Sources de Vérité

- `GEMINI.md` règle 20 : typage statique strict 100 % (`mypy`, `disallow_untyped_defs`), types modernes Python 3.12+ (unions `X | Y`, generics PEP 695), interdiction des `disable_error_code` globaux, types stubs (`types-peewee`, `types-requests`, `types-markdown`), bannissement de `print()` (T20).
- `pyproject.toml` : config ruff (`E F B I UP T20 PT SIM`, line-length 200), config mypy (overrides `ankiforge.database.migrations.*` et `ankiforge.ui.*` détendus), config bandit.
- Rapport cible : `src/ankiforge/` (migrations et UI ont des overrides mypy légitimes — à vérifier qu'ils restent justifiés).

## 2. Exécution des Outils (Obligatoire)

```bash
# Lint & format (en analyse, SANS --fix pour rapporter ; ne modifier que sur demande)
uv run ruff check .
uv run ruff format --check .

# Typage strict
uv run mypy src/ankiforge

# Importations typing interdites (List/Dict/Tuple/Optional...)
grep -rIn "^from typing import.*\b\(List\|Dict\|Tuple\|Optional\|Union\|AnyStr\)\b" src/ankiforge/ || true

# print() dans le code applicatif (T20)
grep -rInE "(^|[^A-Za-z_])print\(" src/ankiforge/ --include="*.py" || true

# Règles de type désactivées en masse
grep -rIn "disable_error_code" pyproject.toml src/ --include="*.py" --include="*.toml" || true
```

## 3. Points de Contrôle

1. **Typage strict** : toute fonction publique sans annotations de retour/paramètres dans `ankiforge.*` hors overrides autorisés (`database/migrations.*`, `ui.*`) est une violation. Vérifier que les overrides UI/migrations restent le périmètre minimal.
2. **`print()`** : interdiction absolue dans `src/ankiforge/`. Toute occurrence doit être remplacée par `logging.getLogger(__name__)` (niveau adapté — règle 19). Les `script/*` et `tests/*` sont exemptés (per-file-ignores).
3. **Importations typing périmées** : `list`, `dict`, `tuple`, `Optional` → `X | None`, `Union` → `X | Y` (Python 3.12+). Toute importation de `List`/`Dict`/`Tuple` depuis `typing` est une violation.
4. **Ruff** : exécuter les règles `B` (bugbear), `SIM` (simplifications), `UP` (pyupgrade) et signaler les propositions non appliquées ; vérifier que les `# noqa` ajoutés ne masquent pas des erreurs réelles (chaque noqa doit être justifié).
5. **Code mort & dette** : signaler les fonctions jamais appelées (heuristique greps d'usage), les `# TODO`/`# FIXME` et les blocs `except` vides dans `src/` (hors `B110` les skips bandit justifiés UI/fallbacks).
6. **Cohérence des conventions** : nommage, longueur de ligne (200 max), imports isort (`I`).

## 4. Rapport

`audits/audit-qualite-code.md` :

### 📊 Synthèse
Tableau : nombre d'issues par outil (ruff / mypy / grep) et par sévérité (Erreur bloquante / Avertissement / Style).

### 🔍 Détail des violations
Liens cliquables `[fichier.py:Lnn](file://<abs>/...#Lnn)` · règle (code ruff/mypy/grep) · extrait · correction proposée (ex. `typing.List[int]` → `list[int]`, ajout `-> None`).

### 🗺️ Plan de remédiation
Actions ordonnées par priorité (print() et typing d'abord — bloquants CI réels), puis suggestions de refactoring SIM/UP.

## 5. Clôture

Résume le nombre d'issues et les plus bloquantes dans le chat, indique le chemin du rapport, et propose d'appliquer les correctifs automatiques (`uv run ruff check --fix .`) puis de relancer les vérifications.