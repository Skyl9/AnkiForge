---
name: obsidian-vault
description: Gère et synchronise le suivi des tâches dans le vault Obsidian (ankiforge_obsidian/), le Kanban (Avancement du projet.md) et les tickets sans boucle infinie. Use when creating, updating, moving, or referencing Obsidian tickets, manipulating the Kanban board, or triaging issues in the vault.
---

# Obsidian Vault & Kanban Manager

Ce skill régit l'utilisation du vault `ankiforge_obsidian/` comme **gestionnaire de tâches et de tickets (Issue Tracker)** exclusif pour AnkiForge.

## 🧭 Règle Fondamentale : Todo List, pas Documentation

- **Obsidian = Issue Tracker / Todo List** : Le vault sert uniquement à suivre l'avancement, les tickets (`Tickets/`) et le tableau Kanban (`Avancement du projet.md`).
- **Sous-Dépôt Git Autonome** : Le dossier `ankiforge_obsidian/` constitue son **propre dépôt Git indépendant** (avec son propre dossier `.git/`), ignoré par le `.gitignore` du dépôt racine AnkiForge. Les modifications du vault doivent faire l'objet de commits distincts dans `ankiforge_obsidian/` et ne sont jamais captées par un commit à la racine.
- **La vraie documentation vit dans Zensical** : Toute documentation d'architecture, guide technique ou spécification pérenne doit être rédigée dans `docs/` (`zensical.toml`) et committée dans le dépôt Git principal.
- **Nettoyage du vault** : Les anciennes notes documentaires présentes à la racine du vault (ex. `Objectif du projet.md`, `Ankiforge Analise et audit.md`) sont obsolètes/legacy et ne doivent pas servir de référence documentaire. Ne pas y ajouter de nouvelle documentation.

## 🛡️ Règle d'Or Anti-Écrasement Concurrent & Anti-Boucle (One-Shot Action & Stop)

Les agents risquent d'écraser des colonnes réorganisées par l'utilisateur ou de boucler indéfiniment en relisant leurs modifications. Les garde-fous stricts suivants s'appliquent :

1. **Édition Chirurgicale Mono-Ligne Obligatoire** :
   - Ne JAMAIS remplacer de blocs multi-colonnes ou des sections entières de `Avancement du projet.md`.
   - Toujours effectuer un ciblage strict d'une seule ligne à supprimer et d'une seule ligne à insérer.
   - Ne jamais écraser ou déplacer les tickets modifiés ou créés en parallèle par l'utilisateur.
2. **Cycle Atomique Strict (One-Shot Pass)** :
   - Étape 1 : Lire la note ciblée (`Tickets/<Nom>.md`) ou la section précise du Kanban.
   - Étape 2 : Modifier ou créer la note du ticket.
   - Étape 3 : Insérer ou déplacer la ligne correspondante dans `Avancement du projet.md`.
   - Étape 4 : **ARRÊT IMMÉDIAT (STOP)**. Terminer le tour et notifier l'utilisateur.
3. **Zéro Auto-Vérification Circulaire** : Ne JAMAIS relire le Kanban ou le ticket après l'écriture pour « vérifier » que la modification a pris. Le retour de l'outil d'écriture fait foi.
4. **Protection du Bloc Technique** : Ne JAMAIS modifier, reformater ou supprimer le bloc de configuration en bas de `Avancement du projet.md` :
   ```markdown
   %% kanban:settings
   ```...```
   %%
   ```
5. **Pas de Traitement en Rafale Silencieux** : Traiter exactement le ou les tickets demandés. Ne jamais enchaîner de manière autonome sur « le ticket suivant » de la colonne sans ordre explicite de l'utilisateur.

## 📋 Format Canonique d'un Ticket (`Tickets/<Nom>.md`)

Toute création ou modification de ticket respecte cette structure :

```markdown
# <Type> — <Titre Explicite>

**Statut :** <Emoji> <Libellé> · <triage-role>
**Priorité :** 🔴 P0 / 🟡 P1 / 🟢 P2 / ⚪ P3
**Piliers & Modules :** <Module Principal> / <Sous-module>
**Lien Tableau :** [[Avancement du projet]]
**Fichiers Cibles :** `src/ankiforge/...`

---

## 🎯 Contexte
Description concise du problème ou du besoin.

## 🔍 Constats (Analyse de code)
Faits vérifiés dans le code, classes, méthodes ou fichiers concernés.

## 👤 User Story
**En tant qu'** utilisateur / développeur,
**Je veux** [action attendue],
**Afin d'** [bénéfice mesurable].

## 📋 Critères d'Acceptation
- [ ] Critère 1 vérifiable
- [ ] Critère 2 vérifiable

## Comments
Historique des échanges ou retours d'exécution.
```

**Rôles de triage (`triage-role`)** : `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.

## 📌 Format d'une Entrée Kanban (`Avancement du projet.md`)

- **Tâche à faire / en cours :**
  `- [ ] [[Tickets/<NomFichierSansExt>|<Libellé Court>]] #tags <Emoji Priorité>`
- **Tâche terminée :**
  `- [x] [[Tickets/<NomFichierSansExt>|<Libellé Court>]] #tags <Emoji Priorité>`
- Déplacer une carte consiste à **supprimer la ligne de son ancienne colonne** et à **l'insérer dans la nouvelle colonne**, sans altérer l'indentation ni les autres éléments.

## 📦 Politique d'Archivage des Livraisons

Pour éviter d'alourdir le tableau Kanban actif `Avancement du projet.md` (qui consomme du contexte et ralentit chaque lecture par l'agent) :

1. **Rétention active dans le Kanban** : La colonne `## ✅ Terminé (Fonctionnalités Livrées)` ne conserve que les livraisons récentes du sprint en cours (~10 à 15 items maximum) et affiche en tête le lien vers l'archive :
   `- [x] 📦 [[Archives - Tickets Terminés|Consulter l'archive des fonctionnalités et tickets livrés antérieurs]]`
2. **Registre d'Archives (`Archives - Tickets Terminés.md`)** : Toutes les livraisons plus anciennes sont transférées dans `ankiforge_obsidian/Archives - Tickets Terminés.md`.
3. **Règle d'Archivage** : Lorsque la colonne `Terminé` du Kanban accumule trop de cartes, transférer les plus anciennes vers `Archives - Tickets Terminés.md` pour maintenir `Avancement du projet.md` sous la barre des 120 lignes.

## ⛔ Ne PAS utiliser ce skill si...

- La tâche consiste à rédiger ou modifier de la documentation générale d'AnkiForge : utiliser le skill `documentation-zensical` dans `docs/`.
- La tâche consiste à implémenter du code source sans rapport avec le suivi de projet : utiliser `implement` ou les compétences de dev spécifiques.
- La tâche consiste à auditer la conformité du code Python/Qt : utiliser `audit-qualite-code` ou `audit-ankiforge`.
