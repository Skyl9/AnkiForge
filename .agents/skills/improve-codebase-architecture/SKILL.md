---
name: improve-codebase-architecture
description: >-
  Scanne la base de code pour identifier les opportunités de modularisation profonde (deep modules), génère un rapport visuel HTML et cadre le refactoring choisi.
  Use when the user asks to "improve-codebase-architecture", "analyser l'architecture", "trouver des opportunités de refactoring", "deepen modules", or wants to survey architectural friction and deepening opportunities.
  When NOT to use: Do not use for immediate bug fixing (use diagnosing-bugs) or implementing already specified tickets (use implement).
disable-model-invocation: true
---

# Improve Codebase Architecture

Identifie les frictions architecturales et propose des **opportunités de modularisation profonde** : des refactorisations qui transforment des modules superficiels (shallow) en modules profonds (deep modules) avec une forte localité et un effet de levier pour les appelants.

## Vocabulaire & Principes

- S'appuie sur le vocabulaire formel de **`codebase-design`** (**module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**).
- Utilise le glossaire de domaine `CONTEXT.md` et respecte les ADRs enregistrés dans `docs/adr/`.

## Processus

1. **Explorer avec discernement** :
   - Cibler en priorité les zones du code fréquemment modifiées dans l'historique git récent (`git log --oneline`).
   - Détecter les modules superficiels (interface presque aussi complexe que l'implémentation), les fuites à travers les coutures et les zones difficiles à tester.
   - Appliquer le test de suppression (deletion test).
2. **Présenter les candidats via un rapport HTML visuel** :
   - Écrire un fichier HTML autonome dans le dossier temporaire de l'OS (`/tmp/architecture-review-<timestamp>.html`).
   - Intégrer des schémas comparatifs Mermaid (Avant / Après) et des fiches structurées.
   - Ouvrir automatiquement le rapport pour l'utilisateur.
3. **Boucle d'affûtage (Grilling)** :
   - Dès que l'utilisateur sélectionne un axe, dérouler `grilling` et `domain-modeling` pour concevoir la nouvelle interface et consigner d'éventuels ADRs.

## When NOT to use this skill

- Ne pas utiliser pour corriger une régression ou un bogue identifié → utiliser `/diagnosing-bugs`.
- Ne pas utiliser pour implémenter un ticket déjà spécifié → utiliser `/implement`.
- Ne pas utiliser pour simplifier localement une fonction sans impact architectural → utiliser `/code-simplification`.
