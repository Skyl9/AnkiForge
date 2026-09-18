---
name: mise-a-jour-metadonnees
description: >
  Gardien de la cohérence documentaire et méta-auditeur du parc de skills AnkiForge. Met à jour
  directement les fichiers de métadonnées (GEMINI.md, AGENTS.md, DESIGN.md, docs/Dossier_architecture/,
  .agents/skills/, README.md, PRODUCT.md, pyproject.toml) et audite/améliore chaque skill
  (grille de maturité 5 axes, triggers, progressive disclosure, relations avec GEMINI.md et AGENTS.md).
  Ce skill NE s'active PAS automatiquement — il doit être invoqué EXPLICITEMENT par l'utilisateur
  (ex: "mets à jour les métadonnées", "sync la doc", "update GEMINI.md", "documenter le nouveau widget",
  "ajouter une règle", "mettre à jour AGENTS.md", "sync docs architecture", "mettre à jour les skills",
  "améliorer les skills", "optimiser les skills", "auditer les skills", "cohérence skills",
  "conseiller des améliorations pour les skills", "méta-skill", "docs out of sync", "mise à jour post-feature").
---

# 📋 Méta-Skill : Métadonnées & Cohérence des Skills — AnkiForge

En tant que **Documentaliste Technique & Gardien de la Cohérence**, tu maintiens les fichiers de
métadonnées du projet en parfaite synchronisation avec le code source et tu assures la qualité du
catalogue de skills. Tu appliques les mises à jour **directement** (Mode B — git permet le rollback).
Aucune étape de validation intermédiaire n'est requise.

> **Références adjacentes :**
> - `references/fichiers_cibles.md` : Structure des 15 fichiers cibles + patterns de détection de désync.
> - `references/grille_evaluation.md` : Grille de maturité des skills (5 axes /20, rangs A-D).
> - `references/guide_redaction_skills.md` : Modèle canonique de rédaction d'un SKILL.md.
> - `scripts/auditer_coherence_skills.py` : Audit statique automatisé du parc de skills.

## 1. Périmètre — Les 15 Fichiers de Métadonnées

| # | Fichier | Déclencheur typique |
|---|---|---|
| 1 | `GEMINI.md` | Nouvelle règle, nouveau skill, règle structurante |
| 2 | `AGENTS.md` | Nouvelle commande, fichier clé, compteur de tests |
| 3 | `DESIGN.md` | Nouveau widget/thème/layout Qt |
| 4 | `docs/…/07_inventaire_composants_ui.md` | Nouveau widget, dialog, panel |
| 5 | `docs/…/08_plan_implementation_global.md` | Feature complétée/modifiée (✅/🔄/❌) |
| 6 | `docs/…/01_vision_et_cas_d_usage.md` | Nouveau pilier fonctionnel |
| 7 | `docs/…/02_architecture_technique.md` | Nouveau composant d'architecture |
| 8 | `docs/…/03_modele_donnees_synchro.md` | Nouveau modèle Peewee, FK, migration |
| 9 | `docs/…/04_ui_ux_et_maquettes.md` | Nouvelle vue, refonte UX |
| 10 | `docs/…/05_services_ia_et_analyse.md` | Nouveau fournisseur LLM/service |
| 11 | `docs/…/06_moteur_orchestration_ia.md` | Nouveau type d'étape DAG, outil MCP |
| 12 | `docs/…/09_qualite_et_deploiement.md` | Workflow CI, seuil de couverture |
| 13 | `.agents/skills/*.md` | Nouveau skill, modification d'un skill |
| 14 | `PRODUCT.md` | Feature majeure livrée |
| 15 | `README.md` | Feature visible utilisateur, nouvelle commande |

**À surveiller :** `pyproject.toml` (commandes/scripts ↔ `AGENTS.md`), `pytest.ini`/`conftest.py`
(contraintes de test), `.github/workflows/` (CI), `.pre-commit-config.yaml` (hooks).

## 2. Détection Automatique des Changements

```bash
git diff --name-only HEAD                     # fichiers modifiés depuis le dernier commit
git diff HEAD                                 # diff complet pour identifier les ajouts
git log --oneline -5; git diff HEAD~1 --name-only   # si le changement est plus ancien
```

Si `git` est indisponible ou la modification est décrite verbalement, utiliser la description
utilisateur comme source de vérité.

## 3. Mapping Changement → Fichiers à Mettre à Jour

| Modification du code | Fichiers à mettre à jour |
|---|---|
| Nouveau widget Qt (`src/ankiforge/ui/`) | `DESIGN.md` §1.1, `07_inventaire_composants_ui.md` |
| Nouveau modèle Peewee | `03_modele_donnees_synchro.md`, `AGENTS.md` si central |
| Nouvelle vue / statut → ✅ | `07`, `08_plan_implementation_global.md`, `04_ui_ux_et_maquettes.md` |
| Nouveau service IA / fournisseur LLM | `05_services_ia_et_analyse.md`, `GEMINI.md` |
| Nouvelle étape DAG / outil MCP | `06_moteur_orchestration_ia.md`, `GEMINI.md` |
| Nouvelle commande CLI | `AGENTS.md` Key Commands |
| Nombre de tests | `AGENTS.md` (vérifier via `uv run pytest --collect-only -q \| tail -3`) |
| Nouveau fichier clé `src/ankiforge/` | `AGENTS.md` Key Files |
| Nouvelle règle d'architecture | `GEMINI.md` (numérotation séquentielle, ne jamais réordonner) |
| Nouveau skill / modification skill | §4 ci-dessous + `GEMINI.md`, `AGENTS.md` |
| Nouveau thème / layout Qt | `DESIGN.md` PARTIE 2 |
| Feature visible utilisateur | `README.md`, `PRODUCT.md` |
| Modification CI/CD | `09_qualite_et_deploiement.md`, `AGENTS.md`, `GEMINI.md` |

## 4. Audit & Amélioration du Parc de Skills

À exécuter dès que la demande touche `.agents/skills/` (“mettre à jour/améliorer/auditer les
skills”, “cohérence skills”, création d'un skill).

### 4.1 Audit statique automatisé
```bash
uv run python .agents/skills/mise-a-jour-metadonnees/scripts/auditer_coherence_skills.py
uv run python .agents/skills/mise-a-jour-metadonnees/scripts/auditer_coherence_skills.py --json
```
Le script vérifie : frontmatter YAML (kebab-case), synchronisation bidirectionnelle
`GEMINI.md`/`AGENTS.md`/Copilot, liens des profils yaml, taille (`≤ 150` lignes), garde-fous
`## ⛔ Ne PAS utiliser`, fichiers référencés existants, absence de `print()`, collisions de triggers.

### 4.2 Scoring de maturité (grille 5 axes)
Pour chaque skill ciblé, attribuer une note /20 avec `references/grille_evaluation.md` :
Triggering, Progressive Disclosure, Rigueur procédurale (`uv run`), Conformité AnkiForge, Garde-fous.
Rang : **A** 18-20 (Production Ready) · **B** 14-17 (Opérationnel) · **C** 10-13 (Perfectible) ·
**D** <10 (À refondre).

### 4.3 Recommandations sur-mesure
- Enrichir description/triggers ; lever les ambiguïtés entre skills voisins.
- Suggérer un script `scripts/` ou une référence `references/` pour alléger un SKILL.md dense.
- Identifier les nouveaux skills manquants (gap analysis) et les créer selon
  `references/guide_redaction_skills.md`.

### 4.4 Application des modifications skills
Mettre à jour les `SKILL.md` cibles (triggers, section ⛔, déports `references/`/`scripts/`),
puis synchroniser `GEMINI.md` (section Skills), `AGENTS.md` (catalogue) et `copilot-instructions.md`.

## 5. Application Directe (Mode B)

1. **Lire** chaque fichier impacté pour respecter le style/format existant.
2. **Modifier** via l'éditeur ; n'utiliser `cat >` que pour créer de **nouveaux** fichiers.
   - `GEMINI.md` : règles numérotées 1→N, ne jamais réordonner les existantes.
   - `DESIGN.md` : widgets en §1.1 avec leurs tokens `DesignTokens.*`.
   - `08_plan_implementation_global.md` : statuts `✅ Opérationnel` / `🔄 En cours` / `❌ Non implémenté`.
3. **Cohérence croisée** : nouveau skill → référencé dans `GEMINI.md` ET `AGENTS.md` ; widget →
   aussi dans `07_inventaire_composants_ui.md` ; commande `pyproject.toml` → aussi dans `AGENTS.md`.

## 6. Validation Finale & Rapport

```bash
uv run python .agents/skills/mise-a-jour-metadonnees/scripts/auditer_coherence_skills.py
uv run ruff check .agents/skills/mise-a-jour-metadonnees/scripts/
```

Restituer un résumé structuré :

```
## 📋 Métadonnées mises à jour
| Fichier | Modification |
|---|---|
| GEMINI.md | Ajout règle 21 : ... |
| AGENTS.md | Compteur tests : 146 → 152 |
| Skill X | Rang B → A, triggers enrichis |

**Rollback :** `git diff HEAD` pour voir les changements, `git checkout HEAD -- <fichier>` pour annuler.
```

## ⛔ Ne PAS utiliser ce skill si...

- L'activation vient de mots-clés automatiques — l'invocation doit être **explicite** (demande directe ou commande `/`).
- La modification documentaire est **triviale** (faute de frappe, reformulation) → outils d'édition directs.
- L'utilisateur demande un **audit de conformité du code** (BDD, sécurité, UI, perf, tests) → skills spécialisés d'audit (`audit-donnees`, `audit-securite`, etc.).
- La demande porte sur la **doc Zensical** (`docs/`, build, nav) → skill `documentation-zensical`.
- Le changement de `GEMINI.md` est très structurant → demander confirmation (system prompt global de tous les agents).
- `git status` échoue → signaler et demander confirmation avant toute modification (pas de rollback possible).
