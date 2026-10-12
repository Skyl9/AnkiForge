---
name: wait-what
description: >-
  Recadre et réexplique la dernière intervention lorsque l'explication précédente n'a pas été comprise, en simplifiant le langage et en utilisant le glossaire CONTEXT.md.
  Use when the user asks to "wait-what", "attends quoi", "pas compris", "réexplique", or indicates that the previous explanation was confusing or missed the mark.
  When NOT to use: Do not use if the user asks a completely new question or asks to execute a specific tool command.
disable-model-invocation: true
---

# Wait What — Réexplication et Clarification Immédiate

Interrompt le fil lorsque le dernier message n'a pas été compris. Reformule l'explication avec clarté, concision et pédagogie.

## Règles de Restitution

1. **Fournir le contexte manquant** : expliciter le point de départ et l'enjeu sous-jacent.
2. **Langage technique simplifié** : bannir le jargon obscur et employer des phrases courtes et directes.
3. **Vocabulaire canonique** : utiliser exclusivement les termes définis dans le glossaire `CONTEXT.md` du projet.
4. **Restitution impérative en français** : exposer la synthèse de manière limpide.

## When NOT to use this skill

- L'utilisateur pose une nouvelle question thématique → répondre directement.
- L'utilisateur donne un ordre de dev clair → exécuter l'action.
