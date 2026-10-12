---
name: grill-with-docs
description: >-
  Interview contradictoire stateful pour affûter une idée ou fonctionnalité dans le dépôt AnkiForge, en mettant à jour le glossaire CONTEXT.md et en enregistrant des ADRs.
  Use when the user asks to "grill-with-docs", "cadrer l'idée", "cadrer la fonctionnalité", "affûter le besoin avec doc", or wants an architectural interview with paper trail.
  When NOT to use: Do not use outside of a codebase or without doc persistence (use grill-me).
disable-model-invocation: true
---

# Grill With Docs — Cadrage & Affûtage Persistant

Mène une interview contradictoire et rigoureuse pour affûter une idée ou une évolution d'AnkiForge, en maintenant en continu une trace écrite vérifiable dans le dépôt.

## Processus

Cette compétence orchestre conjointement :
1. **`grilling`** : pour progresser de round en round le long de la frontière de l'arbre de conception jusqu'à accord mutuel.
2. **`domain-modeling`** : pour clarifier la terminologie, enrichir le glossaire `CONTEXT.md` et figer les arbitrages structurants sous forme d'ADR (`docs/adr/NNNN-titre.md`).

## Règles d'Exécution

- La recherche de faits dans la base de code est la responsabilité de l'agent (ne pas interroger l'utilisateur sur ce qui peut être vérifié par le code ou les tests).
- Poser les questions de la frontière d'un bloc en formulant systématiquement la réponse recommandée.
- Mettre à jour `CONTEXT.md` en ligne dès qu'un terme de domaine est stabilisé.
- Ne pas passer à l'implémentation tant que la frontière n'est pas vide et confirmée par l'utilisateur.

## When NOT to use this skill

- Ne pas utiliser hors d'un dépôt de code ou pour une réflexion jetable sans persistance → utiliser `/grill-me`.
- Ne pas utiliser lorsque l'idée est déjà complètement tranchée et prête pour spécification → utiliser `/to-spec`.
- Ne pas utiliser pour coder une tâche directement → utiliser `/implement`.
