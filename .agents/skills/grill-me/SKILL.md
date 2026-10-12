---
name: grill-me
description: >-
  Interview contradictoire sans persistance locale pour affûter une idée, un texte ou une conception générale hors dépôt de code.
  Use when the user asks to "grill-me", "grille-moi", "interviewe-moi", "challenge mon idée", or wants a stateless grilling session outside of a repository.
  When NOT to use: Do not use when working inside a codebase with documentation to update (use grill-with-docs).
disable-model-invocation: true
---

# Grill Me — Interview Contradictoire Stateless

Mène une interview serrée et contradictoire pour affûter une idée, un texte ou une conception générale, sans persistance sur le système de fichiers.

## Processus

Invoque la compétence primitive **`grilling`** :
1. Décompose l'idée en un **arbre de décisions**.
2. Identifie la **frontière** : l'ensemble des questions dont les prérequis sont établis.
3. Pose toutes les questions de la frontière en un seul **round numéroté** avec tes réponses recommandées.
4. Itère jusqu'à épuisement de la frontière.

## When NOT to use this skill

- Ne pas utiliser dans un projet ou dépôt où les décisions doivent être persistées dans la documentation → utiliser `/grill-with-docs`.
- Ne pas utiliser pour rédiger directement une spécification sans interview → utiliser `/to-spec`.
- Ne pas utiliser pour coder une solution → utiliser `/implement`.
