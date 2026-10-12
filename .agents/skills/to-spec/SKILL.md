---
name: to-spec
description: >-
  Synthétise la discussion et le cadrage en cours en une spécification technique structurée prête pour le découpage en tickets Obsidian.
  Use when the user asks to "to-spec", "rédiger la spec", "spécifier", "synthétiser en spec", or wants to formalize a discussed plan into a full technical specification.
  When NOT to use: Do not use if the idea still needs sharpening (use grill-with-docs) or if you want tickets directly (use to-tickets).
disable-model-invocation: true
---

# To Spec — Synthèse en Spécification Technique

Transforme le fil de conception et la compréhension de la base de code en une **spécification technique formelle**. Aucune nouvelle interview n'est menée : il s'agit d'une synthèse directe de ce qui a déjà été arbitré.

Le document produit sert de base directe pour le découpage en tickets via **`/to-tickets`** dans le vault Obsidian (`ankiforge_obsidian/`).

## Processus

1. **Explorer le contexte** : réutiliser le glossaire `CONTEXT.md` et les ADRs applicables.
2. **Identifier les coutures (Seams)** : identifier le point d'intégration le plus haut possible pour tester le comportement de bout en bout.
3. **Rédiger la spécification** selon le gabarit canonique ci-dessous.

## Gabarit de Spécification

```markdown
## Problématique (Problem Statement)
Description du problème ou du besoin du point de vue de l'utilisateur.

## Solution proposée
Description synthétique de la réponse fonctionnelle et technique.

## User Stories (Extensives)
1. En tant que [rôle], je veux [action], afin de [bénéfice].
2. ...

## Décisions d'Implémentation
- Modules et interfaces touchés
- Schéma de base de données / migrations
- Contrats d'API et flux d'état
- Composants d'interface utilisateur

## Décisions de Test
- Stratégie de test aux coutures clés (tests unitaires, tests headless Qt)
- Précédents et fixtures existantes

## Hors Périmètre (Out of Scope)
Ce que cette spécification exclut délibérément.
```

## When NOT to use this skill

- Ne pas utiliser si des questions de conception restent ouvertes → utiliser `/grill-with-docs`.
- Ne pas utiliser pour découper directement en tickets de travail → utiliser `/to-tickets`.
- Ne pas utiliser pour implémenter du code immédiatement → utiliser `/implement`.
