---
name: ask-forge
description: >-
  Aiguilleur de flux et routeur d'ingénierie pour AnkiForge. Oriente l'agent et le développeur vers le chemin optimal (idée, cadrage, spécification, tickets Obsidian, TDD, revue).
  Use when the user asks to "ask-forge", "quel skill", "quel flux", "comment aborder", "orienter la tâche", "router le ticket", or needs guidance on which skill or engineering flow to follow.
  When NOT to use: Do not use for implementing code directly (use implement) or debugging (use diagnosing-bugs).
disable-model-invocation: true
---

# Ask Forge — Flux d'Ingénierie AnkiForge

Tu ne peux pas mémoriser chaque compétence : consulte l'aiguilleur.

Un **flux** est un parcours cohérent à travers les compétences. La majorité des tâches empruntent le **flux principal**, alimenté par **deux rampes d'accès**. Les autres compétences sont autonomes ou constituent un socle de vocabulaire sous-jacent. Le gestionnaire de tickets et de suivi exclusif du projet est le vault Obsidian (`ankiforge_obsidian/`).

## Le flux principal : de l'idée à la livraison

Le trajet naturel d'une fonctionnalité ou d'une évolution :

1. **`/grill-with-docs`** : affûte l'idée par interview contradictoire. Point de départ dans le dépôt : c'est un processus avec persistance dans `CONTEXT.md` et les ADRs (`docs/adr/`).
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
- **Comportement cassé ou régression** → **`/diagnosing-bugs`**. Pour les anomalies résistantes : reproduction stricte en une commande rouge, isolation du composant et correction par test de non-régression.
- **Chantier exploratoire vaste ou brumeux** → **`/wayfinder`**. Pour les efforts de grande envergure : cartographie progressive des décisions avant de basculer sur `/to-spec`.

## Santé et architecture de la base de code

- **`/improve-codebase-architecture`** : identifie les opportunités de modularisation et de découplage pour maintenir la base de code fluide pour les agents. S'appuie sur le vocabulaire profond de **`/codebase-design`**.

## Socle de vocabulaire sous-jacent

- **`/domain-modeling`** : affine le modèle de domaine du projet, maintient le glossaire `CONTEXT.md` et documente les décisions structurantes dans `docs/adr/`.
- **`/codebase-design`** : vocabulaire de conception des modules profonds (interfaces compactes, coutures uniques, isolation des effets de bord).

## Compétences autonomes (Standalone)

- **`/grill-me`** : interview contradictoire stateless, réservée aux sessions hors dépôt / hors working directory.
- **`/resolving-merge-conflicts`** : résolution méthodique des conflits de fusion git par intention.
- **`/research`** : délégation d'investigation documentaire à un sous-agent avec rapport sourcé.
- **`/writing-for-agents`** : référence pour la rédaction de compétences et d'instructions agentiques.

## When NOT to use this skill

- Ne pas utiliser pour coder directement une fonctionnalité → utiliser `/implement` ou `/tdd`.
- Ne pas utiliser pour diagnostiquer un bogue précis → utiliser `/diagnosing-bugs`.
- Ne pas utiliser pour manipuler manuellement le Kanban Obsidian sans routage → utiliser `obsidian-vault`.
