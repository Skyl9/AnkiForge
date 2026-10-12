---
name: code-review
description: >-
  Revue de code à deux axes (Conformité aux standards du repo + Respect de la spécification/ticket Obsidian). Exécute deux sous-agents d'inspection en parallèle et agrège leurs constats sans masquer les faiblesses.
  Use when the user asks to "code-review", "revue de code", "revoir la branche", "review since", or wants a 2-axis review against standards and spec.
  When NOT to use: Do not use for in-flight adversarial decision testing (use doubt-driven-development) or pre-push automated quality gating (use script/verify.py).
---

# Code Review — Revue à Deux Axes (Standards & Spécification)

Revue de code à deux axes distincts comparant le diff entre `HEAD` et un point de référence (commit, branche, tag, ou merge-base) :

- **Axe 1 — Standards** : le code respecte-t-il les standards documentés du dépôt (`GEMINI.md`, `AGENTS.md`, typage strict, conventions d'architecture) ?
- **Axe 2 — Spécification** : le code implémente-t-il fidèlement le ticket ou la spécification Obsidian d'origine sans régression ni hors-périmètre ?

Les deux analyses s'exécutent en sous-agents parallèles isolés afin d'éviter toute pollution croisée de contexte.

## Processus

1. **Définir le point de référence** :
   - `git diff <point-fixe>...HEAD` et liste des commits via `git log <point-fixe>..HEAD --oneline`.
2. **Identifier la spécification source** :
   - Note de ticket Obsidian (`ankiforge_obsidian/Tickets/<Type> - <Titre>.md`), spécification dans `docs/`, ou description de tâche.
3. **Identifier les sources de standards** :
   - `GEMINI.md` (règles 13, 18, 19, 20, 21), `AGENTS.md`, `DESIGN.md`.
4. **Lancer les deux sous-agents en parallèle** :
   - **Sous-agent Standards** : relève toute violation de standard ou mauvaise pratique structurelle.
   - **Sous-agent Spécification** : relève les exigences non satisfaites, les comportements erronés ou les dérives de périmètre (scope creep).
5. **Agréger les résultats** :
   - Présenter les deux rapports distincts sous `## Standards` et `## Spécification`. Ne jamais fusionner arbitrairement les axes.

## When NOT to use this skill

- Ne pas utiliser pour tester une décision d'architecture en cours de conception → utiliser `/doubt-driven-development`.
- Ne pas utiliser pour la porte de vérification automatisée de commit/push → utiliser `verification-environnement` (`script/verify.py`).
- Ne pas utiliser pour simplifier le code sans relecture formelle → utiliser `/code-simplification`.
