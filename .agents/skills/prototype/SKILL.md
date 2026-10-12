---
name: prototype
description: >-
  Construit un prototype jetable pour trancher une question de conception (modèle d'état, logique complexe ou variante d'interface utilisateur).
  Use when the user asks to "prototyper", "faire un prototype", "tester l'idée en code", "prototype", or wants to validate logic or UI feasibility before final implementation.
  When NOT to use: Do not use for writing production code (use implement) or settling questions purely through discussion (use grill-with-docs).
---

# Prototype — Exploration par Code Jetable

Un prototype est **du code jetable conçu pour répondre à une question de conception précise**. La question dicte la forme de l'artefact.

## Deux Orientations

1. **« Cette logique ou ce modèle d'état est-il viable ? »** : Construire un fichier HTML/JS autonome ou un script Python isolé simulant la machine à états et permettant de tester les cas limites interactifs.
2. **« À quoi doit ressembler cette interface ? »** : Générer des maquettes rapides comparatives sur une route ou vue de test, sans persistance définitive.

## Règles Cardinales

1. **Jetable dès le premier jour** : clairement documenté comme jetable, situé à proximité du module ou dans un dossier scratch (`.scratch/`).
2. **Trivial à exécuter** : une seule commande pour le lancer.
3. **Sans persistance par défaut** : l'état vit en mémoire ou dans une base SQLite éphémère.
4. **Zéro sur-ingénierie** : pas de couverture de tests formelle ni d'abstractions complexes sur le prototype.
5. **Capitaliser les enseignements** : une fois la question tranchée, réintégrer la décision dans le code réel ou la spécification, puis supprimer ou archiver le prototype.

## When NOT to use this skill

- La question peut être tranchée directement en discussion conceptuelle sans code → utiliser `/grill-with-docs`.
- Le besoin est d'implémenter du code pérenne destiné à la production → utiliser `/implement` ou `/tdd`.
- La tâche consiste à déboguer une régression sur du code existant → utiliser `/diagnosing-bugs`.
