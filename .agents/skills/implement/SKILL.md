---
name: implement
description: >-
  Implémente une tâche ou un ticket Obsidian en déroulant le cycle TDD, les vérifications statiques et la revue de code avant livraison.
  Use when the user asks to "implement", "implémenter", "coder le ticket", "développer", or starts building a feature or bugfix from a spec or Obsidian ticket.
  When NOT to use: Do not use for exploratory interview (use grill-with-docs) or ticket slicing (use to-tickets).
disable-model-invocation: true
---

# Implement — Implémentation Pilotée par les Tests et Suivi Obsidian

Prend en charge la réalisation d'une tâche, d'une spécification ou d'un ticket Obsidian (`ankiforge_obsidian/Tickets/<Type> - <Titre>.md`).

## 1. Démarrage et Cycle de Vie Obsidian

1. **Prise en charge du ticket** :
   - Lire la note du ticket ciblée dans `ankiforge_obsidian/Tickets/`.
   - Dans le tableau Kanban `ankiforge_obsidian/Avancement du projet.md`, déplacer la carte correspondante vers la colonne `## 🏃 En cours`.
   - **Règle anti-boucle** : appliquer la modification en une seule passe atomique (One-shot pass) sans relecture circulaire.
2. **Clarifier la couture (Seam)** :
   - Vérifier les critères d'acceptation et identifier le point d'entrée modulaire (modèle, service, ou widget Qt).

## 2. Développement Test-First (/tdd)

- Développer le comportement attendu tranche par tranche en pilotant **`/tdd`** :
  1. Écrire le test unitaire ou d'intégration rouge (`tests/...`).
  2. Implémenter le code minimal pour passer le test au vert.
  3. Refactoriser pour la lisibilité et la compacité.
- **Règles d'ingénierie AnkiForge obligatoires** :
  - Typage strict 100% (`mypy`).
  - Aucun `print()`, utiliser exclusivement le logging asynchrone (`logging.getLogger(__name__)`).
  - Tests UI Qt 100% headless (`pytest-qt`, `QT_QPA_PLATFORM=offscreen`).
  - Mocks LLM obligatoires (zéro appel API payant en test).

## 3. Clôture, Vérification Canonique & Revue

1. **Pré-synchronisation des traductions i18n (`ADR 0013`)** :
   - Si des chaînes utilisateur ont été ajoutées ou modifiées avec `tr()` dans l'UI :
     ```bash
     uv run python script/extract_translations.py
     ```
     Cette étape met à jour les catalogues `.ts` (`ankiforge_fr.ts`, `ankiforge_en.ts`) et compile les `.qm`, prévenant tout échec de `test_committed_catalog_matches_a_fresh_extraction`.
2. **Porte de vérification canonique** :
   ```bash
   uv run python script/verify.py
   ```
   Exécute la chaîne complète (ruff check/format, mypy strict, bandit, tests rapides).
3. **Revue de code à deux axes (Obligatoire)** :
   - Déclencher systématiquement **`/code-review`** (deux sous-agents parallèles : Standards & Spécification) pour confronter le diff aux exigences avant toute clôture.
   > [!IMPORTANT]
   > ⛔ **Garde-fou bloquant** : Il est formellement INTERDIT de clore le ticket, de modifier son statut en `✅ Terminé`, de toucher au Kanban ou de formuler une proposition de commit avant d'avoir formellement restitué le rapport de code-review à deux axes à l'utilisateur.
4. **Mise à jour du statut Obsidian & Archivage Physique (Post-Revue)** :
   - Mettre à jour l'en-tête du ticket : `**Statut :** ✅ Terminé` et cocher les critères d'acceptation.
   - **Déplacement physique obligatoire** : déplacer la note du ticket de `ankiforge_obsidian/Tickets/ticket-actif/` vers `ankiforge_obsidian/Tickets/Archives/` (ainsi que les spécifications associées). La racine `Tickets/` ne doit jamais comporter de fichier à plat.
   - Déplacer la carte dans `ankiforge_obsidian/Avancement du projet.md` vers `## ✅ Terminé (done)` en ajustant le lien vers `[[Tickets/Archives/<Nom>|<Titre>]]`.
   - Vérifier l'absence de fichiers fantômes résiduels de 0 octet à la racine de `Tickets/`.
   - Si la colonne `Terminé` dépasse 15 items, archiver les plus anciens dans `Archives - Tickets Terminés.md`.
   - **Sous-Dépôt Git Autonome** : `ankiforge_obsidian/` dispose de son propre dépôt Git ignoré par la racine. Ne jamais l'inclure dans un `git add` du projet principal ; proposer un commit dédié via `git -C ankiforge_obsidian`.
   - **Arrêt immédiat** (One-shot pass).

## When NOT to use this skill

- Ne pas utiliser pour cadrer une idée non formalisée → utiliser `/grill-with-docs`.
- Ne pas utiliser pour découper une spécification en plusieurs tickets → utiliser `/to-tickets`.
- Ne pas utiliser pour qualifier des retours bruts → utiliser `/triage`.
