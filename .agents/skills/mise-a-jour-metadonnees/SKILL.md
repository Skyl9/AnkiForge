---
name: mise-a-jour-metadonnees
description: >-
  Gardien de la synchronisation documentaire et des métadonnées du projet AnkiForge. Met à jour les 15 fichiers de métadonnées et d'architecture (GEMINI.md, AGENTS.md, DESIGN.md, docs/Dossier_architecture/, README.md, PRODUCT.md) suite à des ajouts ou modifications de code.
  Use when the user asks to "mets à jour les métadonnées", "sync la doc", "update GEMINI.md", "mettre à jour AGENTS.md", "documenter le nouveau widget", "sync docs architecture", "docs out of sync", "mise à jour post-feature", or needs to align project documentation with code changes.
  When NOT to use: Do not use for auditing or governing the agent skills catalog (use gouvernance-skills) or building Zensical HTML docs (use documentation-zensical).
---

# 📋 Synchronisation des Métadonnées & Architecture — AnkiForge

En tant que **Documentaliste Technique du Projet**, tu maintiens les 15 fichiers de métadonnées et d'architecture d'AnkiForge en parfaite synchronisation avec le code source après chaque développement.

## 1. Périmètre — Les 15 Fichiers Cibles

| # | Fichier | Déclencheur typique |
|---|---|---|
| 1 | `GEMINI.md` | Nouvelle règle d'architecture, mise à jour du catalogue de compétences |
| 2 | `AGENTS.md` | Nouvelle commande CLI, fichier clé, compteur de tests |
| 3 | `DESIGN.md` | Nouveau composant Qt, nouveau thème ou layout |
| 4 | `docs/…/07_inventaire_composants_ui.md` | Nouveau widget, dialogue ou panneau |
| 5 | `docs/…/08_plan_implementation_global.md` | Statut d'une fonctionnalité complétée (✅/🔄) |
| 6 | `docs/…/01_vision_et_cas_d_usage.md` | Évolution d'un pilier fonctionnel |
| 7 | `docs/…/02_architecture_technique.md` | Nouveau service ou composant d'architecture |
| 8 | `docs/…/03_modele_donnees_synchro.md` | Nouveau modèle Peewee, clé étrangère, migration |
| 9 | `docs/…/04_ui_ux_et_maquettes.md` | Nouvelle vue ou refonte ergonomique |
| 10 | `docs/…/05_services_ia_et_analyse.md` | Nouveau fournisseur LLM ou service d'analyse |
| 11 | `docs/…/06_moteur_orchestration_ia.md` | Nouveau type d'étape DAG, outil MCP |
| 12 | `docs/…/09_qualite_et_deploiement.md` | Workflow CI, seuil de couverture |
| 13 | `.agents/skills/*.md` | Compétences disponibles |
| 14 | `PRODUCT.md` | Fonctionnalité majeure livrée |
| 15 | `README.md` | Commande utilisateur ou présentation générale |

## 2. Détection des Évolutions

```bash
git diff --name-only HEAD~1 HEAD
```
Identifier les couches modifiées : `src/ankiforge/ui/` (➔ DESIGN.md, 07), `src/ankiforge/database/` (➔ 03, AGENTS.md), `src/ankiforge/services/` (➔ 05, 06).

## 3. Règle d'Application

- Appliquer les modifications **directement** dans les fichiers concernés (git permet le rollback).
- Préserver strictement la structure existante et les commentaires.
- Ne jamais réordonner les numéros de règles dans `GEMINI.md`.

## When NOT to use this skill

- L'objectif est d'**auditer la cohérence ou la qualité du parc de skills** → utiliser `gouvernance-skills`.
- L'objectif est de **valider la compilation HTML de la documentation Zensical** → utiliser `documentation-zensical`.
- L'objectif est d'**auditer la conformité du code Python aux règles GEMINI.md** → utiliser `audit-ankiforge` ou `audit-qualite-code`.
