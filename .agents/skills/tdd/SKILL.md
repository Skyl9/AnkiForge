---
name: tdd
description: >-
  Méthodologie du développement piloté par les tests (Red-Green-Refactor) en Python 3.12 pour AnkiForge. Définit les règles des boucles de tests aux coutures publiques, la conception pour la testabilité et la prévention des anti-patterns de test.
  Use when the user asks to "tdd", "red-green-refactor", "écrire les tests d'abord", "test-first", "concevoir par les tests", or wants to build features and bugfixes test-first in Python.
  When NOT to use: Do not use for orchestrating full ticket lifecycle, pre-push gate and code reviews (use implement).
---

# 🔴🟢 Test-Driven Development (TDD) — AnkiForge

Le **TDD** est la boucle itérative stricte **Rouge ➔ Vert ➔ Refactorisation**. Cette compétence est la référence méthodologique garantissant que cette boucle produise des tests fiables, véloces et pérennes dans l'écosystème Python 3.12, PySide6 et Peewee d'AnkiForge.

> **Guides associés** :
> - [tests.md](tests.md) : Exemples comparatifs (Bons vs Mauvais tests) sur les 3 piliers d'AnkiForge.
> - [mocking.md](mocking.md) : Lignes directrices de mock aux frontières système (Mocks LLM, BDD SQLite mémoire, workers).

---

## 1. Ce qu'est un Bon Test

Les tests vérifient le comportement observable à travers les **interfaces publiques**, jamais les détails d'implémentation privés. Le code interne peut être totalement refactorisé ; les tests ne doivent pas casser tant que le comportement externe reste identique.

Un bon test se lit comme une spécification métier :
- Exprime le **QUOI** (le résultat attendu), pas le **COMMENT** (les étapes internes).
- Ne dépend d'aucun état global persistant ni appel réseau distant.
- Survit aux refactorisations internes.

---

## 2. Les Coutures (Seams) : Où Poser les Tests

Une **couture (seam)** est la frontière publique où vous observez le comportement d'un module sans pénétrer à l'intérieur :
- **Tester uniquement aux coutures convenues** : n'écrivez aucun test contre des méthodes privées (`_methode_interne`).
- Si la forme de l'interface pose question (profondeur du module, couplage), consulter le vocabulaire de `codebase-design`.

---

## 3. Anti-Patterns de Test à Proscrire

1. **Couplage aux détails d'implémentation** :
   - Mocker des collaborateurs internes privés.
   - Vérifier le nombre exact d'appels internes (`assert mock.call_count == 2`) au lieu du résultat observable.
   - Symptôme : le test casse lors d'un renommage de méthode privée alors que le comportement reste intact.
2. **Test tautologique** :
   - L'assertion recalcule la valeur attendue avec la même logique que le code testé (`assert result == a + b`). Le test passe par construction et n'a aucune valeur de validation.
   - La valeur attendue doit provenir d'un oracle indépendant : un cas d'exemple vérifié, un contrat de spec, ou une constante littérale.
3. **Découpage horizontal (Horizontal Slicing)** :
   - Écrire tous les tests d'un coup, puis tout le code. Cela teste un comportement imaginaire.
   - Travailler par **tranches verticales (Vertical Slices)** : un test unitaire rouge ➔ l'implémentation minimale ➔ vert ➔ refactorisation ➔ test suivant.

---

## 4. Règles de la Boucle TDD

1. **Le Rouge avant le Vert** : toujours exécuter le test pour le voir échouer sur la cause attendue (`assert False` ou exception métier).
2. **Code minimal** : n'écrire que la quantité stricte de code nécessaire pour faire passer le test au vert. Pas de fonctionnalités spéculatives.
3. **Refactorisation propre** : une fois au vert, assainir la clarté du code et l'élimination des duplications avant d'aborder la tranche suivante.

---

## When NOT to use this skill

- Ne pas utiliser pour orchestrer la prise en charge d'un ticket Obsidian, la mise à jour du Kanban, le passage de la porte canonique `script/verify.py` et la revue finale → utiliser `/implement`.
- Ne pas utiliser pour explorer visuellement une maquette UI sans logique → utiliser `/prototype` ou `ui-screenshot`.
- Ne pas utiliser pour diagnostiquer un bogue complexe non isolé → utiliser `/diagnosing-bugs`.
