# Format et Conventions du Glossaire CONTEXT.md 📖

## 1. Structure du Glossaire Mono-Contexte (AnkiForge)

Dans AnkiForge, l'architecture documentaire repose sur un **unique `CONTEXT.md` à la racine du dépôt** couplé au registre de décisions d'architecture `docs/adr/`.

```markdown
# Contexte Métier & Domaine — AnkiForge

Environnement de création et de révision assistée par IA de cartes mémoire Anki, modélisation relationnelle locale et couverture documentaire.

## Termes Clés du Domaine

**Type de note**:
Gabarit régissant les champs (`CardFieldModel`), le CSS global et les gabarits de cartes (`CardTemplateModel`).
_Avoid_: Modèle de carte, card model, template

**Note**:
Unité documentaire portant les données brutes (champs textuels, LaTeX, balises HTML). Une note génère une ou plusieurs cartes.
_Avoid_: Fiche, item, flashcard (au niveau stockage)

**Carte**:
Unité d'interrogation et de révision atomique générée par application d'un gabarit de carte (recto/verso) sur une note.
_Avoid_: Note, enregistrement

**Écarter (Exclusion)**:
Règle de périmètre non destructive sortant un conteneur ou une section du calcul de couverture et de génération de cartes.
_Avoid_: Supprimer, masquer, purger
```

## 2. Règles de Rédaction

- **Prise de position tranchée** : lorsqu'il existe plusieurs termes concurrents pour désigner la même notion, choisir le terme canonique du projet et consigner impérativement les faux synonymes sous `_Avoid_`.
- **Définitions resserrées** : une ou deux phrases maximum. Définir ce que le concept *EST*, non son implémentation de bas niveau.
- **Périmètre métier exclusif** : n'inclure que les concepts propres au domaine applicatif d'AnkiForge (modélisation de cartes, RAG, traçabilité, profils). Bannir les notions génériques de programmation (threads, timeouts, exceptions).
- **Regroupement thématique** : structurer par sous-sections logiques (`### Modélisation des Cartes`, `### Couverture & RAG`, `### Profils & Stockage`).

## 3. Articulation avec les ADRs (`docs/adr/`)

- `CONTEXT.md` fige le **vocabulaire partagé** et les frontières conceptuelles.
- Tout arbitrage technique structurant (ex: choix d'un algorithme de délimitation, contrat de synchronisation, persistance) est consigné dans un fichier ADR dédié sous `docs/adr/NNNN-titre.md` et référencé depuis les compétences associées.
