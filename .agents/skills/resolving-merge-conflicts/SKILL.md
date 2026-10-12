---
name: resolving-merge-conflicts
description: >-
  Résout les conflits de fusion (merge) ou de rebase git en cours en analysant l'intention d'origine de chaque branche et en préservant la cohérence fonctionnelle.
  Use when the user asks to "résoudre les conflits git", "résoudre le merge", "conflit de rebase", "resolving-merge-conflicts", or is in an active git conflict state.
  When NOT to use: Do not use if there is no active git conflict or when preparing a new branch before merge.
---

# Resolving Merge Conflicts — Résolution de Conflits Git

Résout méthodiquement les conflits de fusion ou de rebase git sans recourir à un abandon brutal (`--abort`).

## Processus

1. **Analyser l'état actuel** : identifier les fichiers en conflit via `git status` et inspecter l'historique des deux branches (`git log ..MERGE_HEAD` / `git log ..HEAD`).
2. **Identifier l'intention première** : lire les messages de commits et les tickets de référence pour comprendre pourquoi chaque modification a été introduite.
3. **Résoudre bloc par bloc (hunk by hunk)** :
   - Préserver les deux intentions lorsque c'est possible.
   - En cas d'incompatibilité, privilégier l'objectif principal de la branche cible en explicitant le compromis.
   - Ne jamais inventer de comportement non sollicité.
4. **Vérifier les contrôles automatisés** :
   ```bash
   uv run python script/verify.py
   ```
5. **Finaliser l'opération** : indexer les fichiers résolus (`git add`) et poursuivre la fusion ou le rebase (`git rebase --continue` ou commit de merge).

## When NOT to use this skill

- Aucun conflit de fusion n'est actif sur le dépôt.
- L'utilisateur souhaite comparer deux branches sans les fusionner → utiliser `git diff` ou `/code-review`.
