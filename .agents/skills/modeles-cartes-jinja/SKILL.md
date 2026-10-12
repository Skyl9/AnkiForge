---
name: modeles-cartes-jinja
description: >-
  Expert en modélisation de types de notes Anki, gabarits Jinja2, HTML/CSS et occlusions pour AnkiForge. Conçoit les modèles de cartes (NoteTypeModel, CardTemplateModel), les gabarits recto/verso, les directives d'occlusion (cloze_manager.py) et applique les 20 règles de formulation de Piotr Wozniak.
  Use when the user asks to "créer un type de note", "modifier un modèle de carte", "template jinja2", "styling css anki", "gérer les clozes", "règles de wozniak", "linter wozniak", "recto verso anki", or designs flashcard note types and templates.
  When NOT to use: Do not use for packaging .apkg export or media synchronization (use export-synchro-anki) or general PySide6 view styling (use ui-pyside6-design).
---

# 🗂️ Modèles de Cartes, Gabarits Jinja2 & Wozniak — AnkiForge

En tant qu'**Expert des Modèles de Cartes & Gabarits Anki**, tu conçois, fais évoluer et valides les types de notes, le templating Jinja2/HTML/CSS et les directives de formulation pédagogique de l'application.

> **Code source clé** :
> - `src/ankiforge/database/models/cards.py` : `NoteTypeModel`, `CardFieldModel`, `CardTemplateModel`.
> - `src/ankiforge/services/cards/cloze_manager.py` : Gestion des occlusions de texte (`{{c1::...}}`).
> - `src/ankiforge/services/cards/card_model_io.py` : Import/export de modèles au format bundle/JSON.
> - `src/ankiforge/services/audit/linter_service.py` : Moteur de règles Wozniak (atomicité, interférences).

## 1. Modélisation des Types de Notes & Cartes

- **Type de note (`NoteTypeModel`)** : gabarit Anki régissant les champs (`CardFieldModel`), le CSS global, et les gabarits de cartes (`CardTemplateModel`).
  - *Règle de terminologie (`CONTEXT.md`)* : utiliser rigoureusement « Type de note » (et non modèle de carte / card model).
- **Rôle IA du type de note** : champ `NoteTypeModel.description` injecté dynamiquement dans la balise `{{ available_card_models }}` des prompts d'extraction pour orienter le LLM vers le type le plus pertinent (ex: définition, formule, chronologie).
- **Notes vs Cartes** :
  - La *Note* porte les données brutes (champs textuels, LaTeX, balises HTML).
  - La *Carte* est l'unité de révision générée par application d'un gabarit (recto `qfmt` / verso `afmt`). Une note génère une ou plusieurs cartes.

## 2. Gabarits Jinja2 & Styling CSS

- **Syntaxe standard Anki & Jinja2** : champs `{{Champ}}`, conditions `{{#Champ}}...{{/Champ}}`, filtres `{{cloze:Texte}}`.
- **CSS scopé** : styles de cartes isolés garantissant un rendu propre sur Desktop, AnkiMobile et AnkiWeb.
- **Rendu mathématique & KaTeX** : validation de la syntaxe des formules `$..$` et `$$..$$`.
- **Gestionnaire d'occlusions (`cloze_manager.py`)** : génération déterministe d'indices d'occlusion incrémentaux sans chevauchements illégaux.

## 3. Linter Pédagogique Wozniak

Validation de la qualité des cartes selon les 20 règles de formulation de Piotr Wozniak :
- **Atomicité stricte** : une carte = un fait atomique unique (règle 4). Éviter les listes à puces exhaustives au profit de scissions en plusieurs cartes.
- **Prévention des interférences** : formulations différenciées pour les concepts symétriques ou proches.
- **Inspecteur de refactoring** : comparaison 5 champs SQLite vs proposition IA et scission/mutation en un clic.

## When NOT to use this skill

- L'objectif est d'exporter un paquet `.apkg` ou de synchroniser les médias avec Anki → utiliser `export-synchro-anki`.
- L'objectif est de modifier l'interface Qt de l'atelier de cartes (panneaux, fenêtrage) → utiliser `ui-pyside6-design`.
- L'objectif est de configurer une étape DAG de génération par l'IA → utiliser `pipeline-dag-ia`.
