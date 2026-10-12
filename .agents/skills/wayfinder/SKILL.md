---
name: wayfinder
description: >-
  Planifie et cartographie un chantier vaste et incertain en un graphe de tickets de décisions résolus un par un jusqu'à lever le brouillard.
  Use when the user asks to "wayfinder", "cartographier les décisions", "explorer ce grand projet", "clarifier la vision", or faces a huge foggy effort too large for a single session.
  When NOT to use: Do not use for well-scoped single-session features (use grill-with-docs) or immediate bug diagnosis (use diagnosing-bugs).
disable-model-invocation: true
---

# Wayfinder — Cartographie des Décisions pour Chantiers Complexes

Guide un projet de grande envergure enveloppé d'incertitude (trop volumineux pour une seule session) en cartographiant une **carte partagée de tickets de décisions** résolus pas à pas jusqu'à dégager la voie vers la destination.

## Planifier, pas implémenter

Wayfinder est un outil de **cadrage et de levée d'inconnues**. Chaque ticket correspond à une décision ou investigation à trancher, non à une tâche d'implémentation. Le but est d'éliminer le brouillard pour aboutir à une trajectoire claire pouvant être confiée à `/to-spec`.

## Processus

1. **Nommer la destination** : formuler en une ou deux phrases ce à quoi ressemble l'état final visé.
2. **Cartographier la frontière** :
   - Identifier les questions immédiatement tranchables (la frontière).
   - Consigner le reste dans la zone « Pas encore spécifié » (le brouillard).
3. **Résoudre un ticket de décision par session** :
   - Par recherche (`research`), prototype jetable (`prototype`), ou interview contradictoire (`grilling`).
   - Mettre à jour la carte et consigner les décisions validées dans `CONTEXT.md` / ADRs.
4. **Passer la main** : dès que le chemin est dégagé, basculer sur `/to-spec` puis `/to-tickets`.

## When NOT to use this skill

- Le besoin est déjà délimité et réalisable en une ou deux sessions → utiliser `/grill-with-docs`.
- Le besoin est prêt à être découpé en tranches de code → utiliser `/to-tickets`.
- La tâche consiste à exécuter directement le code d'un ticket → utiliser `/implement`.
