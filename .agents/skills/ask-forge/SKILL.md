---
name: ask-forge
description: >-
  Aiguilleur de flux et routeur d'ingénierie pour AnkiForge. Oriente l'agent et le développeur vers le chemin optimal (idée, cadrage, spécification, tickets Obsidian, TDD, revue).
  Use when the user asks to "ask-forge", "quel skill", "quel flux", "comment aborder", "orienter la tâche", "router le ticket", or needs guidance on which skill or engineering flow to follow.
  When NOT to use: Do not use for implementing code directly (use implement) or debugging (use diagnosing-bugs).
disable-model-invocation: true
---

# Ask Forge — Routeur de Tickets et Flux d'Ingénierie AnkiForge

Tu ne peux pas mémoriser chaque compétence : consulte l'aiguilleur. **Le
Kanban Obsidian est la source de vérité du routage dès qu'un ticket existe.**
Ne commence pas par un parcours générique de conception si l'utilisateur
désigne une carte du Kanban ou un ticket existant.

## Point d'entrée obligatoire : ticket existant

1. Lire `ankiforge_obsidian/Avancement du projet.md`, identifier la carte
   ciblée et relever sa colonne.
2. Lire la note correspondante dans `Tickets/ticket-actif/` ou
   `Tickets/Archives/` avec le skill **`/obsidian-vault`**. Vérifier le statut,
   les prérequis et les critères d'acceptation.
3. Router vers **un seul prochain skill** selon l'état constaté :

| État Kanban / ticket | Skill à utiliser ensuite |
| --- | --- |
| `needs-triage` ou demande brute sans fiche | `/triage` |
| `needs-info` | Demander les informations manquantes, puis `/triage` |
| `ready-for-spec` | `/grill-with-docs` si des décisions restent ouvertes, sinon `/to-spec` |
| `ready-for-agent` | `/implement` |
| `in-progress` | Reprendre `/implement` sans recréer le cadrage |
| `ready-for-review` | `/code-review` |
| `ready-for-human` | Stopper et restituer l'action attendue de l'utilisateur |
| `done` ou `wontfix` | Ne pas relancer de travail ; restituer l'état |

Un ticket marqué `rechercher` ou relevant d'une investigation passe d'abord
par `/research`, après clarification du sujet, et jamais directement par
`/grill-with-docs`. La manipulation du ticket ou du Kanban reste du ressort de
`/obsidian-vault`, pas de ce routeur.

## Sortie attendue du routage

Restituer brièvement : le ticket détecté, son statut, ses prérequis bloquants,
le skill recommandé et la raison. Ne pas exécuter automatiquement plusieurs
skills en chaîne ; le skill recommandé devient la prochaine étape explicite.

Un **flux** est un parcours cohérent à travers les compétences. En l'absence
de ticket existant, la majorité des tâches empruntent le flux principal,
alimenté par deux rampes d'accès. Les autres compétences sont autonomes ou
constituent un socle de vocabulaire sous-jacent.

## Le flux principal : de l'idée à la livraison

Le trajet naturel d'une fonctionnalité ou d'une évolution :

1. **`/grill-with-docs`** : affûte l'idée par interview contradictoire. Point de départ dans le dépôt : c'est un processus avec persistance dans `CONTEXT.md` et les ADRs (`docs/adr/`). *(Exception formelle : si le ticket affiche « rechercher », interdiction de lancer `/grill-with-docs` tout de suite ; passer par la rampe `/research`).*
2. **Embranchement : peut-on trancher toutes les questions en discussion ?** Si une question nécessite une réponse exécutable (état complexe, règle métier incertaine, ergonomie d'UI), faire un détour par un prototype, relié par **`/handoff`** :
   - `/handoff` sortant vers un dossier isolé,
   - **`/prototype`** pour répondre avec du code jetable exploratoire,
   - `/handoff` rentrant pour intégrer les enseignements dans le fil de conception.
3. **Embranchement : est-ce un chantier multi-sessions ?**
   - **Oui** → **`/to-spec`** (synthétise la discussion en spécification), puis **`/to-tickets`** pour découper le travail en tranches verticales publiées directement dans `ankiforge_obsidian/Tickets/` et positionnées dans le Kanban `Avancement du projet.md`. Chaque ticket déclare ses blocages mutuels. Lancer ensuite **`/implement`** par ticket en nettoyant le contexte entre chaque unité (`/clear`).
   - **Non** → **`/implement`** directement dans le contexte courant.

Dans tous les cas, **`/implement`** s'appuie en interne sur **`/tdd`** (cycle red-green tranche par tranche), puis se conclut par une revue à deux axes **`/code-review`** (Conformité aux Standards + Respect de la Spécification) et la vérification canonique `uv run python script/verify.py`.

## Rampes d'accès

Situations initiales générant du travail avant d'intégrer le flux principal :

- **Demandes ou tickets bruts à qualifier** → **`/triage`**. Évalue les besoins arrivants, qualifie leur criticité et met à jour les fiches et colonnes du Kanban Obsidian (`ready-for-agent`, `needs-info`, `wontfix`).
- **Idée floue, hésitation sur la direction, dilemme technique ou fonctionnel** → **`/to-questionnaire`**. Clarifie et reformule la question vague, expose plusieurs perspectives argumentées et soumet un questionnaire interactif pour guider un choix éclairé, avant tout cadrage ou spécification.
- **Tickets ou besoins de recherche (« Rechercher »)** → **`/research`**. Pour tout ticket ou sujet affichant « rechercher » : **ne JAMAIS lancer `/grill-with-docs` tout de suite**. Demander le sujet précis de la recherche à l'utilisateur, rechercher et amener la documentation existante (via web et sources primaires) et l'adapter au besoin avant tout cadrage ultérieur.
- **Comportement cassé ou régression** → **`/diagnosing-bugs`**. Pour les anomalies résistantes : reproduction stricte en une commande rouge, isolation du composant et correction par test de non-régression.
- **Chantier exploratoire vaste ou brumeux** → **`/wayfinder`**. Pour les efforts de grande envergure : cartographie progressive des décisions avant de basculer sur `/to-spec`.

## Santé et architecture de la base de code

- **`/improve-codebase-architecture`** : identifie les opportunités de modularisation et de découplage pour maintenir la base de code fluide pour les agents. S'appuie sur le vocabulaire profond de **`/codebase-design`**.

## Socle de vocabulaire sous-jacent

- **`/domain-modeling`** : affine le modèle de domaine du projet, maintient le glossaire `CONTEXT.md` et documente les décisions structurantes dans `docs/adr/`.
- **`/codebase-design`** : vocabulaire de conception des modules profonds (interfaces compactes, coutures uniques, isolation des effets de bord).

## Compétences autonomes (Standalone)

- **`/resolving-merge-conflicts`** : résolution méthodique des conflits de fusion git par intention.
- **`/research`** : délégation d'investigation documentaire à un sous-agent avec rapport sourcé.
- **`/writing-for-agents`** : référence pour la rédaction de compétences et d'instructions agentiques.

## When NOT to use this skill

- Ne pas utiliser pour traiter un ticket affichant « rechercher » sans clarification préalable → utiliser directement `/research`.
- Ne pas utiliser pour coder directement une fonctionnalité → utiliser `/implement` ou `/tdd`.
- Ne pas utiliser pour diagnostiquer un bogue précis → utiliser `/diagnosing-bugs`.
- Ne pas utiliser pour manipuler manuellement le Kanban Obsidian sans routage → utiliser `obsidian-vault`.
