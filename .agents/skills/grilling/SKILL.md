---
name: grilling
description: >-
  Moteur primitif d'interview contradictoire par rounds de questions pour explorer la frontière de décision d'un arbre de conception.
  Use when the user asks to "grilling", "relentless interview", or when invoked by grill-me or grill-with-docs.
  When NOT to use: Do not use directly for full feature scoping with documentation (use grill-with-docs).
---

# Grilling — Moteur Primitif d'Interview

Interviewe l'utilisateur de manière méthodique jusqu'à atteindre une compréhension partagée. Modélise la réflexion sous forme d'un **arbre de conception** où chaque choix conditionne les décisions aval.

## Fonctionnement par Tours (Rounds)

La **frontière** représente l'ensemble des décisions dont les prérequis sont déjà tranchés : les questions qu'il est possible de poser *immédiatement* sans anticiper sur des arbitrages en suspens. Pose toute la frontière en un seul round :

```markdown
❓ **Q1** - **<titre>** : <corps de la question avec options éventuelles>

➡️ <réponse recommandée>

---

❓ **Q2** - **<titre>** : <corps de la question>

➡️ <réponse recommandée>
```

## Règles Clés

- **Faits vs Décisions** : chercher les faits dans le code, les tests et l'environnement est le rôle de l'agent. Les décisions appartiennent à l'utilisateur.
- À chaque round complété, recalculer la frontière et poser le round suivant.
- La session se termine lorsque la frontière est vide. Ne pas agir tant que l'accord partagé n'est pas explicite.

## When NOT to use this skill

- Ne pas utiliser directement pour une séance de cadrage d'architecture liée à un dépôt → utiliser `/grill-with-docs`.
- Ne pas utiliser pour une interview sans trace hors d'un dépôt → utiliser `/grill-me`.
