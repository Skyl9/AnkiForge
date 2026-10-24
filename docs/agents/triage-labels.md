# Triage Labels & Cycle de Vie des Tickets Obsidian

Les skills et agents d'AnkiForge s'articulent autour d'une machine à états de triage canonique. Ce document définit la correspondance entre les rôles de triage et la structure formelle des tickets dans le traqueur **Obsidian** (`ankiforge_obsidian/Tickets/` et `ankiforge_obsidian/Avancement du projet.md`).

Le traqueur n'utilise pas de labels natifs d'une forge distante (GitHub/GitLab) : l'état est matérialisé par l'en-tête `**Statut :**` de chaque note de ticket et sa position dans les colonnes du Kanban `Avancement du projet.md`.

---

## 1. Les 9 Rôles de Triage Canoniques

| Rôle technique (`triage-role`) | Valeur d'en-tête recommandée (`Statut :`) | Colonne Kanban associée | Description & Usage |
| :--- | :--- | :--- | :--- |
| `needs-triage` | `📥 Backlog & Idées · needs-triage` | `## 📥 Backlog & Idées (needs-triage)` | Demande brute, idée ou retour utilisateur à qualifier. |
| `needs-info` | `🔎 En Attente d'Infos · needs-info` | `## 🔎 En Attente d'Infos (needs-info)` | Demande en attente de précisions, de données de test ou de reproduction. |
| `ready-for-spec` | `🎯 Prêt pour Spécification · ready-for-spec` | `## 📥 Backlog & Idées (needs-triage)` ou section dédiée | Cadré conceptuellement mais nécessitant une interview d'architecture (`/grill-with-docs`) ou une spec détaillée (`/to-spec`). |
| `ready-for-agent` | `🎯 Prêt pour Agent · ready-for-agent` | `## 🐞 Bugs · Prêts pour Agent` / `## 🚀 Features · Prêtes pour Agent` / Colonnes thématiques | Ticket entièrement spécifié, autonome et prêt pour prise en charge directe par `/implement` ou `/tdd`. |
| `ready-for-human` | `👤 À faire humain · ready-for-human` | `## 👤 À faire humain (ready-for-human)` | Nécessite un jugement ou une intervention humaine exclusive (traductions littéraires manuelles, décisions stratégiques, audit visuel réel). |
| `in-progress` | `⚙️ En Cours · in-progress` | `## ⚙️ En Cours` | Ticket activement pris en charge par un agent ou l'utilisateur. |
| `ready-for-review` | `👀 En Revue · ready-for-review` | `## ⚙️ En Cours` (ou colonne d'arbitrage) | Implémenté et testé, en attente de contre-revue (`/code-review`) ou de validation humaine finale. |
| `done` | `✅ Terminé · done` | `## ✅ Terminé (Fonctionnalités Livrées)` | Livré, testé (porte de vérification passée) et committé. |
| `wontfix` | `🚫 Classé sans suite · wontfix` | `## 🗑️ Abandonné` | Rejeté, classé sans suite, rendu obsolète par un refactoring ou doublon. |

---

## 2. Échelle de Difficulté (T-Shirt Sizing)

Chaque ticket spécifié déclare son niveau d'effort estimé via le champ `**Difficulté :**` selon l'échelle normalisée :

- `🟢 XS` : Trivial (modification de quelques lignes, renommage, fix CSS ponctuel, < 15 min).
- `🟢 S` : Court (tâche ciblée et bornée, test unitaire simple, < 1h).
- `🟡 M` : Moyen (tranche verticale standard, service + widget + tests, 1-2h).
- `🔴 L` : Lourd (refactoring transversal, nouveau sous-système, plusieurs composants interconnectés).
- `🟣 XL` : Épic à découper (trop vaste pour une seule session, doit être scindé via `/to-tickets`).

---

## 3. Format Canonique de l'En-Tête de Ticket

Tout ticket sous `ankiforge_obsidian/Tickets/<Nom>.md` doit respecter strictement cet ordre de métadonnées :

```markdown
# <Type> — <Titre du Ticket>

**Statut :** 🎯 Prêt pour Agent · ready-for-agent
**Prérequis :** Aucun | [[Tickets/<NomDuTicketBloquant>]]
**Difficulté :** 🟡 M
**Priorité :** 🔴 P0 (bloquant) / 🟡 P1 (important) / 🟢 P2 (standard) / ⚪ P3 (confort)
**Piliers & Modules :** <Module Principal> / <Sous-module>
**Lien Tableau :** [[Avancement du projet]]
**Fichiers Cibles :** `src/ankiforge/...`

---

## 🎯 Contexte
...
```

Quand un skill mentionne un rôle (ex. « applique le label prêt-agent »), toujours écrire la forme complète bivalente :
`**Statut :** 🎯 Prêt pour Agent · ready-for-agent`.
