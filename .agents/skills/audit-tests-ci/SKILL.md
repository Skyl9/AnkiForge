---
name: audit-tests-ci
description: Audit de la qualité du jeu de tests et de la configuration CI/CD d'AnkiForge. Use when the user asks to "audit tests", "audit CI", "couverture", "coverage", "mock", "mocking LLM", "pytest", "headless", "pre-commit", "workflows GitHub Actions" or "fiabilité des tests". Checks mocking discipline, headless constraints, coverage gates and CI workflows; produces a report under audits/.
---

# Audit Tests & CI AnkiForge

En tant qu'**Auditeur QA & CI/CD**, tu évalues la discipline de test (isolation, mocking, headless), la couverture et la robustesse des workflows GitHub Actions/pre-commit, puis tu produis un rapport priorisé.

## 1. Périmètre & Sources de Vérité

- `GEMINI.md` règle 20 : pyramide de tests (unitaires purs < 10 ms, intégration BDD en mémoire partagée, UI pytest-qt headless), IA 100 % mockées, couverture CODEVIS ≥ 70 %, pré-push test+mypy.
- `AGENTS.md` : « Testing Constraints » (tous LLM mockés, `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX`, fixture `mock_db`, nettoyage widgets Qt), commandes qualité.
- `pytest.ini` (xdist `-n auto`, `timeout=30.0`, `timeout_method=thread`), `tests/conftest.py`, `.pre-commit-config.yaml`, `.github/workflows/` (`ci.yml`, `docs.yml`, `nightly.yml`, `release.yml`).

## 2. Commandes d'Investigation

```bash
# Collecte seule (rapide) pour vérifier la santé de découverte
uv run pytest --collect-only -q | tail -3

# Sous-ensemble rapide en série (recommandé, ~40s) — pas la suite complète d'emblée
uv run pytest tests/ -m "not slow" -n 0 -q

# Couverture sur le sous-ensemble (CI exige ≥ 70)
uv run pytest tests/ -m "not slow" -n 0 --cov=ankiforge --cov-report=term-missing -q | tail -20 || true

# Patterns interdits dans les tests
grep -rInE "time\.sleep\(|sleep\(" tests/ || true
grep -rInE "(MagicMock|mock\.patch\(|patch\.object)" tests/ || true
grep -rInE "(OpenAI\(|Client\(|Anthropic\(|genai\.|ollama|requests\.(get|post))\(" tests/ || true
```

## 3. Points de Contrôle

1. **Mocking LLM 100 %** : aucun test ne doit initier de vraie connexion à OpenAI/Anthropic/Gemini/Ollama. Vérifier le fixture/driver utilisé à travers la suite (mock déterministe des fournisseurs, embeddings, retrieveurs). Toute occurrence d'instanciation réelle est une violation bloquante.
2. **Discipline des mocks BDD** : interdiction stricte de `MagicMock`/`patch` sur les modèles Peewee — utiliser la fixture `mock_db` (in-memory `mode=memory&cache=shared`). Signaler tout contournement.
3. **Headless UI** : les tests UI doivent fonctionner sans affichage (`QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1`, `ANKIFORGE_MOCK_WEBENGINE=1` dans `conftest.py`) ; pas de snapshot visuel (jugé instable).
4. **`time.sleep`** dans `tests/` : interdit (problèmes de flakiness) — remplacer par attente d'événement (`SignalSpy`, polling court, `qtbot.waitSignal`/`waitUntil`).
5. **Pyramide & isolation** : tests unitaires purs < 10 ms (zéro BDD, zéro widget, zéro réseau) ; identifier les tests lents (> 1 s) via marqueur `slow`/collect durations.
6. **Pytest config** : `pytest.ini` (`--strict-markers`, testpaths, addopts xdist, timeout) cohérent avec conftest ; markers documentés et 100% assignés (aucun test sans marqueur unitaire/intégration/UI).
7. **CI/CD** (`.github/workflows/ci.yml`) : jobs qualité parallèles (ruff, mypy, bandit, pip-audit), matrice multi-OS (Linux/macOS/Windows) avec compilation de l'extension C, coverage SÉRIEL (`-n 0`, `--cov-fail-under=70` sur Linux — contrainte Qt/WebEngine), gitleaks, build & smoke test Nuitka. Signaler toute régression (ex. couverture re-parallélisée, seuil abaissé).
8. **Pré-commit / pré-push** : hooks `ruff --fix`+format, pre-push `mypy` + tests rapides, sous 5-10 s ; rendre l'ordre de vérification conforme à `AGENTS.md`.

## 4. Rapport

`audits/audit-tests-ci.md` :

### 📊 Synthèse
Anomalies par sévérité et par catégorie (Mocking, Isolation, Headless, CI/CD, Config, Performance des tests), + durée moyenne du sous-ensemble rapide.

### 🔍 Violations détaillées
Liens cliquables `[fichier.test:Lnn](file://<abs>/...#Lnn)` · règle violée · extrait · correction (ex. remplacer `time.sleep(2)` par `qtbot.waitUntil`).

### 🗺️ Plan priorisé
Actions ordonnées (flakiness/mocking d'abord), puis optimisations CI (durées, caches, parallélisation sûre).

## ⛔ Ne PAS utiliser ce skill si...

- La demande est d'**écrire un nouveau test** pour une fonctionnalité → utiliser les outils d'édition directement.
- L'utilisateur veut uniquement **relancer la suite de tests** sans audit (`uv run pytest` suffit).
- La requête concerne les **performances de l'application** (lenteur UI, N+1 queries) → utiliser `audit-performance`.
- Le workflow CI dont parle l'utilisateur est un **projet différent** (hors AnkiForge GitHub Actions).
- Les **erreurs de tests** signalées sont déjà triagées et le correctif est connu — passer directement à la correction.

## 5. Clôture

Résume l'état des tests (nombre, durée, couverture) et les risques de flakiness dans le chat, indique le chemin du rapport, propose les correctifs (fixtures, mocks, ajustements CI).
