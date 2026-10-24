---
name: domain-modeling
description: >-
  Modélisation du domaine métier d'AnkiForge, enrichissement continu du glossaire CONTEXT.md et enregistrement des décisions d'architecture (ADR) structurantes dans docs/adr/.
  Use when the user asks to "domain-modeling", "modéliser le domaine", "définir un terme métier", "enrichir CONTEXT.md", "ajouter un ADR", or wants to align terms and architectural decisions.
  When NOT to use: Do not use for technical module interface design (use codebase-design), full feature interview (use grill-with-docs), or pure glossary reading.
---

# 📖 Modélisation du Domaine Métier (Domain Modeling)

Construire et affûter activement le modèle de domaine d'AnkiForge au fil de la conception : challenger la terminologie, éliminer les faux synonymes, éprouver les cas limites et figer les arbitrages dans le glossaire partagé et le registre d'ADRs.

---

## 1. Structure Mono-Contexte d'AnkiForge

AnkiForge fonctionne rigoureusement en **mono-contexte** :

```
/
├── CONTEXT.md                     ← Glossaire canonique unique du domaine
├── docs/
│   └── adr/                       ← Registre des décisions d'architecture structurantes
│       ├── 0001-...md
│       └── 0038-...md
└── src/ankiforge/
```

- `CONTEXT.md` est un **glossaire pur** et rien d'autre. Il ne contient aucun détail d'implémentation, aucun code, aucune table SQL.
- Format obligatoire : voir [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md).
- Format d'ADR : voir [ADR-FORMAT.md](./ADR-FORMAT.md).

---

## 2. Rôle Actif pendant les Échanges

### Challenger les Termes face au Glossaire
Dès que l'utilisateur ou une proposition emploie un terme ambigu ou contradictoire avec `CONTEXT.md`, le signaler immédiatement :
> *« Le glossaire définit "Note" comme l'entité documentaire brute et "Carte" comme l'unité de révision générée par un gabarit. Vous parlez de "créer une note de révision" : s'agit-il d'éditer la note ou de réviser la carte ? »*

### Affûter le Vocabulaire Imprécis
Identifier les termes flous ou surchargés et proposer la formulation canonique du domaine :
- Au lieu de « supprimer le chunk », employer « écarter la région » (règle d'exclusion non destructive ADR 0010).
- Au lieu de « modèle de carte », employer « type de note » (`NoteTypeModel`).

### Mettre à Jour `CONTEXT.md` au Fil de l'Eau
Dès qu'un terme ou une frontière de concept est stabilisé avec l'utilisateur, éditer immédiatement `CONTEXT.md`. Ne pas différer cette mise à jour en fin de session.

### Proposer un ADR avec Parcimonie
Ne proposer d'enregistrer un ADR (`docs/adr/0038-titre.md`) que lorsque les **3 critères suivants sont simultanément réunis** :
1. **Difficile à inverser** : le coût de revenir sur ce choix plus tard est significatif.
2. **Surprenant sans contexte** : un futur contributeur se demandera légitimement « pourquoi avoir fait ce choix ? ».
3. **Fruit d'un arbitrage réel** : il existait plusieurs alternatives crédibles et l'une a été retenue pour des motifs techniques précis.

---

## When NOT to use this skill

- Ne pas utiliser pour la conception technique des interfaces de modules et des coutures de code → utiliser `/codebase-design`.
- Ne pas utiliser pour mener l'interview complète de cadrage d'une fonctionnalité → utiliser `/grill-with-docs`.
- Ne pas utiliser pour une simple consultation passive du glossaire.
