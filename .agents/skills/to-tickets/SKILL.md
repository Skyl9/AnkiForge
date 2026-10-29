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
   **Fichiers Cibles :** `src/ankiforge/...`

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

2. **Insertion dans le Kanban** : Dans `ankiforge_obsidian/Avancement du projet.md`, insérer la carte sous la colonne `## 📋 Prêt pour Agent (Ready for Agent)` :
   `- [ ] [[Tickets/<NomFichierSansExt>|<Libellé Court>]] #tags <Emoji Priorité>`

3. **Règle anti-boucle** : Écrire le ticket, insérer la ligne dans le Kanban, puis s'arrêter immédiatement (One-shot pass). Ne jamais faire de relecture circulaire.

## When NOT to use this skill

- Ne pas utiliser pour rédiger une spécification fonctionnelle globale sans découpage unitaire → utiliser `/to-spec`.
- Ne pas utiliser si le plan ou la discussion est encore trop flou et que l'utilisateur hésite sur la direction → utiliser `/to-questionnaire` pour éclaircir les options avant tout découpage.
- Ne pas utiliser pour implémenter directement le code d'un ticket → utiliser `/implement`.
- Ne pas utiliser pour trier des retours bruts ou des bogues non qualifiés → utiliser `/triage`.
