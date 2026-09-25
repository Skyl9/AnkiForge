---
name: proposer-commits
description: Analyse les modifications de l'arbre Git et propose un découpage en un ou plusieurs commits atomiques au format Conventional Commits v1.0.0 en français sans jamais committer sans accord explicite. Use when code changes are complete, before ending a turn with modified git files, or when asked to "proposer les commits", "commit", "messages de commit", "préparer le commit".
---

# Proposer des Commits Atomiques (Conventional Commits)

Ce skill encadre la fin de toute intervention modifiant l'arbre Git. Il interdit tout commit autonome non sollicité et formule des propositions de commits atomiques conformes à la spécification **Conventional Commits v1.0.0 en français**.

## 🛡️ Règle d'Or : Aucun Commit Sans Accord Explicite

- **Interdiction formelle de committer ou pusher en douce :** L'agent ne doit JAMAIS exécuter `git commit` ou `git push` de sa propre initiative.
- **Délégation et validation :** L'agent inspecte `git status` et `git diff`, formule une ou plusieurs propositions claires avec leurs fichiers cibles, et attend la confirmation explicite de l'utilisateur avant d'exécuter la moindre commande d'enregistrement dans l'historique Git.

## 📋 Découpage Atomique & Responsabilités

Ne regroupez pas des modifications disparates dans un commit fourre-tout. Découpez les changements par unité logique :
1. **Un commit par préoccupation :** Isoler un refactoring (`refactor:`), un ajout de tests (`test:`), une correction de bug (`fix:`), une mise à jour de documentation (`docs:`) ou une nouvelle fonctionnalité (`feat:`).
2. **Ciblage strict des fichiers :** Chaque commit proposé doit spécifier la liste exacte des fichiers à indexer via `git add <fichiers>`, sans utiliser aveuglément `git add .` ou `git add -A`.

## ✍️ Règles Conventional Commits v1.0.0 (Français)

Chaque proposition respecte strictement ce formalisme :

1. **Format :** `<type>(<portée optionnelle>): <description courte>` suivi d'un corps détaillé.
2. **Longueur des lignes (critique) :** Aucune ligne (en-tête comme corps) ne doit excéder **250 caractères** pour éviter toute coupure ou troncature visuelle dans les interfaces Git (recommandé : retours à la ligne entre 72 et 100 caractères).
3. **Corps du commit :**
   - Fournir du détail sur le *pourquoi* et les changements structurants.
   - Structurer en puces ou paragraphes clairs.
4. **Types autorisés :**
   - `feat:` (nouvelle fonctionnalité)
   - `fix:` (correction d'anomalie ou de bug)
   - `docs:` (documentation, guides, docstrings seules)
   - `style:` (formatage, lint, espaces ; aucun impact sur le code métier)
   - `refactor:` (restructuration sans ajout de fonctionnalité ni correction)
   - `perf:` (gain mesuré de performance ou réduction de latence/mémoire)
   - `test:` (ajout, correction ou fiabilisation de tests unitaires/UI)
   - `build:` (dépendances pyproject.toml, uv, builds Nuitka/DMG, extensions C)
   - `ci:` (workflows GitHub Actions, hooks de qualité)
   - `chore:` (maintenance courante, mise à jour de scripts internes)
5. **Portée (scope) :** Indiquer le composant ou module entre parenthèses si pertinent (ex: `(ui)`, `(batch)`, `(rag)`, `(peewee)`, `(obsidian)`).
6. **Description (titre) :**
   - Rédigée en **français**.
   - À l'**impératif présent** (ex: `ajoute`, `corrige`, `supprime`, `met à jour` au lieu de `ajouté`, `ajout` ou `correction`).
   - **Pas de majuscule** au premier mot de la description.
   - **Pas de point final**.
7. **Rupture de compatibilité (Breaking Change) :**
   - Ajouter un point d'exclamation après le type ou la portée : `feat!:` ou `feat(api)!:`.
   - Mentionner `BREAKING CHANGE: <explication>` dans le corps du commit.

## 📤 Format de Présentation Attendu

Pour chaque commit suggéré, présenter le résultat ainsi :

```markdown
### 📦 Commit [N] : `<type>(<scope>): <description>`
- **Fichiers :** `chemin/vers/fichier1`, `chemin/vers/fichier2`
- **Message détaillé :**
  > **Titre :** `<type>(<scope>): <description>`
  > **Corps :**
  > - <Détail 1>
  > - <Détail 2>
- **Commande suggérée :**
  ```bash
  git add chemin/vers/fichier1 chemin/vers/fichier2
  git commit -m "<type>(<scope>): <description>" -m "<corps détaillé ligne 1>" -m "<corps détaillé ligne 2>"
  ```
```

Terminer en demandant à l'utilisateur :
*« Souhaites-tu que j'exécute ce(s) commit(s) ou veux-tu ajuster les messages ou le découpage ? »*

## ⛔ Ne PAS utiliser ce skill si...

- L'arbre Git est propre (`git status` ne retourne aucun fichier modifié ou non suivi).
- Les tests ou vérifications de qualité (`ruff`, `mypy`, `pytest`) ne sont pas encore passés au vert.
- L'utilisateur a explicitement demandé une commande git bas niveau (ex. `git stash`, `git checkout`).
