---
name: audit-ankiforge
description: >
  Orchestre la batterie complète des audits et tests d'AnkiForge (ruff, mypy, pytest, bandit,
  pip-audit, audits spécialisés, skills, docs) en la parallélisant via des sous-agents, en adaptant
  l'exécution à l'environnement de lancement (OS, uv, extension C, headless, réseau, CI, budget
  temps), puis consolide un rapport global priorisé sous audits/. Use when the user asks to
  "audit ankiforge", "audit global", "audit complet", "lancer tous les tests", "auditer l'architecture",
  "vérifier conformité GEMINI.md", "full battery", "audit de conformité", or runs an overarching review.
---

# Instructions

Tu es l'**Orchestrateur d'Audit Global** d'AnkiForge : tu décomposes le contrôle de conformité
(règles `GEMINI.md` + qualité + sécurité + tests + docs) en lots de travail indépendants, tu les
délègues à des **sous-agents parallèles**, puis tu consolides un rapport unique, priorisé et
contextualisé par l'environnement.

## 1. Détection de l'environnement de lancement

Avant tout travail, sonde l'environnement réel et construis la **matrice d'environnement** (tu la
fourniras à chaque sous-agent) :

```bash
uname -s 2>/dev/null || ver                       # darwin / linux / windows
command -v uv >/dev/null && uv --version || echo "uv absent"
ls c_ext/*.so c_ext/*.dll c_ext/*.pyd 2>/dev/null || echo "extension C non compilée (fallback Python)"
python3 -c "import os; print('nproc≈', os.cpu_count())"
echo "CI=${CI:-non} GITHUB_ACTIONS=${GITHUB_ACTIONS:-non} ANKIFORGE_ENV=${ANKIFORGE_ENV:-dev}"
curl -sI --max-time 3 https://pypi.org 2>/dev/null | head -1 || echo "réseau indisponible"
[ -n "$DISPLAY" ] && echo "display OK" || echo "headless (sans DISPLAY)"
```

**Interprétation & règles de décision :**

| Signal runtime | Décision d'adaptation |
|---|---|
| OS `windows` | binaire C = `.dll` ; même commandes `uv run` ; scripts bash → équivalents PowerShell/Cmd si nécessaire |
| `uv` absent | basculer sur `python -m` (ruff/mypy/pytest/bandit) ; signaler le risque de divergence d'environnement |
| extension C absente | fallback Python pur prévu (`utils/c_bridge.py`) : vérifier son utilisation, pas une erreur |
| headless (pas de DISPLAY) | ne JAMAIS ouvrir de fenêtre Qt : tests UI via pytest-qt headless (`QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1`, `ANKIFORGE_MOCK_WEBENGINE=1` posés par conftest) ; pas de capture visuelle non sollicitée |
| réseau indisponible | WPs `pip-audit`, `zensical build` → `SKIPPED - réseau` (noté au rapport) ; le reste reste exécutable localement |
| en CI (`GITHUB_ACTIONS`/`CI`) | budget court : `-k "not slow"`, sans coverage longue ni mutation testing ; couverture uniquement en série `-n 0` |
| `nproc` (cœurs) ≥ 8 | pytest `-n auto` (addopts) ; sinon forcer `-n 0` pour éviter la sur-allocation |
| mode **quick** (défaut) | sous-ensemble rapide uniquement (dures < 2-3 min) ; WPs lourds (coverage, slow tests, docs build) marqués `SUSPENDU` si non demandés |
| mode **full** demandé | suite complète `pytest tests/ -k "not slow" -n 0` + coverage ≥ 70 + builds docs zensical |

## 2. Découpage en lots de travail (batterie de tests) via sous-agents

Décompose l'audit en **work packages indépendants** et lance **un sous-agent par WP en parallèle**
(via l'outil de sous-agent/task de ton runtime ; en l'absence de support, exécute-les séquentiellement
dans l'ordre de priorité ci-dessous). Chaque WP cartographie vers un skill d'audit spécialisé existant :

| WP | Mission du sous-agent | Skill dédié | Commande (ex.) | Activé quand |
|---|---|---|---|---|
| W1 | Lint & format `ruff` | `audit-qualite-code` | `uv run ruff check . ; uv run ruff format --check .` | toujours |
| W2 | Typage strict `mypy` | `audit-qualite-code` | `uv run mypy src/ankiforge` | toujours |
| W3 | Tests rapides pytest | `audit-tests-ci` | `uv run pytest tests/ -k "not slow" -q` | toujours |
| W4 | Couverture + SÉRIEL | `audit-tests-ci` | `uv run pytest tests/ -k "not slow" -n 0 --cov=ankiforge --cov-fail-under=70` | en mode full |
| W5 | Sécurité `bandit`+`gitleaks` | `audit-securite` | `uv run bandit -c pyproject.toml -r src/` | toujours (bandit), gitleaks si dispo |
| W6 | Dépendances `pip-audit`+outdated | `audit-dependances` | `uv run --with pip-audit pip-audit --local --skip-editable` | réseau OK |
| W7 | BDD/Peewee (CASCADE, atomic, NOT NULL) | `audit-donnees` | inspection `src/ankiforge/database/` (statique) | toujours |
| W8 | UI/Design System (tokens, WCAG, headless) | `audit-design-ui` | inspection `src/ankiforge/ui/` + `DESIGN.md` (statique) | mode full |
| W9 | Pipeline IA/DAG/MCP (injections, JSON, coûts) | `audit-ia-pipeline` | inspection `src/ankiforge/services/ai/` (statique) | mode full |
| W10 | Catalogue skills | `mise-a-jour-metadonnees` | charge le skill cible puis lance son script `auditer_coherence_skills.py` | toujours |
| W11 | Docs Zensical build | `documentation-zensical` | `uv run zensical build` | mode full + réseau |

**Contrat imposé à chaque sous-agent :**
1. Reçoit : matrice d'environnement (§1), chemin du workspace, sa mission (tableau ci-dessus), et le chemin `audits/raw/`.
2. **Ne modifie jamais le code source** — audit/rapport uniquement ; aucun `--fix` sans accord explicite de l'utilisateur.
3. Sauvegarde la sortie brute horodatée : `audits/raw/<wp>-<horodatage>.txt` (mkdir -p `audits/raw`).
4. Ne fait **aucun appel LLM/API externe** (batterie 100 % locale ; mocks garantis par la suite pytest existante).
5. Retourne une **synthèse structurée** par violation : `[fichier.py:Lnn](file://{workspace}/...#Lnn)`, règle violée (numéro de règle GEMINI.md, code ruff/mypy, ou libellé), extrait, piste de correction, sévérité (Critique/Majeur/Mineur). Ou `OK` / `SKIPPED - <cause>` si rien à signaler.

## 3. Vérifications ciblées rapides (option, sans sous-agent)

Pour des audits ciblés de volumes limités, tu peux exécuter toi-même des `grep` :
`from typing import.*(List|Dict|Tuple)`, `print\(` hors comentaires dans `src/ankiforge/ui/`,
`time.sleep\(|sleep\(` dans `tests/`, `MagicMock\(|patch\(` sur modèles Peewee dans `tests/`,
marges CSS sur QLabel dans `src/ankiforge/ui/`, patterns de clés API dures.

## 4. Consolidation du rapport global (artefact)

Compile toutes les synthèses des sous-agents dans `audits/audit-ankiforge-<date>.md` :

1. **Contexte d'exécution** : matrice d'environnement (§1), mode quick/full, durée, WPs `SKIPPED` et leur cause.
2. **📊 Tableau de synthèse** : anomalies par sévérité (Critique/Majeur/Mineur) et par WP (W1–W11).
3. **🔍 Violations détaillées** : regroupées par WP ; chaque violation avec lien cliquable absolu, règle (GEMINI.md / ruff / mypy / bandit), extrait incriminé et correctif immédiat proposé (diff court).
4. **🆚 Diff vs audit précédent** : charge le dernier rapport `audits/audit-ankiforge-*.md` (si présent) et liste les régressions et améliorations.
5. **🗺️ Plan de résolution priorisé** : ordonner par sévérité décroissante, contexté par l'environnement (ex. test lent uniquement sur `full`, CVE requérant le réseau).

## ⛔ Ne PAS utiliser ce skill si...

- La requête est une **modification de code isolée** sans besoin d'audit global (éditer directement).
- L'utilisateur demande de **corriger** un bug précis déjà identifié (ce skill audite, ne corrige pas).
- La demande porte sur un **sous-domaine spécialisé unique** : utiliser le skill dédié (`audit-donnees`,
  `audit-tests-ci`, `audit-performance`, `audit-ia-pipeline`, `audit-securite`, `audit-qualite-code`,
  `audit-design-ui`, `audit-dependances`).
- L'audit complet a été exécuté récemment **sans modification du code source** depuis : proposer un diff ciblé au lieu de relancer la batterie.
- L'utilisateur veut uniquement **relancer la suite pytest** sans audit : `uv run pytest` suffit.

## 5. Clôture

Résume dans le chat : verdict global (PASS si 0 bloquant), compteurs par WP, cause des WPs
`SKIPPED`, et le chemin absolu du rapport. Propose les actions de correction à passer aux sous-agents
de correction (ex. `uv run ruff check --fix .`, patch mypy ciblé) sans les appliquer sans accord.
