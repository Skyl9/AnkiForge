# Concevoir Deux Fois (Design It Twice) 📐

Lorsque l'utilisateur souhaite explorer des interfaces alternatives pour un module à approfondir, utiliser ce patron de sous-agents parallèles. Fondé sur le principe *« Design It Twice »* (John Ousterhout) : votre première idée d'interface est rarement la meilleure.

S'appuie sur le vocabulaire de [SKILL.md](SKILL.md) : **module**, **interface**, **couture (seam)**, **adaptateur (adapter)**, **effet de levier (leverage)**.

---

## Processus d'Exploration

### 1. Cadrer l'Espace du Problème
Avant de lancer des sous-agents, exposer à l'utilisateur une explication concise du problème :
- Les contraintes que toute nouvelle interface doit respecter.
- Les dépendances requises et leur catégorie (voir [DEEPENING.md](DEEPENING.md)).
- Une esquisse de code illustrative en Python 3.12 pour ancrer les contraintes concrètement.

### 2. Lancer les Sous-Agents Parallèles
Instancier 3 sous-agents en parallèle avec des contraintes de conception intentionnellement opposées :
- **Agent 1 (Minimaliste)** : Réduire l'interface au strict minimum (1 à 2 points d'entrée max, fort effet de levier).
- **Agent 2 (Extensible)** : Maximiser la modularité et la composition d'étapes (ex: pipeline DAG).
- **Agent 3 (Usage courant)** : Optimiser pour le cas le plus fréquent (rendre le cas nominal trivial en une ligne).

Chaque sous-agent produit :
1. L'interface typée (méthodes, types PEP 695, invariants, exceptions).
2. Un exemple d'usage appelant en Python.
3. Ce que l'implémentation masque derrière la couture.
4. Les compromis (points forts vs points faibles).

### 3. Restituer et Comparer
Présenter les variantes successivement, puis les confronter :
- Par **profondeur** (puissance offerte par rapport à l'effort d'apprentissage).
- Par **localité** (concentration des responsabilités).
- Par **pertinence du placement de la couture**.

Formuler une recommandation tranchée et argumentée pour AnkiForge.
