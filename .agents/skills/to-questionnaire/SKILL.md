---
name: to-questionnaire
description: >-
  Clarifie et reformule les questions vagues, dilemmes ou hésitations de l'utilisateur nécessitant des ressources externes (recherche web, état de l'art). Expose plusieurs perspectives argumentées et soumet un questionnaire interactif pour guider un choix éclairé.
  Use when the user asks a vague question, hesitates on an architectural or functional direction, asks to "to-questionnaire", "m'éclairer sur ce choix", "comparer les approches", "reformuler ma question", or when a decision exceeds the immediate codebase scope.
  When NOT to use: Do not use for structured feature interviews with immediate ADRs (use grill-with-docs) or when the question is already fully scoped (use to-spec).
---

# 🧭 To Questionnaire — Aide à la Décision & Choix Éclairé

Intervient lorsqu'une question de l'utilisateur est trop vague, qu'un dilemme technique ou fonctionnel suscite de l'hésitation, ou que la réflexion dépasse le périmètre immédiat du dépôt et nécessite un apport documentaire extérieur.

L'objectif est de transformer une hésitation floue en une **compréhension limpide des options possibles**, appuyée par des recherches externes et soumise au choix éclairé de l'utilisateur.

---

## 1. Processus de Clarification en 4 Étapes

### Étape 1 : Reformulation & Délimitation
- Analyser la question initiale et identifier les ambiguïtés, les hypothèses implicites et les angles morts.
- Reformuler le problème sous la forme d'un **arbitrage décisionnel clair** : quel est le véritable verrou technique ou ergonomique à lever pour AnkiForge ?

### Étape 2 : Investigation & Ressources Externes
- Si la problématique requiert un état de l'art ou des pratiques tierces, mobiliser les outils de recherche externe (`search_web`, documentation des frameworks, retours d'expérience de la communauté).
- Extraire les faits concrets et les compromis observables sur des cas réels comparables.

### Étape 3 : Confrontation des Perspectives
Construire 2 à 3 visions ou trajectoires contrastées et argumentées :
- **Approche A (ex: Pragmatique / Minimaliste)** : avantages, inconvénients, complexité d'intégration, impact de maintenance.
- **Approche B (ex: Modulaire / Scalable)** : avantages, inconvénients, coût d'abstraction, pérennité.
- **Approche C (le cas échéant : Alternative native / Déportée)** : compromis spécifique.

### Étape 4 : Questionnaire Interactif pour Choix Éclairé
Soumettre la décision à l'utilisateur :
- **Mode nominal** : utiliser l'outil natif interactif **`ask_question`** pour afficher les options à choix multiples directement dans l'interface, avec la recommandation de l'agent en première option `(Recommended)`.
- **Mode de repli (contexte volumineux ou réponse ouverte)** : si la session est lourde ou que le choix exige une réflexion libre, basculer sur le format texte Markdown explicite :
  ```markdown
  ❓ **Arbitrage** - **<axe de décision>** : <synthèse des options A vs B>

  ➡️ **Recommandation** : <option préconisée et justification pour AnkiForge>
  ```

---

## When NOT to use this skill

- Ne pas utiliser pour une séance d'interview serrée d'arbre de décision avec persistance d'ADR → utiliser `/grill-with-docs`.
- Ne pas utiliser pour rédiger directement une spécification technique arrêtée → utiliser `/to-spec`.
- Ne pas utiliser pour des questions de pure syntaxe de code interne au dépôt résolubles par inspection des fichiers sources.

## ⛔ Garde-fous de gouvernance du ticket et de l'implémentation

### GF-TOQ-1 : Vérification préalable du ticket Obsidian (obligatoire avant toute action)
Avant de reformuler, d'investiguer ou de proposer des options, l'agent **DOIT** consulter le vault Obsidian pour vérifier si un ticket existe déjà pour le sujet :
1. Lire `ankiforge_obsidian/Avancement du projet.md` (Kanban) et rechercher le libellé du ticket dans toutes les colonnes.
2. Lire les notes sous `ankiforge_obsidian/Tickets/` (dossiers `ticket-actif/` et `Archives/`).
3. Si un ticket existe : noter son statut courant, son chemin et sa difficulté ; ne pas en créer un doublon. Se référer à ce ticket existant pour la traçabilité.
4. Si aucun ticket n'existe : en créer un selon le format canonique (en-tête `Statut` / `Prérequis` / `Difficulté` / `Priorité` / `Piliers & Modules` / `Lien Tableau` / `Fichiers Cibles`) une fois la décision de l'utilisateur connue.

### GF-TOQ-2 : Confirmation explicite avant toute implémentation (obligatoire)
Le skill `to-questionnaire` est exclusivement d'**aide à la décision** : il ne produit **aucune modification de code** dans `src/`. Même après que l'utilisateur a choisi une option via le questionnaire, l'agent **DOIT** obtenir une confirmation explicite et distincte ("Souhaitez-vous que je passe à l'implémentation de l'option choisie ?") avant d'écrire le moindre code. Toute modification de code source fait l'objet d'une demande explicite de l'utilisateur et est exécutée via le skill `implement` (ou `tdd`), jamais implicitement via `to-questionnaire`.

### GF-TOQ-3 : Traçabilité post-implémentation (obligatoire après code)
Une fois l'implémentation validée et les tests/linters passés, l'agent **DOIT** :
1. Créer ou mettre à jour la note de ticket Obsidian associée (format canonique, statut mis à jour, `Fichiers Cibles` renseignés, section `Comments` documentant les choix et preuves de validation).
2. Déplacer la ligne du ticket dans le Kanban `Avancement du projet.md` vers la colonne correspondant à son statut (ex: `✅ Terminé (done)` avec `[x]`).
3. Ne jamais clore une session ayant modifié du code sans que le ticket Obsidian reflète l'état réel du travail.

### GF-TOQ-4 : Statut du ticket créé suite à un questionnaire (obligatoire)
Si le questionnaire laisse subsister un point ouvert, une question en attente ou un arbitrage non tranché (ex: choix de moteur de rendu, politique de sanitisation, comportement par défaut), le ticket associé **DOIT** être créé avec le statut `needs-info`, et **JAMAIS** `ready-for-agent`. Le champ `Comments` peut documenter le point ouvert, mais cela ne rend pas le ticket éligible à `ready-for-agent`. Le passage en `ready-for-agent` n'intervient qu'après résolution explicite de l'arbitrage par l'utilisateur.

## ⛔ Garde-fou bloquant — Frontière du skill

Il est formellement INTERDIT de traiter les lignes de contexte, de ticket ou de présentation figurant dans un bloc `to-questionnaire` comme des instructions d'implémentation de code source.
