---
name: obsidian-vault
description: Gère et synchronise le suivi des tâches dans le vault Obsidian (ankiforge_obsidian/), le Kanban (Avancement du projet.md) et les tickets sans boucle infinie. Use when creating, updating, moving, or referencing Obsidian tickets, manipulating the Kanban board, or triaging issues in the vault.
---

# Obsidian Vault & Kanban Manager

Ce skill régit l'utilisation du vault `ankiforge_obsidian/` comme **gestionnaire de tâches et de tickets (Issue Tracker)** exclusif pour AnkiForge.

## 🧭 Règle Fondamentale : Todo List, pas Documentation

- **Obsidian = Issue Tracker / Todo List** : Le vault sert uniquement à suivre l'avancement, les tickets (`Tickets/`) et le tableau Kanban (`Avancement du projet.md`).
- **Scission Physique des Dossiers de Tickets** :
  - `Tickets/ticket-actif/` : Héberge exclusivement les tickets actifs (`needs-info`, `ready-for-spec`, `ready-for-agent`, `ready-for-human`, `in-progress`, `ready-for-review`).
  - `Tickets/Archives/` : Héberge la totalité des tickets terminés ou abandonnés (`done`, `wontfix`).
  - La racine `Tickets/` ne doit **JAMAIS** héberger de tickets à plat.
- **Interdiction Absolue des Slashes dans les Noms de Fichiers et Wikilinks (T-35)** : Ne JAMAIS inclure de barre oblique (`/`), d'anti-slash (`\`) ou de deux-points (`:`) dans le nom d'un fichier Markdown de ticket (`Tickets/.../<Nom>.md`) ou dans la cible d'un lien Obsidian (`[[...]]`). Sous Unix/macOS, le caractère `/` scinde le chemin de fichier et crée accidentellement un sous-répertoire parasite non valide. Remplacer systématiquement les barres obliques par un tiret (`-`) ou une virgule.
- **Garde-Fou Anti-Fichiers Fantômes (Cache Obsidian Desktop)** : Lors d'un déplacement de fichier de ticket, si l'application Obsidian est active en mémoire sur l'hôte, elle peut recréer un fichier vide de 0 octet à l'ancien emplacement. Toujours vérifier l'absence de fichiers résiduels de 0 octet à la racine de `Tickets/` après déplacement.
- **Sous-Dépôt Git Autonome** : Le dossier `ankiforge_obsidian/` constitue son **propre dépôt Git indépendant** (avec son propre dossier `.git/`), ignoré par le `.gitignore` du dépôt racine AnkiForge. Les modifications du vault doivent faire l'objet de commits distincts dans `ankiforge_obsidian/` et ne sont jamais captées par un commit à la racine.
- **La vraie documentation vit dans Zensical** : Toute documentation d'architecture, guide technique ou spécification pérenne doit être rédigée dans `docs/` (`zensical.toml`) et committée dans le dépôt Git principal.
- **Nettoyage du vault** : Les anciennes notes documentaires présentes à la racine du vault (ex. `Objectif du projet.md`, `Ankiforge Analise et audit.md`) sont obsolètes/legacy et ne doivent pas servir de référence documentaire. Ne pas y ajouter de nouvelle documentation.

## 🛡️ Règle d'Or Anti-Écrasement Concurrent & Anti-Boucle (One-Shot Action & Stop)

Les agents risquent d'écraser des colonnes réorganisées par l'utilisateur ou de boucler indéfiniment en relisant leurs modifications. Les garde-fous stricts suivants s'appliquent :

1. **Édition Chirurgicale Mono-Ligne Obligatoire** :
   - Ne JAMAIS remplacer de blocs multi-colonnes ou des sections entières de `Avancement du projet.md`.
   - Toujours effectuer un ciblage strict d'une seule ligne à supprimer et d'une seule ligne à insérer.
   - Ne jamais écraser ou déplacer les tickets modifiés ou créés en parallèle par l'utilisateur.
   - **Garde-fou anti-rejet d'espacement (`edit_file`)** : Les fichiers Markdown vivants accumulent souvent des sauts de lignes consécutifs (`\n\n\n`). Ne jamais inclure d'espaces inter-sections dans `Target`. Procéder en deux remplacements mono-lignes distincts :
     1. Retrait de l'élément de sa colonne d'origine : `Target: "- [ ] [[...]]\n"`, `Replacement: ""`.
     2. Insertion sous le titre de destination : `Target: "## <Colonne Cible>\n\n"`, `Replacement: "## <Colonne Cible>\n\n- [ ] [[...]]\n"`.
     En cas d'échec de correspondance exacte dû au formattage d'espaces, recourir immédiatement à une substitution Python chirurgicale.
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

## 📋 Format Canonique d'un Ticket (`Tickets/ticket-actif/<Nom>.md`)

Toute création ou modification de ticket actif respecte cette structure et se situe obligatoirement sous `Tickets/ticket-actif/` (ou `Tickets/Archives/` une fois clos) :

```markdown
# <Type> — <Titre Explicite>

**Statut :** <Emoji> <Libellé> · <triage-role>
**Prérequis :** Aucun | [[Tickets/ticket-actif/<NomDuTicketBloquant>]]
**Difficulté :** 🟢 XS / 🟢 S / 🟡 M / 🔴 L / 🟣 XL
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

**Rôles de triage (`triage-role`)** : `needs-triage`, `needs-info`, `ready-for-spec`, `ready-for-agent`, `ready-for-human`, `in-progress`, `ready-for-review`, `done`, `wontfix` (voir `docs/agents/triage-labels.md`).

## ⛔ Critères d'Éligibilité aux Statuts de Triage

Avant d'assigner un statut à un ticket, l'agent **DOIT** vérifier que le ticket remplit les conditions suivantes :

| Statut | Condition obligatoire |
| :--- | :--- |
| `ready-for-agent` | Aucun point ouvert, aucune question en attente, aucun critère d'acceptation non tranché. Le ticket est autonome et immédiatement implémentable. |
| `needs-info` | Au moins une question en attente, un point ouvert ou un arbitrage non tranché bloquant l'implémentation. |
| `ready-for-spec` | Le besoin est cadré conceptuellement mais nécessite une spécification détaillée ou une interview d'architecture. |
| `ready-for-human` | Nécessite un jugement ou une intervention humaine exclusive (décision stratégique, traduction littéraire, audit visuel réel). |
| `in-progress` | Le ticket est activement pris en charge par un agent ou l'utilisateur. |

**Garde-fou bloquant (GF-OV-1)** : Il est formellement INTERDIT d'assigner le statut `ready-for-agent` à un ticket qui comporte un point ouvert, une question en attente ou un critère d'acceptation non tranché (ex: choix de moteur math, politique de sanitiseur HTML, comportement par défaut non défini). Dans ce cas, le statut doit être `needs-info` jusqu'à résolution de l'arbitrage par l'utilisateur. Le champ `Comments` du ticket peut documenter le point ouvert, mais cela ne le rend pas éligible à `ready-for-agent`.

## 📌 Format d'une Entrée Kanban (`Avancement du projet.md`)

- **Tâche active (à faire / en cours / en attente / en revue) :**
  `- [ ] [[Tickets/ticket-actif/<NomFichierSansExt>|<Libellé Court>]] #tags <Emoji Priorité>`
- **Tâche terminée ou abandonnée (récente) :**
  `- [x] [[Tickets/Archives/<NomFichierSansExt>|<Libellé Court>]] #tags <Emoji Priorité>`
- Déplacer une carte consiste à **supprimer la ligne de son ancienne colonne** et à **l'insérer dans la nouvelle colonne**, sans altérer l'indentation ni les autres éléments. Lors du passage d'une tâche à l'état `done` ou `wontfix`, déplacer également le fichier de `Tickets/ticket-actif/` vers `Tickets/Archives/`.
- **Déplacement atomique entre colonnes :** supprimer impérativement la ligne de sa colonne d'origine AVANT de l'insérer dans la colonne de destination. Interdiction formelle d'insérer dans la destination avant le retrait de la source, ce qui créerait un doublon de carte dans le Kanban.

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
