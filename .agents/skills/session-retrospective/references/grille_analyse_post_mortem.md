# Grille d'Analyse Post-Mortem & Typologie des Erreurs Agentiques 🔍

Ce document fournit la typologie canonique des défaillances agentiques observées lors des sessions de développement et les stratégies de remédiation associées pour durcir les compétences dans AnkiForge.

---

## 1. Typologie des Défaillances Agentiques Récurrentes

### T-1 : Biais de Précipitation vers la Clôture (Early Completion Bias)
- **Symptôme** : L'agent voit ses tests et sa porte de vérification passer, et saute immédiatement aux étapes de clôture du ticket ou de proposition de commit, omettant une étape intermédiaire requise (ex: revue de code à deux axes, mise à jour des métadonnées, audit des docstrings).
- **Cause racine** : L'étape de revue est perçue comme "consultative" ou secondaire plutôt que comme une précondition bloquante.
- **Remédiation** : Transformer l'étape en garde-fou bloquant avec formulation impérative :
  > ⛔ **Garde-fou bloquant** : Il est formellement INTERDIT de modifier le statut du ticket à `Terminé` ou de formuler une proposition de commit avant d'avoir formellement exécuté l'étape X et présenté son rapport.

### T-2 : Écrasement Silencieux d'État Concurrent (Blind State Overwrite)
- **Symptôme** : L'agent utilise `edit_file` ou `write_file` sur un fichier partagé ou vivant (comme le Kanban `Avancement du projet.md`) en s'appuyant sur une version obsolète mémorisée dans son contexte, écrasant les modifications manuelles de l'utilisateur ou d'un processus concurrent.
- **Cause racine** : Absence de relecture immédiate de la version disque/Git courante (`HEAD`) juste avant l'écriture, ou édition par gros blocs plutôt que par substitution chirurgicale mono-ligne.
- **Remédiation** : Imposer la vérification préalable de `git diff` / `git status` et restreindre les éditions à des cibles atomiques strictes.

### T-3 : Méconnaissance des Frontières Multi-Dépôts (Multi-Repo Blindness)
- **Symptôme** : L'agent applique des commandes `git` sur la racine du projet en pensant englober un sous-dossier, alors que celui-ci est un sous-dépôt indépendant avec son propre `.git` (ex: `ankiforge_obsidian/` ignoré par le `.gitignore` racine).
- **Cause racine** : Omission de la topologie Git dans la spécification du skill concerné.
- **Remédiation** : Documenter explicitement la structure multi-dépôts dans le `SKILL.md` et interdire les commandes globales transverses aveugles.

### T-4 : Hypothèse Non Vérifiée sur l'i18n (Silently Broken Markers)
- **Symptôme** : Utilisation de `self.tr("Message : %1", val)` dans un widget Qt sans réaliser que `self.tr()` ne supporte pas la substitution de paramètres, conduisant à des marqueurs bruts affichés à l'écran.
- **Cause racine** : Confusion avec les méthodes de formatage classiques.
- **Remédiation** : Audit automatisé fail-fast (`tests/utils/test_i18n_audit.py`) et rappel strict de l'ADR 0013 dans les skills UI.

### T-5 : Biais de Regroupement Hâtif / Cadrage en Vrac (Bulk Decision Bias)
- **Symptôme** : Face à plusieurs axes de refonte ou plusieurs décisions architecturales, l'agent regroupe tout en bloc dans le chat textuel au lieu d'interroger l'utilisateur de manière unitaire et méthodique.
- **Cause racine** : Précipitation à vouloir solder l'ensemble du périmètre en une passe conversationnelle, négligeant l'outil natif interactif de choix.
- **Remédiation** : Imposer la règle d'incrémentalité stricte (une modification = une série de questions ciblées) via l'outil interactif natif (`ask_question` dans Antigravity) avec option recommandée en tête et repli texte si le contexte sature.

### T-6 : Cécité de l'Audit Statique Superficiel (Shallow Audit Blindness)
- **Symptôme** : Un script de gouvernance valide le statut `PASS` en se basant sur des métriques superficielles (présence de balises, longueur), masquant des liens cassés, des références décalées ou du code issu d'autres langages/stacks.
- **Cause racine** : Absence de validation des cibles réelles sur disque (liens Markdown, chemins d'ADRs, détection de patterns de langages interdits).
- **Remédiation** : Enrichir le script d'audit statique (`auditer_coherence_skills.py`) pour vérifier l'existence physique de chaque ADR et lien relatif, et interdire les blocs de langages étrangers (TypeScript/JSX dans un repo Python).

---

## 2. Matrice d'Évolution des Compétences Post-Incident

Lorsqu'un incident survient, appliquer la règle suivante :

| Type d'Incident | Action sur le Catalogue de Skills | Fichiers Cibles |
|---|---|---|
| Omission de revue ou de vérification | Ajout d'une précondition bloquante dans le workflow | `implement/SKILL.md`, `to-spec/SKILL.md` |
| Conflit / écrasement dans le vault Obsidian | Clarification du sous-repo Git et renforcement des règles atomiques | `obsidian-vault/SKILL.md` |
| Erreur de Design System ou couleur codée en dur | Rappel de la règle 8 et ajout d'assertions `refresh_theme` | `ui-pyside6-design/SKILL.md` |
| Nouvelle famille d'erreurs récurrente (≥ 3 occurrences) | Admission d'un nouveau skill spécialisé ou script d'audit | `.agents/skills/<nouveau-skill>/` |
