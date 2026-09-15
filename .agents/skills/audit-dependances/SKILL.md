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

**Portée de cet audit** : l'exécution locale ne couvre qu'un seul OS et une seule version de Python à la fois. La couverture multi-OS/multi-version reste assurée par la CI ; le rapport doit le mentionner explicitement pour ne pas donner une fausse impression de couverture complète.

## 2. Exécution des Outils (Obligatoire)

Toutes les sorties sont conservées brutes sous `audits/raw/` (horodatées) pour permettre une comparaison d'un audit à l'autre.

```bash
mkdir -p audits/raw
STAMP=$(date +%Y-%m-%d)

# CVE connues (même commande que la CI ; skip-editable car projet installé en mode editable)
# Sortie JSON conservée pour analyse et historique — ne pas utiliser `|| true` en aveugle :
# un code de sortie non nul signifie qu'il y a des CVE, c'est le signal qu'on veut capter.
uv run --with pip-audit pip-audit --local --skip-editable --format json \
  > "audits/raw/pip-audit-${STAMP}.json"
PIP_AUDIT_STATUS=$?

# Dépendances obsolètes (majeures)
uv pip list --outdated > "audits/raw/outdated-${STAMP}.txt"

# Liste des paquets runtime vs dev
uv pip freeze | wc -l
uv pip list | rg -i "numpy|torch|faiss|marker|chromadb|pyside6|nuitka|peewee|keyring"

# Licences (si demandé) — installation explicite, pas de dépendance implicite
uv run --with pip-licenses pip-licenses --format=markdown \
  > "audits/raw/licenses-${STAMP}.md" 2>/dev/null || echo "pip-licenses indisponible, revue manuelle de uv.lock"
```

> Note : `grep -iE` est utilisé plutôt que `rg` pour ne pas supposer que ripgrep est installé sur toutes les machines/CI.

## 3. Points de Contrôle

1. **CVE bloquantes** : tout paquet avec une CVE **CVSS ≥ 7.0** (sévérité haute/critique selon le scoring OSV/PyPI Advisory utilisé par pip-audit) non justifiée (pin en attente de patch documenté) est une violation critique ; les vulnérabilités modérées (CVSS 4.0–6.9) avec workaround doivent être notées mais non bloquantes.
2. **Séparation des groupes** : rien d'accidentel dans `[project.dependencies]` qui devrait vivre en `dev`/`docs`/`build` (ex. `pytest`, `nuitka`, `mkdocs`) ; et réciproquement, pas de dépendance runtime indispensable absente.
3. **Dépendances lourdes / lazy** : Marker OCR, PyTorch, FAISS, ChromaDB ne font pas partie du runtime obligatoire (installés à la volée — vérifier `services/` pour l'installation dynamique et l'absence d'import au sommet).
4. **Extension C** : `src/ankiforge/c_ext/levenshtein_distance.c` est compilée par OS dans la CI (gcc/clang) avec repli Python transparent (`utils/c_bridge.py`) ; vérifier la présence du fallback et la cohérence binaire/source.
5. **Types stubs** : `types-peewee`, `types-requests`, `types-markdown` présents dans `dev` (nécessaires au mypy strict).
6. **Verrouillage** : `uv.lock` commité ; `uv sync --frozen` viable (CI) ; pas de divergence pyproject/uv.lock.
7. **Build Nuitka** (`build_script/`, workflow `release.yml`) : cohérence des bundles (PySide6, extension C, ressources) ; pas de dépendance non embarquable.
8. **Licences** (si demandé) : alerte sur les licences incompatibles avec MIT du projet (via `pip-licenses` — voir commande section 2, sinon revue `uv.lock`).

## 4. Rapport

`audits/audit-dependances.md` (écrasé à chaque audit — l'historique brut vit sous `audits/raw/`) :

### 📊 Synthèse
Tableau : CVE par sévérité (avec score CVSS), paquets obsolètes (majeures), écarts de groupes, et catégories (CVE, Fraîcheur, Structure, Build/Lazy, Licences).

### 🔁 Évolution depuis le dernier audit
Comparaison avec le fichier `audits/raw/` le plus récent précédent (nouvelles CVE, CVE corrigées, nouveaux paquets obsolètes) — si un audit précédent existe.

### 🔍 Détail
Pour chaque élément : paquet, version, issue, score CVSS le cas échéant, impact, correction proposée (upgrade pin, déplacement de groupe, lazy-load) avec commande de vérification.

### 🗺️ Plan priorisé
Ordre : CVE critiques (CVSS ≥ 7.0) → paquets obsolètes à risque → restructuration → optimisations build.

## ⛔ Ne PAS utiliser ce skill si...

- La demande est une simple **installation ou mise à jour de dépendance** (`uv add X`) sans besoin d'audit global.
- L'utilisateur veut **comprendre l'API** d'une bibliothèque (pas un audit de supply chain).
- La requête concerne uniquement la **qualité du code source** → utiliser `audit-qualite-code`.
- La requête concerne uniquement les **CVE dans le code applicatif** (ex: `eval`, subprocess) → utiliser `audit-securite`.
- L'environnement n'a pas `uv` installé ou le projet n'utilise pas `pyproject.toml` / `uv.lock`.

## 5. Clôture

Résume les CVE et les obsolescences majeures dans le chat, indique le chemin du rapport et des sorties brutes, précise que la couverture est limitée à l'OS/version Python locaux (CI = couverture complète), propose d'appliquer les upgrades ciblés (`uv add/upgrade` + `uv sync --frozen` de contrôle).
