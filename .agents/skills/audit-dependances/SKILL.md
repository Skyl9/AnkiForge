---
name: audit-dependances
description: Audit des dépendances, de la chaîne logicielle et du build d'AnkiForge. Use when the user asks to "audit dépendances", "pip-audit", "CVE", "vulnérabilités dépendances", "outdated", "licences", "supply chain", "uv.lock" or "build Nuitka". Runs pip-audit + uv pip list --outdated and reviews dependency/build choices; produces a report under audits/.
---

# Audit Dépendances & Chaîne Logicielle AnkiForge

En tant qu'**Auditeur Supply Chain & Build**, tu évalues la sécurité (`pip-audit`), la fraîcheur, la séparation dépendances groupe dev/docs et la cohérence avec le build Nuitka/extension C, puis tu produis un rapport priorisé.

## 1. Périmètre & Sources de Vérité

- `pyproject.toml` : dépendances runtime (`[project.dependencies]`), groupes `build`, `docs`, `dev` ; config `[tool.bandit]`, `[tool.mutmut]`.
- `uv.lock` : verrouillage complet des dépendances transitives.
- `GEMINI.md` règle 10 (lazy loading des dépendances lourdes Marker/PyTorch — hors runtime principal), règle 12 (extension C Levenshtein avec repli Python), règle 20 (types stubs).
- `.github/workflows/ci.yml` : job `audit-dependencies` (pip-audit), compilation extension C par OS.

## 2. Exécution des Outils (Obligatoire)

```bash
# CVE connues (même commande que la CI ; skip-editable car projet installé en mode editable)
uv run --with pip-audit pip-audit --local --skip-editable || true

# Dépendances obsolètes (majeures)
uv pip list --outdated

# Seuils de dépendances bloquantes (sévérité) : pip-audit --fail-on PACKAGE? -> filtrer la sortie
# Liste des paquets runtime vs dev
uv pip freeze | wc -l
uv pip list | rg -i "numpy|torch|faiss|marker|chromadb|pyside6|nuitka|peewee|keyring"
```

## 3. Points de Contrôle

1. **CVE bloquantes** : tout paquet avec CVE en sévérité haute/critique non justifiée (pin en attente de patch documenté) est une violation critique ; les vulnérabilités modérées avec workaround doivent être notées.
2. **Séparation des groupes** : rien d'accidentel dans `[project.dependencies]` qui devrait vivre en `dev`/`docs`/`build` (ex. `pytest`, `nuitka`, `mkdocs`) ; et réciproquement, pas de dépendance runtime indispensable absente.
3. **Dépendances lourdes / lazy** : Marker OCR, PyTorch, FAISS, ChromaDB ne font pas partie du runtime obligatoire (installés à la volée — vérifier `services/` pour l'installation dynamique et l'absence d'import au sommet).
4. **Extension C** : `src/ankiforge/c_ext/levenshtein_distance.c` est compilée par OS dans la CI (gcc/clang) avec repli Python transparent (`utils/c_bridge.py`) ; vérifier la présence du fallback et la cohérence binaire/source.
5. **Types stubs** : `types-peewee`, `types-requests`, `types-markdown` présents dans `dev` (nécessaires au mypy strict).
6. **Verrouillage** : `uv.lock` commité ; `uv sync --frozen` viable (CI) ; pas de divergence pyproject/uv.lock.
7. **Build Nuitka** (`build_script/`, workflow `release.yml`) : cohérence des bundles (PySide6, extension C, ressources) ; pas de dépendance non embarquable.
8. **Licences** (si demandé) : alerte sur les licences incompatibles avec MIT du projet (via `pip-licenses` si disponible, sinon revue `uv.lock`).

## 4. Rapport

`audits/audit-dependances.md` :

### 📊 Synthèse
Tableau : CVE par sévérité, paquets obsolètes (majeures), écarts de groupes, et catégories (CVE, Fraîcheur, Structure, Build/Lazy, Licences).

### 🔍 Détail
Pour chaque élément : paquet, version, issue, impact, correction proposée (upgrade pin, déplacement de groupe, lazy-load) avec commande de vérification.

### 🗺️ Plan priorisé
Ordre : CVE critiques → paquets obsolètes à risque → restructuration → optimisations build.

## 5. Clôture

Résume les CVE et les obsolescences majeures dans le chat, indique le chemin du rapport, propose d'appliquer les upgrades ciblés (`uv add/upgrade` + `uv sync --frozen` de contrôle).