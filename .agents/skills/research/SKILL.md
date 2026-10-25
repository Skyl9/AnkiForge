---
name: research
description: >-
  Investigation documentaire et recherche pour AnkiForge. Sur un ticket « rechercher », interdit tout grill-with-docs prématuré, clarifie le sujet précis, effectue la recherche web et apporte la documentation existante adaptée au besoin. Couvre aussi l'analyse approfondie par sous-agent.
  Use when the user asks to "rechercher", "investiguer", "documenter les options", "research", or when a ticket displays "rechercher".
  When NOT to use: Do not use for quick targeted lookups you can do yourself in one turn or for coding directly (use implement).
---

# Research — Investigation Documentaire, Recherche Web & État de l'Art

Ce skill régit la conduite des recherches documentaires, l'exploration de l'état de l'art et l'analyse de sources fiables pour AnkiForge, en direct ou par délégation à un sous-agent.

---

## 🛡️ Règle Fondamentale sur Ticket « Rechercher »

Lorsqu'un ticket du Kanban Obsidian ou une demande utilisateur affiche **« rechercher »** (investigation documentaire, veille technologique, benchmark, exploration d'outils ou de bibliothèques tierces) :

> [!CAUTION]
> **Interdiction formelle de lancer un `/grill-with-docs` d'emblée.**
> Une interview de décisions ou un cadrage d'architecture est prématuré et inopérant tant que la matière documentaire n'a pas été rassemblée et assimilée.

---

## 🧭 Déroulement Nominal en 4 Étapes

### Étape 1 : Clarification du Sujet Précis
Si le ticket ou la demande n'est pas totalement explicite, interroger immédiatement l'utilisateur :
- Quel est le **sujet précis** et le périmètre d'investigation souhaité ?
- Quelles sont les **questions clés** ou incertitudes à lever en priorité (performances, compatibilité Python 3.12/PySide6, licences, architecture locale) ?
- Quels sont les **critères d'acceptation** ou le format de restitution attendu ?

### Étape 2 : Recherche Web & Sources Primaires
Explorer activement la documentation existante :
- **Recherche sur le web** (`search_web`) : documentation officielle des projets amont, dépôts GitHub, comparatifs récents, RFCs et spécifications.
- **Sources primaires exclusivement** : privilégier la documentation canonique des éditeurs/mainteneurs aux articles dérivés ou obsolètes.
- **Confrontation au socle existant** : vérifier l'adéquation avec les contraintes d'AnkiForge (`src/ankiforge/`, ADRs existants, typage strict, fonctionnement hors ligne).

### Étape 3 : Adaptation & Synthèse Contextualisée
- Ne pas se contenter d'un copier-coller brut : **adapter directement la documentation trouvée aux besoins spécifiques de l'utilisateur** et aux contraintes du projet.
- Présenter les compromis (avantages, limites, complexité d'intégration, dépendances requises).
- Rédiger une synthèse claire et sourcée (URLs, versions de paquets, extraits pertinents) enregistrée sous `docs/` ou consignée dans le ticket Obsidian ciblé.

### Étape 4 : Orientation Aval Conditionnelle
Ce n'est qu'une fois la documentation existante amenée, synthétisée et validée avec l'utilisateur que l'on détermine l'étape suivante du flux :
- **Arbitrage d'architecture nécessaire** : basculer vers `/grill-with-docs` pour cadrer la décision sur des bases factuelles solides.
- **Orientation technique évidente** : basculer directement vers la spécification `/to-spec` puis le découpage `/to-tickets`.
- **Validation empirique requise** : basculer vers un prototype jetable `/prototype`.

---

## 🤖 Mode Délégué (Sous-Agent d'Arrière-Plan)

Pour les analyses documentaires massives (lecture de spécifications très denses, analyse comparative de multiples dépôts tiers) :
1. Lancer un sous-agent de recherche (`research`) via `invoke_subagent`.
2. Définir une mission claire : périmètre d'investigation, sources cibles et questions précises.
3. Le sous-agent rédige sa synthèse sourcée dans un document Markdown sous `docs/` et notifie la session principale.

---

## When NOT to use this skill

- Pour une vérification rapide d'une signature d'API ou d'un fichier source du projet réalisable en un tour → consulter directement le code.
- Pour affûter une décision d'architecture une fois la documentation déjà établie et assimilée → utiliser `/grill-with-docs`.
- Pour implémenter du code de production → utiliser `/implement` ou `/tdd`.
- Pour reproduire et corriger un bug technique → utiliser `/diagnosing-bugs`.
