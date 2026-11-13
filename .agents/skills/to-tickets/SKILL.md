---
name: to-tickets
description: >-
  Découpe un plan, une spécification ou une discussion en tickets traceurs verticaux avec dépendances de blocage, publiés directement dans le vault Obsidian (ankiforge_obsidian/Tickets/) et positionnés sur le Kanban Avancement du projet.md.
  Use when the user asks to "to-tickets", "découper en tickets", "créer les tickets", "découper en tâches", or wants to slice a plan into tracer-bullet issues for Obsidian.
  When NOT to use: Do not use for writing a single high-level spec without ticket breakdown (use to-spec).
disable-model-invocation: true
---

# To Tickets — Découpage en Tickets Traceurs Obsidian

Découpe un plan, une spécification ou un fil de conception en **tickets traceurs verticaux** (tracer bullets), chacun déclarant ses dépendances de blocage mutuelles.

Le gestionnaire de tickets cible exclusif est le vault **Obsidian** (`ankiforge_obsidian/Tickets/` et `ankiforge_obsidian/Avancement du projet.md`).

## Processus de découpage

### 1. Rassembler le contexte
Analyser la discussion en cours, la spécification ou les retours d'interview (`grill-with-docs`). Utiliser le glossaire de domaine `CONTEXT.md` et respecter les ADRs existants.

### 1 bis. Dé-jargonisation et Ancrage Réel via Sous-Agent d'Investigation (Obligatoire si volumineux, flou ou jargonneux)

Si la tâche répond à **au moins l'un** de ces trois critères :
1. **Volumineuse** : traverse $\ge 3$ fichiers/services, introduit de nouveaux modèles/outils ou scinde une épique de priorité $\ge \text{P1}$ ;
2. **Plutôt mal définie** : heuristiques de calcul approximatives, formats d'erreur omis, gestion des doublons ou d'idempotence non tranchée ;
3. **Très jargonneuse** : mobilise des concepts denses du domaine (RAG, Smart Coverage, FastMCP, Two-Phase Commit, Staged Bundles, règles Wozniak, FTS5 BM25, adresses de région ADR 0010, etc.) ;

L'agent **DOIT impérativement instancier un sous-agent d'investigation** (`invoke_subagent` avec le rôle `Ticket Grounding & Reality Checker`) avant toute rédaction de ticket :

- **1. Contrôle d'existence et de signature réelle (Codebase Reality Check)** : Le sous-agent inspecte le code réel pour vérifier chaque classe, méthode, outil MCP ou constante mentionné. **Interdiction formelle de supposer une API de mémoire** (ex: vérifier la signature réelle de `find_duplicate_cards`, la méthode canonique de ré-indexation `reindex_document`, et la fonction de notification de mutation `_notify_mcp_mutation`).
- **2. Éradication du jargon magique** : Remplacer chaque formule séduisante mais floue par un contrat déterministe (seuils mathématiques précis pour les verdicts, assainissement HTML/cloze explicite, formules de décompte chiffrées).
- **3. Validation de la chaîne d'architecture du dépôt** : Identifier l'ensemble des fichiers devant être modifiés de concert (ex: pour tout outil FastMCP `@mcp.tool()`, synchroniser la triade `mcp_server.py` + `mcp_tool_registry.py` + `mcp_tool_catalog_widget.py` + assertions de décompte dans les tests).
- **4. Stress-test des hypothèses (`/doubt-driven-development`)** : Évaluer le nombre de suppositions techniques non prouvées ; si $\ge 2$ éléments restent obscurs, instruire les doutes avant de figer les tickets.
- **5. Matrice d'ordonnancement & Garde-fou GF-TT-1** : Ordonnancer strictement le graphe de dépendances. **Interdiction absolue d'assigner `ready-for-agent` à un ticket qui dépend d'un autre ticket non encore fusionné.**

### 2. Définir des tranches verticales (Tracer Bullets)
Chaque ticket doit respecter les règles suivantes :
- **Tranche verticale complète** : traverse chaque couche nécessaire (modèle, service/logique, interface Qt, tests), jamais un découpage horizontal en silos.
- **Autonome et vérifiable** : chaque tranche est testable et démontrable isolément.
- **Taille adaptée** : calibrée pour être traitée dans une seule fenêtre de contexte propre par `/implement`.
- **Déclaration des blocages** : indiquer les tickets préalables indispensables. Un ticket sans bloquant peut être démarré immédiatement.

### 3. Soumettre le découpage à l'utilisateur
Présenter la liste ordonnée des tickets proposés :
- **Titre** : explicite et concis.
- **Bloqué par** : tickets prérequis indispensables.
- **Comportement livré** : ce que la tranche rend fonctionnel de bout en bout.
- Valider la granularité avec l'utilisateur avant publication.

### 4. Publication directe dans le Vault Obsidian
Une fois validé, publier chaque ticket **directement** dans le vault Obsidian selon le format canonique :

1. **Création de la note de ticket** : `ankiforge_obsidian/Tickets/<Type> - <Titre>.md`
   ```markdown
   # <Type> — <Titre Explicite>

   **Statut :** 🎯 Prêt pour Agent · ready-for-agent
   **Prérequis :** Aucun | [[Tickets/<Bloquant>]]
   **Difficulté :** 🟢 XS / 🟢 S / 🟡 M / 🔴 L / 🟣 XL
   **Priorité :** 🔴 P0 / 🟡 P1 / 🟢 P2 / ⚪ P3
   **Piliers & Modules :** <Module> / <Sous-module>
   **Lien Tableau :** [[Avancement du projet]]
   **Fichiers Cibles :** `src/ankidraft/...`

   ---

   ## 🎯 Contexte
   Description concise du problème ou besoin.

   ## 🔍 Constats (Analyse de code)
   Classes, méthodes et fichiers inspectés.

   ## 👤 User Story
   **En tant qu'** utilisateur / développeur,
   **Je veux** [action attendue],
   **Afin d'** [bénéfice mesurable].

   ## 📋 Critères d'Acceptation
   - [ ] Critère vérifiable 1
   - [ ] Critère vérifiable 2

   ## 🧱 Bloqué par
   - [[Tickets/<Bloquant>|<Titre Bloquant>]] ou "Aucun (démarrage immédiat)"

   ## Comments
   Historique et notes d'exécution.
   ```

2. **Insertion dans le Kanban** :
   - Si le ticket n'a **aucun bloquant** et est immédiatement codable : insérer la carte sous la colonne `## 🚀 Prêt pour Agent (ready-for-agent)`.
   - Si le ticket est **bloqué par un prérequis non terminé** : insérer la carte sous `## 📥 Backlog & Idées (needs-triage)` ou `## 🔎 En Attente d'Infos (needs-info)` avec le tag du bloquant.
   `- [ ] [[Tickets/ticket-actif/<NomFichierSansExt>|<Libellé Court>]] #tags <Emoji Priorité>`

3. **Règle anti-boucle** : Écrire le ticket, insérer la ligne dans le Kanban, puis s'arrêter immédiatement (One-shot pass). Ne jamais faire de relecture circulaire.

## When NOT to use this skill

- **Interdiction de sur-découpage (anti-dispersion)** : Ne JAMAIS découper une tâche, un correctif ou une évolution qui peut être conçue, réalisée et testée dans une seule session de développement (tailles `🟢 XS`, `🟢 S`, `🟡 M`). Ce skill est réservé exclusivement à la scission d'épiques complexes (`🟣 XL`) dépassant la fenêtre de contexte d'une session.
- Ne pas utiliser pour rédiger une spécification fonctionnelle globale sans découpage unitaire → utiliser `/to-spec`.
- Ne pas utiliser si le plan ou la discussion est encore trop flou et que l'utilisateur hésite sur la direction → utiliser `/to-questionnaire` pour éclaircir les options avant tout découpage.
- Ne pas utiliser pour implémenter directement le code d'un ticket → utiliser `/implement`.
- Ne pas utiliser pour trier des retours bruts ou des bogues non qualifiés → utiliser `/triage`.
