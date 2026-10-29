---
name: triage
description: >-
  Qualifie et fait progresser les demandes, bogues et tickets dans la machine à états de triage du Kanban Obsidian (ankiforge_obsidian/).
  Use when the user asks to "triage", "trier les tickets", "qualifier une demande", "mettre à jour le statut du ticket", or wants to evaluate and categorize issues in Obsidian.
  When NOT to use: Do not use for tickets already marked ready-for-agent (use implement).
disable-model-invocation: true
---

# Triage — Qualification et Suivi des Demandes dans Obsidian

Gère et qualifie les demandes entrantes et les tickets à travers la machine à états de triage du vault **Obsidian** (`ankiforge_obsidian/Avancement du projet.md` et `ankiforge_obsidian/Tickets/`).

## Machine à états de triage

Deux catégories d'items :
- `bug` : anomalie ou régression.
- `enhancement` : évolution ou nouvelle fonctionnalité.

Neuf statuts de triage canoniques (détaillés dans `docs/agents/triage-labels.md`) :
- `needs-triage` : en attente d'évaluation technique.
- `needs-info` : en attente de précisions ou de reproduction.
- `ready-for-spec` : prêt pour cadrage ou rédaction de spécification.
- `ready-for-agent` : spécifié, autonome et prêt pour prise en charge par un agent.
- `ready-for-human` : nécessite une intervention humaine exclusive.
- `in-progress` : pris en charge et en cours de réalisation.
- `ready-for-review` : implémenté, en attente de revue ou validation.
- `done` : terminé, testé et livré.
- `wontfix` : demande rejetée ou classée sans suite.

Chaque ticket porte une catégorie, un statut de triage, ses `Prérequis`, sa `Difficulté` (T-shirt sizing `🟢 XS` à `🟣 XL`) et sa `Priorité`, synchronisés avec le tableau Kanban `Avancement du projet.md`.

## Procédure de triage dans Obsidian

1. **Identifier l'item à trier** :
   - Parcourir les tickets non qualifiés ou les colonnes en attente du Kanban `Avancement du projet.md`.
2. **Analyser le contexte technique** :
   - Lire la fiche de ticket `Tickets/<Nom>.md` si existante, ou analyser la demande utilisateur.
   - Vérifier si le comportement existe déjà dans la base de code pour éviter les doublons (`wontfix` si déjà implémenté).
3. **Vérifier les constats** :
   - Pour un bogue : tenter de reproduire avec une commande ciblée ou un test.
   - Pour une évolution : vérifier l'alignement avec les principes de `CONTEXT.md` et les ADRs.
4. **Appliquer la décision dans Obsidian** :
   - Mettre à jour l'en-tête canonique du ticket : `**Statut :** 🎯 Prêt pour Agent · ready-for-agent`, `**Prérequis :**`, `**Difficulté :** 🟢 S`, `**Priorité :**`.
   - Déplacer la carte correspondante dans le tableau Kanban `Avancement du projet.md`.
   - **Règle anti-boucle stricte** : effectuer la mise à jour en une seule passe atomique (One-shot pass), puis s'arrêter immédiatement sans relire le fichier.

## When NOT to use this skill

- Ne pas utiliser pour des tickets déjà marqués `ready-for-agent` → utiliser directement `/implement`.
- Ne pas utiliser pour découper une spécification validée en tranches de tickets → utiliser `/to-tickets`.
- Ne pas utiliser pour diagnostiquer un bogue complexe nécessitant une boucle TDD → utiliser `/diagnosing-bugs`.
- Si la demande brute est trop vague pour être qualifiée directement ou si l'utilisateur hésite sur la nature de la demande → utiliser d'abord `/to-questionnaire` pour clarifier, puis revenir à `/triage` pour qualifier le ticket.
