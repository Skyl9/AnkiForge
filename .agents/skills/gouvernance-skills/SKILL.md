---
name: gouvernance-skills
description: >-
  Méta-gouverneur et auditeur du catalogue de compétences agentiques d'AnkiForge. Évalue la conformité au standard agentskills.io, exécute l'audit statique, applique la grille de maturité 5 axes, détecte les collisions de déclencheurs et encadre l'admission ou la scission de compétences.
  Use when the user asks to "auditer les skills", "cohérence skills", "gouvernance skills", "améliorer les skills", "créer un skill", "scinder un skill", "analyser les déclencheurs", or needs to review or evolve the agent skills catalog.
  When NOT to use: Do not use for general codebase doc updates (use mise-a-jour-metadonnees) or building Zensical HTML docs (use documentation-zensical).
---

# 🛡️ Gouvernance & Méta-Audit des Skills — AnkiForge

En tant que **Gardien de la Qualité et de la Cohérence des Compétences Agentiques**, tu régis le cycle de vie, la granularité et la conformité du catalogue de skills situé sous `.agents/skills/` conformément au standard ouvert **`agentskills.io`**.

> **Références adjacentes :**
> - `references/grille_evaluation.md` : Grille d'évaluation de maturité (5 axes /20, Rangs A-D).
> - `references/guide_redaction_skills.md` : Guide canonique de rédaction d'un `SKILL.md`.
> - `references/analyse_besoins_skills.md` : Matrice de Gap Analysis et fiche d'admission / scission de compétences.
> - `scripts/auditer_coherence_skills.py` : Script d'audit statique automatisé.

## 1. Principes du Standard `agentskills.io`

Chaque compétence du catalogue doit respecter strictement les 3 niveaux de **divulgation progressive** :
1. **Niveau 1 — Découverte** :
   - Frontmatter YAML valide avec `name` (kebab-case) et `description` (≤ 1024 caractères).
   - La description doit formuler le rôle et les déclencheurs explicites (`Use when the user asks to...`), plus les redirections rapides de faux positifs.
2. **Niveau 2 — Activation** :
   - Corps du fichier `SKILL.md` procédural et orienté action, limité à ≤ 150 lignes.
   - Présence obligatoire d'une section d'exclusion (`## When NOT to use this skill` ou `## ⛔ Ne PAS utiliser ce skill si...`).
3. **Niveau 3 — Exécution** :
   - Déportation des guides denses, checklists et catalogues dans `references/`.
   - Scripts exécutables autonomes dans `scripts/` (sans `print()`, conformes à la règle T20).

## 2. Audit Statique Automatisé

Exécuter la vérification automatisée de cohérence :
```bash
uv run python .agents/skills/gouvernance-skills/scripts/auditer_coherence_skills.py
```
Le script valide :
- La conformité YAML et le nommage de chaque compétence.
- La présence de déclencheurs explicites et de sections d'exclusion.
- La détection de collisions lexicales Jaccard entre les descriptions.
- L'existence physique de tous les fichiers référencés.

## 3. Évaluation de Maturité & Gap Analysis

- **Scoring 5 axes (sur 20)** : Triggering, Progressive Disclosure, Rigueur d'exécution (`uv run`), Conformité architecturale AnkiForge, Garde-fous.
- **Scission de compétences** : lorsqu'un skill cumule deux responsabilités opérationnelles distinctes (ex: extraction brute vs RAG, ou sync doc vs audit skills), le scinder en deux modules autonomes avec redirection mutuelle.
- **Admission de nouveaux skills** : soumise à la fiche candidat (`references/analyse_besoins_skills.md`), exigeant une récurrence prouvée (≥ 3 occurrences réelles dans le code/commits) et un gain agentique démontré.

## 4. Règle d'Incrémentalité & Questionnement Natif

- **Modification unitaire obligatoire** : toute refonte de catalogue s'exécute axe par axe, sans regroupement hâtif en vrac (prévention du biais T-5).
- **Interaction native Antigravity (`ask_question`)** : formuler systématiquement les questions de choix via l'outil interactif natif avec option recommandée en tête `(Recommended)`. En cas de contexte de conversation volumineux ou de réflexion ouverte complexe, expliciter la contrainte et basculer sur le format texte Markdown structuré par rounds (`❓ Q1` / `➡️ Recommandation`).

## When NOT to use this skill

- L'objectif est de mettre à jour les 15 fichiers de documentation après une modification de code → utiliser `mise-a-jour-metadonnees`.
- L'objectif est de compiler et vérifier la documentation HTML Zensical → utiliser `documentation-zensical`.
- L'objectif est de vérifier le code Python de l'application via la porte canonique → utiliser `verification-environnement` (`script/verify.py`).
