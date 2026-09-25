# Issue tracker: Obsidian Kanban

Issues et specs de ce repo vivent dans le vault Obsidian `ankiforge_obsidian/` du repository Git (`Skyl9/AnkiForge`). `gh`, `.scratch/` et GitLab **ne sont pas** utilisés.

> **Important (Séparation des Rôles & Anti-Boucle) :**
> - **Obsidian = Issue Tracker / Todo List uniquement** : Géré via le skill `.agents/skills/obsidian-vault/SKILL.md`.
> - **La vraie documentation vit dans Zensical** (`docs/`, `zensical.toml`) et est committée dans le dépôt principal. Le vault Obsidian ne doit plus héberger de documentation pérenne.
> - **Règle d'or One-Shot Action & Stop** : Ne jamais relire le Kanban après écriture, ne jamais toucher au bloc `%% kanban:settings`, et s'arrêter immédiatement après la mise à jour atomique d'un ticket/kanban.

## Conventions

- **Un ticket = une note markdown** : `ankiforge_obsidian/Tickets/<Nom>.md`, avec les en-têtes :
  - `**Statut :**` (état du ticket, voir `triage-labels.md` pour les rôles de triage)
  - `**Priorité :**` (🟡 P1 / 🟢 P2 / …)
  - `**Piliers & Modules :**`
  - `**Lien Tableau :**` `[[Avancement du projet]]`
  - `**Fichiers Cibles :**` (chemins `src/...` visés)
  - puis les sections `## 🎯 Contexte`, `## 🔍 Constats (Analyse de code)`, `## 👤 User Story`, `## 📋 Critères d'Acceptation`.
- **Le tableau Kanban** est `ankiforge_obsidian/Avancement du projet.md` (note Obsidian `kanban-plugin: board`). Chaque ticket y est référencé par une ligne cochable dans la colonne de son statut, au format `- [ ] [[Tickets/<Nom>|<Libellé>]] #tags ⚡priorité`.
- Les commentaires / conversations s'appendent en bas de la note sous `## Comments`.

## Quand un skill dit « publier vers le traqueur d'issues »

Créer (ou éditer) la note `ankiforge_obsidian/Tickets/<Nom>.md` dans ce format, puis ajouter/mettre à jour la ligne liée dans la colonne correspondante du kanban (`Avancement du projet.md`).

## Quand un skill dit « récupérer le ticket concerné »

Lire la note au chemin indiqué. L'utilisateur passera normalement le chemin ou le nom du ticket directement.

## Surface de requête PR

Inactive : les PR externes ne passent pas par la file de triage.
