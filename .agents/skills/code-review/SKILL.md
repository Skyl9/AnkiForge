---
name: code-review
description: >-
  Revue de code hybride à deux axes (Standards du dépôt & Respect de la spécification Obsidian) avec architecture en 3 couches (Filtres déterministes, Générateurs spécialisés isolés, Filtre critique adversarial anti-faux-positifs).
  Use when the user asks to "code-review", "revue de code", "revoir la branche", "review since", or wants a 2-axis review against standards and spec.
  When NOT to use: Do not use for in-flight adversarial decision testing (use doubt-driven-development), automated commit/push verification gating (use script/verify.py), or refactoring without formal review (use code-simplification).
---

# Code Review — Revue Hybride à Deux Axes & Anti-Bruit

Revue de code hybride à deux axes distincts comparant le diff entre `HEAD` et un point de référence (`git diff <base>...HEAD`), orchestrée en 3 couches pour éliminer les faux positifs et garantir la conformité aux standards d'AnkiForge.

> **Références de niveau 3 :**
> - `references/subagent-prompts.md` : Gabarits de prompts des sous-agents (Standards, Spécification, Critic).
> - `references/review-checklist-ankiforge.md` : Checklist des règles canoniques AnkiForge (GEMINI.md, AGENTS.md, DESIGN.md).
> - `references/conventional-comments-guide.md` : Guide normatif des Conventional Comments et verdicts.

---

## ⚡ Principes Directeurs Non Négociables

1. **Parcimonie d'Exécution** : Ne jamais relancer `script/verify.py` complet ou la suite pytest si le superviseur a déjà validé la porte de vérification sur l'arbre de travail. Contrôler les linters et le typage via `uv run python script/verify.py --no-tests` (~10s) et le score CRAP via `uv run python script/verify.py --crap` (< 1s).
2. **Anti-Faux-Positifs par Conception** :
   - *Silence valorisé* : Un retour `findings: []` est un état de succès explicite. Interdiction de spéculer ou de forcer des remarques cosmétiques.
   - *Quote First, Analyze Second* : Tout constat doit citer textuellement l'extrait de code exact du diff.
   - *Fix-Guided Counterfactual* : Tout constat doit être accompagné d'un patch concret de remédiation.
   - *Dépassement du silo diff* : Les sous-agents utilisent les outils (`read_file`, `grep`) pour vérifier les appelants et atténuations amont/aval.

---

## 🔄 Déroulement en 5 Phases

```
[Phase 1 : Cadrage & Pré-contrôles] ──► [Phase 2 : Blast Radius & Aiguillage]
                                                        │
┌───────────────────────────────────────────────────────┘
▼
[Phase 3 : Génération Parallèle Isolée (Standards + Spécification + Conditionnel)]
│
▼
[Phase 4 : Filtrage Critique Adversarial (Critic Pass - réfutation du bruit)]
│
▼
[Phase 5 : Consolidation & Verdict Conventional Comments (APPROVE / REQUEST_CHANGES)]
```

### Phase 1 — Cadrage & Contrôles Déterministes
1. Identifier la base : `git log <base>..HEAD --oneline` et `git diff <base>...HEAD`.
2. Identifier le ticket Obsidian : `ankiforge_obsidian/Tickets/<Type> - <Titre>.md` (critères d'acceptation, périmètre).
3. Exécuter les pré-contrôles statiques déterministes :
   ```bash
   uv run python script/verify.py --no-tests   # linters, formats, mypy strict, bandit
   uv run python script/verify.py --crap       # contrôle CRAP <= 25 sur le diff
   ```

### Phase 2 — Analyse du Blast Radius & Aiguillage
Détecter les chemins sensibles modifiés pour aiguiller un éventuel sous-agent spécialiste conditionnel :
- `database/` ou `migrations/` $\rightarrow$ Spécialiste Intégrité Peewee & Schéma.
- `services/ai/` ou `services/mcp/` $\rightarrow$ Spécialiste Pipeline DAG & Sécurité MCP.
- `ui/` $\rightarrow$ Spécialiste UI PySide6 / Design Tokens / Offscreen.

### Phase 3 — Génération Parallèle Isolée (Couche 2)
Lancer les sous-agents spécialisés en parallèle (prompts issus de `references/subagent-prompts.md`) :
- **Sous-Agent Standards** : Contrôle la conformité aux standards via `references/review-checklist-ankiforge.md`.
- **Sous-Agent Spécification** : Valide chaque critère du ticket (`[MET]`, `[PARTIALLY_MET]`, `[UNMET]`, `[SCOPE_CREEP]`).
- *(Optionnel)* **Sous-Agent Spécialiste** : Contrôle approfondi du sous-système sensible identifié en Phase 2.

### Phase 4 — Filtrage Critique Adversarial (Couche 3)
Court-circuitée si zéro anomalie bloquante ou majeure en Phase 3. Sinon, soumettre le pool brut au sous-agent Critic :
- Réfuter chaque anomalie (recherche d'atténuations amont/aval via `grep`/`read_file`, validation textuelle).
- Rejeter les faux positifs et requalifier les simples suggestions de style en non-bloquantes.

### Phase 5 — Consolidation & Verdict
Restituer le rapport au format `references/conventional-comments-guide.md` :
1. **En-tête & Verdict** : `🟢 APPROVE`, `🔴 REQUEST_CHANGES`, ou `🟡 COMMENT`.
2. **Axe 1 — Standards** : Synthèse déterministe (linters, typage, CRAP) et constats validés.
3. **Axe 2 — Spécification** : Grille des critères d'acceptation du ticket Obsidian.
4. **Suggestions & Patchs** : Extraits de code correctifs prêts à l'emploi.
5. **Bloc Obsidian** : Résumé à insérer dans le ticket avant clôture.

---

## When NOT to use this skill

- Tester une décision d'architecture en cours de conception $\rightarrow$ utiliser `doubt-driven-development`.
- Porte de vérification automatisée de commit/push $\rightarrow$ utiliser `verification-environnement` (`script/verify.py`).
- Simplifier ou clarifier du code sans relecture formelle $\rightarrow$ utiliser `code-simplification`.
- Auditer statiquement tout le dépôt sur un axe spécialisé $\rightarrow$ utiliser le skill d'audit dédié (`audit-qualite-code`, `audit-securite`, etc.).
