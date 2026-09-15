---
name: mise-a-jour-metadonnees
description: >
  Met à jour directement les fichiers de métadonnées du projet AnkiForge (GEMINI.md, AGENTS.md,
  DESIGN.md, docs/Dossier_architecture/, .agents/skills/, README.md, PRODUCT.md, pyproject.toml)
  pour les maintenir en cohérence avec le code source après toute modification significative.
  Ce skill NE s'active PAS automatiquement sur des mots-clés — il doit être invoqué EXPLICITEMENT
  par l'utilisateur (ex: "mets à jour les métadonnées", "sync la doc", "update GEMINI.md",
  "documenter le nouveau widget", "ajouter une règle", "mettre à jour AGENTS.md",
  "sync docs architecture", "mettre à jour les skills", "tenir à jour la doc",
  "documenter la feature", "docs out of sync", "mise à jour post-feature").
---

# 📋 Mise à Jour des Métadonnées — AnkiForge

En tant que **Documentaliste Technique & Gardien de la Cohérence**, tu maintiens les fichiers de
métadonnées du projet en parfaite synchronisation avec le code source. Tu appliques les mises à
jour **directement** (Mode B — git permet le rollback en cas d'erreur). Aucune étape de validation
intermédiaire n'est requise.

> Le fichier `references/fichiers_cibles.md` adjacent contient les patterns de détection de
> désynchronisation et la structure détaillée de chaque fichier cible.

## 1. Périmètre — Les 15 Fichiers de Métadonnées

| # | Fichier | Rôle | Déclencheur typique |
|---|---|---|---|
| 1 | `GEMINI.md` | Règles d'architecture (20 règles), liste des skills | Nouvelle règle, nouveau skill, pilier archi |
| 2 | `AGENTS.md` | Quick reference CLI, highlights, nb de tests | Nouvelle commande, nouveau fichier clé, nb tests |
| 3 | `DESIGN.md` | Design system, tokens, thèmes, **inventaire widgets** | Nouveau widget/composant Qt, nouveau thème |
| 4 | `docs/Dossier_architecture/07_inventaire_composants_ui.md` | Inventaire détaillé PySide6 | Nouveau widget, dialog, panel |
| 5 | `docs/Dossier_architecture/08_plan_implementation_global.md` | Statut d'implémentation par vue (✅/🔄/❌) | Feature complétée ou modifiée |
| 6 | `docs/Dossier_architecture/01_vision_et_cas_d_usage.md` | Vision produit & cas d'usage | Nouveau pilier fonctionnel |
| 7 | `docs/Dossier_architecture/02_architecture_technique.md` | Stack technique & composants | Nouveau composant archi (MCP, RAG, etc.) |
| 8 | `docs/Dossier_architecture/03_modele_donnees_synchro.md` | Modèle de données Peewee & synchro | Nouveau modèle, nouvelle FK, migration |
| 9 | `docs/Dossier_architecture/04_ui_ux_et_maquettes.md` | UI/UX & maquettes | Nouvelle vue, refonte UX |
| 10 | `docs/Dossier_architecture/05_services_ia_et_analyse.md` | Services IA & analyse | Nouveau fournisseur LLM, nouveau service |
| 11 | `docs/Dossier_architecture/06_modele_orchestration_ia.md` | Moteur DAG | Nouveau type d'étape DAG, nouveau MCP tool |
| 12 | `docs/Dossier_architecture/09_qualite_et_deploiement.md` | Qualité & CI/CD | Nouveau workflow CI, seuil de couverture |
| 13 | `.agents/skills/*.md` | Skills agentiques | Nouveau skill, modification d'un skill |
| 14 | `PRODUCT.md` | Description produit haut niveau | Feature majeure livrée |
| 15 | `README.md` | Documentation publique | Feature visible utilisateur, nouvelle commande |

**Fichiers complémentaires à surveiller :**
- `pyproject.toml` → source de vérité pour les commandes et dépendances (AGENTS.md doit rester en sync)
- `pytest.ini` / `conftest.py` → fixtures et contraintes de test (AGENTS.md "Testing Constraints")
- `.github/workflows/ci.yml` → jobs CI (GEMINI.md règle 20, AGENTS.md CI section)
- `.pre-commit-config.yaml` → hooks (AGENTS.md "Code Conventions")

## 2. Détection Automatique des Changements

Commence toujours par identifier précisément ce qui a changé :

```bash
# Fichiers modifiés depuis le dernier commit
git diff --name-only HEAD

# Diff complet (pour lire les ajouts)
git diff HEAD

# Si la modification est plus ancienne
git log --oneline -5
git diff HEAD~1 --name-only
```

Si `git` n'est pas disponible ou que l'utilisateur décrit verbalement la modification, utilise
sa description comme source de vérité.

## 3. Mapping Changement → Fichiers à Mettre à Jour

| Modification du code | Fichiers à mettre à jour |
|---|---|
| Nouveau widget / composant Qt (`src/ankiforge/ui/`) | `DESIGN.md` §inventaire, `07_inventaire_composants_ui.md` |
| Nouveau modèle Peewee (`src/ankiforge/database/`) | `03_modele_donnees_synchro.md`, `AGENTS.md` key files si central |
| Nouvelle vue applicative | `07_inventaire_composants_ui.md`, `08_plan_implementation_global.md`, `04_ui_ux_et_maquettes.md` |
| Vue complétée (statut passe à ✅) | `08_plan_implementation_global.md` |
| Nouveau service IA / fournisseur LLM | `05_services_ia_et_analyse.md`, `GEMINI.md` règle 10 |
| Nouveau type d'étape DAG ou outil MCP | `06_moteur_orchestration_ia.md`, `GEMINI.md` règle 3/4 |
| Nouvelle commande CLI / entrée pyproject | `AGENTS.md` (Key Commands) |
| Nombre de tests mis à jour | `AGENTS.md` (ligne "all X+ tests") |
| Nouveau fichier clé `src/ankiforge/` | `AGENTS.md` (Key Files / Entry Points) |
| Nouvelle règle d'architecture | `GEMINI.md` (section Règles Métier), numérotation séquentielle |
| Nouveau skill créé | `GEMINI.md` (section Skills), `AGENTS.md` |
| Nouveau thème ou layout Qt | `DESIGN.md` (PARTIE 2 — inventaire thèmes/layouts) |
| Feature visible utilisateur | `README.md`, `PRODUCT.md` |
| Modification CI/CD | `09_qualite_et_deploiement.md`, `AGENTS.md` (CI/CD section), `GEMINI.md` règle 20 |

## 4. Workflow d'Application Directe (Mode B)

### 4.1 Lire les fichiers impactés
Pour chaque fichier de la colonne "Fichiers à mettre à jour" (§3), lire son contenu actuel
avec `view_file` pour comprendre la structure existante avant de modifier.

### 4.2 Appliquer les mises à jour

Utiliser exclusivement `replace_file_content` pour les modifications ciblées.
N'utiliser `run_command` avec `cat >` que pour créer de **nouveaux** fichiers (ex: nouveau skill).

**Règles d'écriture :**
- Respecter scrupuleusement le style et le format existant du fichier cible (même niveau de détail,
  même notation emoji, même structure de tableau si applicable).
- Pour `GEMINI.md` : les règles sont numérotées de 1 à N, ne jamais réordre les existantes.
- Pour `DESIGN.md` : les nouveaux widgets vont en **Partie 1** (§1.1 Matrice de correspondance)
  et en **Partie 3** (si applicable). Toujours spécifier les tokens `DesignTokens.*` utilisés.
- Pour `AGENTS.md` (ligne test count) : mettre à jour le chiffre dans "all X+ tests" après avoir
  vérifié avec `uv run pytest --collect-only -q | tail -3`.
- Pour `08_plan_implementation_global.md` : utiliser les statuts `✅ Opérationnel`, `🔄 En cours`,
  `❌ Non implémenté`.

### 4.3 Cohérence croisée
Après toute modification, vérifier la cohérence entre fichiers liés :
- Un nouveau skill dans `.agents/skills/` → vérifier qu'il est référencé dans `GEMINI.md`.
- Un nouveau widget dans `DESIGN.md` → vérifier qu'il est aussi dans `07_inventaire_composants_ui.md`.
- Une nouvelle commande dans `pyproject.toml` → vérifier qu'elle est dans `AGENTS.md`.

## 5. Rapport Final

À la fin de chaque exécution, produire un résumé structuré dans le chat :

```
## 📋 Métadonnées mises à jour

| Fichier | Modification |
|---|---|
| GEMINI.md | Ajout règle 21 : ... |
| AGENTS.md | Mise à jour compteur tests : 146 → 152 |
| DESIGN.md | Ajout widget `NewWidget` en §1.1 |
| ... | ... |

**Rollback si nécessaire :** `git diff HEAD` pour voir les changements, `git checkout HEAD -- <fichier>` pour annuler.
```

## ⛔ Ne PAS utiliser ce skill si...

- **Le skill s'active sur des mots-clés** — il ne doit JAMAIS s'activer automatiquement. L'invocation
  doit être **explicite** de la part de l'utilisateur (demande directe ou commande `/`).
- La modification documentaire est **triviale** (faute de frappe, reformulation de phrase) — utiliser
  les outils d'édition directement sans invoquer le skill.
- L'utilisateur demande un **audit** de la cohérence sans vouloir modifier → utiliser `audit-ankiforge`.
- La mise à jour concerne uniquement **`GEMINI.md`** avec une règle très structurante nécessitant
  une relecture humaine avant commit → informer l'utilisateur et lui demander confirmation car
  `GEMINI.md` est le system prompt de tous les agents.
- Le projet n'utilise pas git (`git status` échoue) — signaler et demander confirmation avant
  toute modification de métadonnée (pas de rollback possible).
