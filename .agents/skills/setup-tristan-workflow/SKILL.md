---
name: setup-tristan-workflow
description: >-
  Configure l'environnement de développement pour le flux d'ingénierie Tristan : initialise le suivi des tâches dans le vault Obsidian (ankiforge_obsidian/), les statuts de triage et la structure de domaine CONTEXT.md/ADRs.
  Use when the user asks to "setup-tristan-workflow", "configurer le workflow", "initialiser le tracker", or sets up the agent engineering environment.
  When NOT to use: Do not use if the Obsidian vault and CONTEXT.md are already initialised and operational.
disable-model-invocation: true
---

# Setup Tristan Workflow — Initialisation de l'Environnement Agent

Configure l'environnement du projet pour le flux d'ingénierie Tristan & AnkiForge :

- **Issue tracker natif** : le vault Obsidian (`ankiforge_obsidian/`) avec ses dossiers `Tickets/` et son tableau Kanban `Avancement du projet.md`.
- **Machine à états de triage** : les 5 statuts canoniques (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`).
- **Documentation de domaine** : `CONTEXT.md` à la racine et les décisions d'architecture dans `docs/adr/`.

## Configuration par défaut (AnkiForge)

Dans AnkiForge, l'environnement est configuré par défaut comme suit :
1. **Tracker** : Obsidian exclusivement. Tout ticket généré ou modifié passe par `ankiforge_obsidian/Tickets/<Type> - <Titre>.md` et s'insère dans `ankiforge_obsidian/Avancement du projet.md`.
2. **Contexte unique** : un unique `CONTEXT.md` racine et `docs/adr/`.
3. **Labels de triage** :
   - `needs-triage` (🟡 À évaluer)
   - `needs-info` (🟠 En attente d'infos)
   - `ready-for-agent` (🟢 Prêt pour Agent)
   - `ready-for-human` (🔵 Prêt pour Humain)
   - `wontfix` (⚪ Rejeté / Classé)

## When NOT to use this skill

- Ne pas utiliser si le vault Obsidian et `CONTEXT.md` sont déjà en place et fonctionnels (cas standard d'AnkiForge).
- Ne pas utiliser pour manipuler des tickets individuels → utiliser `obsidian-vault` ou `to-tickets`.
- Ne pas utiliser pour router une tâche → utiliser `ask-tristan`.
