---
name: code-simplification
description: >-
  Simplifie le code pour la clarté et la maintenabilité sans altérer le comportement observable. Réduit la complexité cognitive, élimine le code mort et unifie le style selon les conventions du projet.
  Use when the user asks to "simplifier le code", "refactorer pour la lisibilité", "clarifier ce module", "alléger la fonction", "code-simplification", or when code works but has accumulated unnecessary complexity.
  When NOT to use: Do not use if you don't yet understand what the code does or if the code is already concise and readable.
---

# Code Simplification

Simplifier le code consiste à réduire sa complexité cognitive tout en préservant rigoureusement son comportement observable. L'objectif n'est pas d'avoir moins de lignes, mais un code plus facile à lire, maintenir et faire évoluer.

> **Référence approfondie** : `references/refactoring-patterns.md` pour le catalogue complet des motifs de complexité structurelle, les tables de nommage et les exemples de refactoring.

## Les Cinq Principes Fondamentaux

1. **Préserver le comportement à l'identique** :
   - Mêmes entrées, sorties, erreurs et effets de bord.
   - Tous les tests existants doivent passer sans modification.
2. **Respecter les conventions du projet** :
   - Cohérence avec `GEMINI.md`, `AGENTS.md` et le code voisin.
   - Respecter le typage strict et l'interdiction de `print()`.
3. **Privilégier la clarté à la concision excessive** :
   - Remplacer les ternaires imbriqués par des structures explicites ou tables de correspondance.
   - Préférer un nom descriptif à une contraction obscure.
4. **Maintenir l'équilibre** :
   - Éviter le sur-inlining qui supprime des abstractions utiles.
   - Ne pas fusionner deux fonctions simples en une seule complexe.
5. **Périmètre ciblé** :
   - Se limiter au code récemment modifié ou explicitement demandé. Pas de refactoring en cascade non sollicité.

## Processus en 4 Étapes

### Étape 1 : Comprendre avant de modifier (Chesterton's Fence)
Identifier la responsabilité du code, ses appelants, ses cas limites et la raison de son implémentation initiale (git blame) avant toute altération.

### Étape 2 : Identifier les opportunités
Consulter `references/refactoring-patterns.md` pour détecter :
- Complexité structurelle (imbrications profondes, fonctions > 50 lignes, drapeaux booléens).
- Nommage générique (`data`, `temp`, `val`) à remplacer par des termes de domaine.
- Redondances et abstractions prématurées sans valeur ajoutée.

### Étape 3 : Appliquer par incréments vérifiés
- Effectuer un seul changement à la fois.
- Lancer la suite de tests après chaque modification (`uv run pytest tests/...`).
- Séparer strictement le refactoring des modifications de fonctionnalités.

### Étape 4 : Vérifier le résultat
- S'assurer que le diff est limpide et lisible.
- Valider la chaîne de contrôle : `uv run python script/verify.py`.

## When NOT to use this skill

- Le code est déjà lisible et idiomatique — ne pas simplifier pour le simple plaisir de retoucher.
- Le comportement du code n'est pas encore compris — comprendre avant d'éditer.
- Le module est sur le point d'être remplacé ou réécrit intégralement.
- La simplification envisagée dégrade mesurablement les performances critiques.
