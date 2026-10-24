---
name: session-retrospective
description: >-
  Rétrospective critique de session et auto-amélioration continue du catalogue de compétences agentiques. Analyse les erreurs, oublis procéduraux, dérives et corrections humaines survenues durant une session, identifie les causes racines et met à jour ou crée des compétences (.agents/skills/) et garde-fous pour immuniser les futures sessions.
  Use when the user asks to "analyser la session", "étudier les erreurs", "rétrospective", "session-retrospective", "post-mortem session", "auto-amélioration", "améliorer les skills", "tirer les leçons", or wants to analyze mistakes made during the session and evolve skills to prevent recurrence.
  When NOT to use: Do not use for diagnostic of bugs in the application code (use diagnosing-bugs) or code quality audits (use audit-qualite-code).
---

# 🔄 Session Retrospective & Auto-Amélioration des Skills

En tant qu'**Agent Rétrospectif et Architecte de l'Auto-Amélioration Continue**, ton rôle est d'analyser sans complaisance les actions, dérives, omissions et corrections humaines survenues au cours d'une session de travail, d'en extraire les causes racines procédurales, et de durcir immédiatement le catalogue de compétences (`.agents/skills/`) pour pérenniser l'apprentissage et immuniser l'agent contre toute récidive.

---

## 1. Contexte & Périmètre d'Analyse

- **Sources d'inspection** :
  - Le transcript de conversation (actions, outils invoqués, rappels à l'ordre ou clarifications de l'utilisateur).
  - L'état Git des dépôts via l'outil dédié `scripts/analyser_session.py`.
  - La typologie des biais cognitifs et erreurs agentiques documentée dans `references/grille_analyse_post_mortem.md`.
  - Les compétences invoquées au cours de la session (`implement`, `obsidian-vault`, `code-review`, etc.).
- **Objectif impératif** : Ne jamais clore une rétrospective par de simples « excuses » ou « promesses ». Tout enseignement doit être traduit par une **modification concrète, vérifiable et versionnée** dans le catalogue de skills ou l'outillage de contrôle.

---

## 2. Procédure Pas-à-Pas de Rétrospective

### Étape 1 : Diagnostic de l'Espace de Travail
Exécuter le script de diagnostic Git multi-dépôts :
```bash
uv run python .agents/skills/session-retrospective/scripts/analyser_session.py
```
Relever les éventuelles divergences entre le dépôt principal AnkiForge et le sous-dépôt `ankiforge_obsidian/`.

### Étape 2 : Reconstitution Chronologique des Faits
1. Lister les intentions initiales de l'utilisateur et les compétences activées.
2. Relever les **incidents observés** :
   - Étapes de compétences omises ou interverties (ex: clôture avant code-review).
   - Altérations de fichiers non prévues ou écrasements collatéraux (ex: Kanban réorganisé).
   - Avertissements ou corrections formulés par l'utilisateur.
   - Échecs de commandes ou régressions détectées par les linters/tests.

### Étape 3 : Analyse Causale des 5 Pourquoi (Root Cause Analysis)
Pour chaque incident, confronter aux patterns de `references/grille_analyse_post_mortem.md` :
- L'instruction du skill était-elle trop vague ou consultative plutôt que contraignante ?
- Manquait-il un garde-fou bloquant explicite (« ⛔ Il est formellement INTERDIT de... ») ?
- L'agent a-t-il présumé de l'état d'un fichier sans inspection préalable du disque/Git ?
- Une spécificité d'architecture (ex: sous-dépôt Git indépendant) était-elle omise de la documentation du skill ?

### Étape 4 : Plan d'Action & Évolution du Parcours de Compétences
Identifier l'action requise :
- **Renforcement d'un skill existant** :
  - Insérer des garde-fous bloquants séquentiels dans `SKILL.md`.
  - Préciser les pièges récurrents et les vérifications préalables obligatoires.
- **Création d'un nouveau skill** :
  - Si le besoin relève d'un domaine ou d'une responsabilité absente du catalogue (≥ 3 cas d'usage réels).
  - Appliquer rigoureusement le guide canonique de rédaction des skills (standard `agentskills.io`).

### Étape 5 : Application, Synchronisation & Audit Statique
1. Appliquer les modifications dans `.agents/skills/<skill>/SKILL.md`.
2. Mettre à jour `.agents/instructions/catalogue_skills.md` et exécuter la synchronisation des adaptateurs :
   ```bash
   uv run python script/sync_agent_instructions.py
   ```
3. Valider la cohérence du catalogue via la compétence `gouvernance-skills` (audit statique 5 axes).
4. Exécuter la porte canonique de vérification globale :
   ```bash
   uv run python script/verify.py
   ```

---

## 3. Format de Restitution du Rapport

Présenter systématiquement à l'utilisateur :
1. **Tableau des Incidents & Causes Racines** (Incident, Conséquence, Cause racine identifiée).
2. **Modifications Concrètes Appliquées** (Fichiers de skills modifiés ou créés, extraits des garde-fous ajoutés).
3. **Preuves de Validation** (Résultats de `auditer_coherence_skills.py` et `verify.py`).
4. **Proposition de Commit** pour persister l'amélioration du catalogue.

---

## When NOT to use this skill

- Pour investiguer un bug ou crash applicatif dans le code Python d'AnkiForge → utiliser `diagnosing-bugs`.
- Pour auditer la sécurité, les performances ou la qualité du code source → utiliser les compétences d'audit dédiées (`audit-qualite-code`, `audit-performance`, `audit-securite`).
- Pour de la simple maintenance documentaire sans incident de session → utiliser `mise-a-jour-metadonnees`.
